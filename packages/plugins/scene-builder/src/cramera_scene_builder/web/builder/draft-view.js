/**
 * The builder's 3D view: the draft's instances over the viewer's ground and studio
 * lights, transform handles on the selection, and picking by click.
 */

import * as THREE from 'three';
import { TransformControls } from 'three/addons/controls/TransformControls.js';

import { DraftKey, InstanceKey } from '../../../protocol.js';
import { Bounds } from '../../../scene/bounds.js';
import { SceneLighting } from '../../../scene/scene-lighting.js';
import { SceneView } from '../../../scene/scene-view.js';
import { PickMark, PlacedInstance } from './placed-instance.js';

/**
 * What the transform handles change.
 */
export const TransformMode = Object.freeze({ MOVE: 'translate', ROTATE: 'rotate', SCALE: 'scale' });

/**
 * How far a pointer may travel between press and release for a click, in pixels.
 */
const CLICK_DISTANCE = 5;

/**
 * How close to a point a click picks it, in metres.
 */
const POINT_PICK_DISTANCE = 0.012;

/**
 * The region that receives shadows while the draft is empty, in metres.
 */
const EMPTY_REGION = new Bounds([-2, -2, 0], [2, 2, 2]);

/**
 * The colour of the box around the selection.
 */
const SELECTION_COLOR = 0x0f766e;

/**
 * The events of the transform handles and the canvas the view listens to.
 */
const ViewEvent = Object.freeze({
  DRAGGING_CHANGED: 'dragging-changed',
  HANDLE_PRESSED: 'mouseDown',
  OBJECT_CHANGED: 'objectChange',
  CHANGED: 'change',
  POINTER_DOWN: 'pointerdown',
  POINTER_UP: 'pointerup',
});

/**
 * The components of a scale, in order.
 */
const SCALE_COMPONENTS = Object.freeze(['x', 'y', 'z']);

/**
 * The primary mouse button.
 */
const PRIMARY_BUTTON = 0;

// %% selection

/**
 * The selected instance and, when one of its links is selected, that link.
 */
export class Selection {
  /**
   * @param {string} instance The instance's identity.
   * @param {string|null=} link The selected link's name, or null for the whole instance.
   */
  constructor(instance, link = null) {
    /**
     * The instance's identity.
     * @type {string}
     */
    this.instance = instance;
    /**
     * The selected link's name, or null for the whole instance.
     * @type {string|null}
     */
    this.link = link;
  }
}

/**
 * What the view reports to the page.
 */
export class DraftViewListeners {
  /**
   * @param {function(Selection): void} onPick Called when a click picks an instance.
   * @param {function(Selection, Object): void} onPlace Called when a handle drag ends,
   *   with the target's position, rotation and scale.
   * @param {function(string): void} onLoaded Called when an instance's resource is shown.
   * @param {function(Error): void} onError Called when a resource cannot be shown.
   */
  constructor(onPick, onPlace, onLoaded, onError) {
    /**
     * Called when a click picks an instance.
     * @type {function(Selection): void}
     */
    this.onPick = onPick;
    /**
     * Called when a handle drag ends.
     * @type {function(Selection, Object): void}
     */
    this.onPlace = onPlace;
    /**
     * Called when an instance's resource is shown.
     * @type {function(string): void}
     */
    this.onLoaded = onLoaded;
    /**
     * Called when a resource cannot be shown.
     * @type {function(Error): void}
     */
    this.onError = onError;
  }
}

// %% view

export class DraftView {
  /**
   * The viewer's 3D view.
   * @type {SceneView}
   */
  #view;

  /**
   * The studio lights.
   * @type {SceneLighting}
   */
  #lighting = new SceneLighting();

  /**
   * The transform handles.
   * @type {TransformControls}
   */
  #handles;

  /**
   * The box around the selection.
   * @type {THREE.BoxHelper}
   */
  #selectionBox;

  /**
   * Loads the instances' resources.
   * @type {import('./resource-loading.js').ResourceLoading}
   */
  #loading;

  /**
   * What the view reports.
   * @type {DraftViewListeners}
   */
  #listeners;

  /**
   * The shown instances by identity.
   * @type {Map<string, PlacedInstance>}
   */
  #instances = new Map();

  /**
   * The resource each instance is being loaded for, by identity.
   * @type {Map<string, string>}
   */
  #pending = new Map();

  /**
   * The draft being shown.
   * @type {Object}
   */
  #draft = { [DraftKey.INSTANCES]: [] };

  /**
   * The selection, or null.
   * @type {Selection|null}
   */
  #selection = null;

  /**
   * What the handles change.
   * @type {string}
   */
  #mode = TransformMode.MOVE;

  /**
   * Whether scaling one axis scales all three alike.
   * @type {boolean}
   */
  #proportional = true;

  /**
   * The target's scale when a scale drag started.
   * @type {THREE.Vector3|null}
   */
  #scaleStart = null;

  /**
   * Where the pointer was pressed, or null.
   * @type {{x: number, y: number, onHandle: boolean}|null}
   */
  #press = null;

  /**
   * The listeners on the canvas, to remove them again.
   * @type {Array<[string, function(Event): void]>}
   */
  #canvasListeners = [];

  /**
   * @param {Document} document The page's document.
   * @returns {boolean} Whether the browser can show the 3D view.
   */
  static isAvailable(document) {
    return Boolean(document.createElement('canvas').getContext('webgl2'));
  }

  /**
   * @param {HTMLElement} container The element the canvas fills.
   * @param {import('./resource-loading.js').ResourceLoading} loading Loads the resources.
   * @param {DraftViewListeners} listeners What the view reports.
   */
  constructor(container, loading, listeners) {
    this.#loading = loading;
    this.#listeners = listeners;
    this.#view = new SceneView(container);
    this.#view.scene.add(this.#lighting.group);
    this.#lighting.showStudio(this.#view.renderer, this.#view.scene, EMPTY_REGION);
    this.#view.frame(EMPTY_REGION);
    this.#handles = new TransformControls(this.#view.camera, this.#view.renderer.domElement);
    this.#handles.addEventListener(ViewEvent.DRAGGING_CHANGED, (event) => {
      this.#view.controls.enabled = !event.value;
      if (!event.value) this.#finishDrag();
    });
    this.#handles.addEventListener(ViewEvent.HANDLE_PRESSED, () => this.#startDrag());
    this.#handles.addEventListener(ViewEvent.OBJECT_CHANGED, () => this.#keepProportions());
    this.#handles.addEventListener(ViewEvent.CHANGED, () => this.#view.requestRender());
    this.#view.scene.add(this.#handles.getHelper());
    this.#selectionBox = new THREE.BoxHelper(new THREE.Object3D(), SELECTION_COLOR);
    this.#selectionBox.visible = false;
    this.#view.scene.add(this.#selectionBox);
    this.#listenOnCanvas(ViewEvent.POINTER_DOWN, (event) => {
      this.#press = { x: event.clientX, y: event.clientY, onHandle: this.#handles.axis !== null };
    });
    this.#listenOnCanvas(ViewEvent.POINTER_UP, (event) => this.#pick(event));
    this.#view.start(() => {
      if (this.#selectionBox.visible) this.#selectionBox.update();
      return false;
    });
  }

  /**
   * Show a draft: load the instances it adds, update those it keeps, remove the others.
   * @param {Object} draft The draft.
   * @param {function(string): (Object|undefined)} resource The catalog's resource of an identifier.
   */
  show(draft, resource) {
    this.#draft = draft;
    const wanted = new Map(draft[DraftKey.INSTANCES].map((instance) => [instance[InstanceKey.IDENTIFIER], instance]));
    for (const [identifier, placed] of this.#instances) {
      if (wanted.get(identifier)?.[InstanceKey.ASSET] !== placed.asset) this.#remove(identifier);
    }
    for (const [identifier, instance] of wanted) {
      const placed = this.#instances.get(identifier);
      if (placed) placed.apply(instance);
      else if (this.#pending.get(identifier) !== instance[InstanceKey.ASSET]) this.#load(instance, resource(instance[InstanceKey.ASSET]));
    }
    this.select(this.#selection && wanted.has(this.#selection.instance) ? this.#selection : null);
    this.#view.requestRender();
  }

  /**
   * @param {Selection|null} selection The instance or link to select, or null.
   */
  select(selection) {
    this.#selection = selection;
    this.#handles.detach();
    this.#selectionBox.visible = false;
    const placed = selection && this.#instances.get(selection.instance);
    if (!placed) return;
    const target = placed.target(selection.link);
    this.#selectionBox.setFromObject(target);
    this.#selectionBox.visible = placed.group.visible;
    const scalingLink = selection.link !== null && this.#mode === TransformMode.SCALE;
    if (placed.isEditable && !scalingLink) {
      this.#handles.attach(target);
      this.#handles.setMode(this.#mode);
    }
    this.#view.requestRender();
  }

  /**
   * @param {string} mode A `TransformMode` value.
   */
  setMode(mode) {
    this.#mode = mode;
    this.select(this.#selection);
  }

  /**
   * @param {boolean} proportional Whether scaling one axis scales all three alike.
   */
  setProportional(proportional) {
    this.#proportional = proportional;
  }

  /**
   * @returns {boolean} Whether a resource of the draft is still loading.
   */
  isLoading() {
    return this.#pending.size > 0;
  }

  /**
   * @param {string} identifier An instance identity.
   * @returns {{links: Array<string>, joints: Array<Object>}} The shown model's links and
   *   movable joints; none while it loads.
   */
  structure(identifier) {
    return this.#instances.get(identifier)?.structure() ?? { links: [], joints: [] };
  }

  /**
   * Look at the selection from far enough to see all of it.
   */
  frameSelection() {
    const placed = this.#selection && this.#instances.get(this.#selection.instance);
    if (placed) this.#frame(placed.target(this.#selection.link));
  }

  /**
   * Look at every instance.
   */
  frameAll() {
    this.#frame(this.#view.content);
  }

  /**
   * Stop rendering and free the view, its instances and its listeners.
   */
  dispose() {
    for (const identifier of [...this.#instances.keys()]) this.#remove(identifier);
    for (const [type, listener] of this.#canvasListeners) this.#view.renderer.domElement.removeEventListener(type, listener);
    this.#handles.dispose();
    this.#lighting.dispose(this.#view.scene);
    this.#view.dispose();
  }

  /**
   * @param {Object} instance The draft's instance.
   * @param {Object|undefined} resource Its catalog resource.
   */
  #load(instance, resource) {
    const identifier = instance[InstanceKey.IDENTIFIER];
    const asset = instance[InstanceKey.ASSET];
    if (!resource) {
      this.#listeners.onError(new Error(`The catalog offers no resource ${asset}.`));
      return;
    }
    this.#pending.set(identifier, asset);
    this.#loading.load(resource, instance[InstanceKey.POINT_CLOUD] ?? null).then(
      (root) => {
        const current = this.#draft[DraftKey.INSTANCES].find((candidate) => candidate[InstanceKey.IDENTIFIER] === identifier);
        if (this.#pending.get(identifier) !== asset || current?.[InstanceKey.ASSET] !== asset) return;
        this.#pending.delete(identifier);
        const placed = new PlacedInstance(current, root);
        this.#instances.set(identifier, placed);
        this.#view.content.add(placed.group);
        if (this.#pending.size === 0) this.#shadeRegion();
        if (this.#selection?.instance === identifier) this.select(this.#selection);
        this.#view.requestRender();
        this.#listeners.onLoaded(identifier);
      },
      (error) => {
        this.#pending.delete(identifier);
        this.#listeners.onError(error);
      },
    );
  }

  /**
   * @param {string} identifier The identity of a shown instance.
   */
  #remove(identifier) {
    if (this.#selection?.instance === identifier) this.#handles.detach();
    this.#instances.get(identifier).dispose();
    this.#instances.delete(identifier);
  }

  /**
   * Let the studio's key light cast shadows over every model, once every pending
   * resource is shown; reference point clouds cast none and may span a whole room.
   */
  #shadeRegion() {
    const box = new THREE.Box3();
    for (const placed of this.#instances.values()) if (!placed.isPointCloud) box.expandByObject(placed.group);
    const region = box.isEmpty() ? EMPTY_REGION : new Bounds(box.min.toArray(), box.max.toArray());
    this.#lighting.showStudio(this.#view.renderer, this.#view.scene, region);
  }

  /**
   * @param {THREE.Object3D} object What to look at.
   */
  #frame(object) {
    const box = new THREE.Box3().setFromObject(object);
    if (!box.isEmpty()) this.#view.frame(new Bounds(box.min.toArray(), box.max.toArray()));
  }

  /**
   * Remember the target's scale when a drag starts.
   */
  #startDrag() {
    this.#scaleStart = this.#handles.object ? this.#handles.object.scale.clone() : null;
  }

  /**
   * While scaling proportionally, scale all three axes as the dragged one.
   */
  #keepProportions() {
    if (this.#mode !== TransformMode.SCALE || !this.#proportional || !this.#scaleStart) return;
    const scale = this.#handles.object.scale;
    const axis = SCALE_COMPONENTS.find((component) => scale[component] !== this.#scaleStart[component]);
    if (axis) scale.copy(this.#scaleStart).multiplyScalar(scale[axis] / this.#scaleStart[axis]);
  }

  /**
   * Report the dragged target's new placement as one change.
   */
  #finishDrag() {
    const placed = this.#selection && this.#instances.get(this.#selection.instance);
    this.#scaleStart = null;
    if (placed) this.#listeners.onPlace(this.#selection, placed.placement(this.#selection.link));
  }

  /**
   * @param {string} type An event type.
   * @param {function(Event): void} listener Its listener on the canvas.
   */
  #listenOnCanvas(type, listener) {
    this.#view.renderer.domElement.addEventListener(type, listener);
    this.#canvasListeners.push([type, listener]);
  }

  /**
   * Select what a click hits: the whole instance, or with Alt the hit URDF link.
   * Locked and hidden references cannot be picked, so clicks reach the models over them.
   * @param {PointerEvent} event The pointer's release.
   */
  #pick(event) {
    const press = this.#press;
    this.#press = null;
    if (!press || press.onHandle || event.button !== PRIMARY_BUTTON) return;
    if (Math.hypot(event.clientX - press.x, event.clientY - press.y) > CLICK_DISTANCE) return;
    const canvas = this.#view.renderer.domElement.getBoundingClientRect();
    const pointer = new THREE.Vector2(((event.clientX - canvas.left) / canvas.width) * 2 - 1, 1 - ((event.clientY - canvas.top) / canvas.height) * 2);
    const ray = new THREE.Raycaster();
    ray.params.Points.threshold = POINT_PICK_DISTANCE;
    ray.setFromCamera(pointer, this.#view.camera);
    const pickable = [...this.#instances.values()].filter((placed) => placed.group.visible && placed.isEditable).map((placed) => placed.group);
    const hit = ray.intersectObjects(pickable, true)[0];
    if (!hit) return;
    let current = hit.object;
    let link = null;
    while (current && current.userData[PickMark.INSTANCE] === undefined) {
      link = link ?? current.userData[PickMark.LINK] ?? null;
      current = current.parent;
    }
    const selection = new Selection(current.userData[PickMark.INSTANCE], event.altKey ? link : null);
    this.select(selection);
    this.#listeners.onPick(selection);
  }
}
