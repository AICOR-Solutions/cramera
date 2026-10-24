/**
 * The builder's 3D view: the environment bundle as the viewer shows it, and over it the
 * plan's robots, objects and the edited robot's targets as markers that are picked by a
 * click and moved or turned with handles.
 */

import * as THREE from 'three';
import { TransformControls } from 'three/addons/controls/TransformControls.js';
import URDFLoader from 'urdf-loader';

import { PlannedObjectKey, PlannedRobotKey, PlanStepKey } from '../../../protocol.js';
import { Bounds } from '../../../scene/bounds.js';
import { MeshLoading } from '../../../scene/mesh-loading.js';
import { SceneLighting } from '../../../scene/scene-lighting.js';
import { SceneLoader } from '../../../scene/scene-loader.js';
import { SceneView } from '../../../scene/scene-view.js';
import { PlanPose } from './poses.js';

/**
 * What a marker stands for.
 */
export const MarkerKind = Object.freeze({ ROBOT: 'robot', OBJECT: 'object', TARGET: 'target' });

/**
 * What the handles change.
 */
export const TransformMode = Object.freeze({ MOVE: 'translate', TURN: 'rotate' });

/**
 * The suffix of an object library model's description.
 */
const DESCRIPTION_SUFFIX = '.urdf';

/**
 * The region shown on an empty floor, in metres.
 */
const FLOOR_REGION = new Bounds([-1, -1, 0], [3, 3, 1.5]);

/**
 * The sizes of the markers, in metres.
 */
const MarkerSize = Object.freeze({
  ROBOT_RADIUS: 0.35,
  ROBOT_HEIGHT: 0.04,
  ARROW_LENGTH: 0.3,
  ARROW_RADIUS: 0.08,
  TARGET_RADIUS: 0.22,
  TARGET_TUBE: 0.025,
  PLACEHOLDER: 0.06,
  LABEL_LIFT: 0.3,
});

/**
 * The height of a robot's name label as a share of the view's height; the label keeps
 * its size on the screen however far the camera is.
 */
const LABEL_SCREEN_HEIGHT = 0.035;

/**
 * How a robot's name label is drawn: the canvas's font size and padding in pixels, and
 * its colours.
 */
const RobotLabel = Object.freeze({
  FONT_SIZE: 48,
  PADDING: 16,
  FONT: '600 48px system-ui, sans-serif',
  TEXT: '#f8fafc',
  BACKGROUND: 'rgba(15, 23, 42, 0.82)',
  EDITED_BACKGROUND: 'rgba(13, 148, 136, 0.92)',
});

/**
 * The colours of the markers.
 */
const MarkerColor = Object.freeze({
  ROBOT: 0x0f766e,
  EDITED_ROBOT: 0x14b8a6,
  OBJECT: 0xd6dde6,
  TARGET: 0x7c3aed,
  PUT_DOWN: 0xf59e0b,
  SELECTION: 0x0ea5e9,
});

/**
 * How see-through a put-down target is.
 */
const TARGET_OPACITY = 0.45;

/**
 * Segments of the round markers.
 */
const SEGMENTS = 32;

/**
 * How far a pointer may travel between press and release for a click, in pixels.
 */
const CLICK_DISTANCE = 5;

/**
 * The primary mouse button.
 */
const PRIMARY_BUTTON = 0;

/**
 * The events of the handles and the canvas the view listens to.
 */
const ViewEvent = Object.freeze({
  DRAGGING_CHANGED: 'dragging-changed',
  CHANGED: 'change',
  POINTER_DOWN: 'pointerdown',
  POINTER_UP: 'pointerup',
});

/**
 * The key a marker's selection is kept under in its object's user data.
 */
const SELECTION_DATA = 'planSelection';

// %% selection

/**
 * A marker the person picked: a robot, an object, or a pose field of a step.
 */
export class Selection {
  /**
   * @param {string} kind A `MarkerKind` value.
   * @param {string} identifier The identity of the robot, object or step.
   * @param {string|null=} field The pose field of a step's target, else null.
   */
  constructor(kind, identifier, field = null) {
    /**
     * What the marker stands for.
     * @type {string}
     */
    this.kind = kind;
    /**
     * The identity of the robot, object or step.
     * @type {string}
     */
    this.identifier = identifier;
    /**
     * The pose field of a step's target, else null.
     * @type {string|null}
     */
    this.field = field;
  }

  /**
   * @param {Selection|null} other Another selection.
   * @returns {boolean} Whether both pick the same marker.
   */
  equals(other) {
    return other !== null && other.key === this.key;
  }

  /**
   * @returns {string} The marker's key among all markers.
   */
  get key() {
    return this.field === null ? `${this.kind}:${this.identifier}` : `${this.kind}:${this.identifier}:${this.field}`;
  }
}

/**
 * What the view reports to the page.
 */
export class PlanSceneListeners {
  /**
   * @param {function(Selection|null): void} onPick Called when a click picks a marker or
   *   nothing.
   * @param {function(Selection, Array<number>): void} onPlace Called when a handle drag
   *   ends, with the marker's new pose.
   * @param {function(Error): void} onError Called when the environment or a mesh cannot
   *   be shown.
   */
  constructor(onPick, onPlace, onError) {
    /**
     * Called when a click picks a marker or nothing.
     * @type {function(Selection|null): void}
     */
    this.onPick = onPick;
    /**
     * Called when a handle drag ends.
     * @type {function(Selection, Array<number>): void}
     */
    this.onPlace = onPlace;
    /**
     * Called when the environment or a mesh cannot be shown.
     * @type {function(Error): void}
     */
    this.onError = onError;
  }
}

// %% view

export class PlanScene {
  /**
   * The viewer's 3D view.
   * @type {SceneView}
   */
  #view;

  /**
   * The lights of the view.
   * @type {SceneLighting}
   */
  #lighting = new SceneLighting();

  /**
   * Loads the environment bundle.
   * @type {SceneLoader}
   */
  #loader;

  /**
   * The shown environment, or null.
   * @type {import('../../../scene/scene-loader.js').LoadedScene|null}
   */
  #environment = null;

  /**
   * Cancels loading an environment another one replaced.
   * @type {AbortController|null}
   */
  #loading = null;

  /**
   * The markers, above the environment.
   * @type {THREE.Group}
   */
  #markers = new THREE.Group();

  /**
   * Each marker by its selection's key.
   * @type {Map<string, THREE.Object3D>}
   */
  #byKey = new Map();

  /**
   * Each object model's mesh once loaded, by model, copied for every object.
   * @type {Map<string, Promise<THREE.Object3D>>}
   */
  #meshes = new Map();

  /**
   * The URL of an object model's mesh.
   * @type {function(string): string}
   */
  #objectUrl;

  /**
   * What the view reports.
   * @type {PlanSceneListeners}
   */
  #listeners;

  /**
   * The handles on the selected marker.
   * @type {TransformControls}
   */
  #handles;

  /**
   * The selected marker, or null.
   * @type {Selection|null}
   */
  #selection = null;

  /**
   * What the handles change.
   * @type {string}
   */
  #mode = TransformMode.MOVE;

  /**
   * Where the pointer was pressed, or null.
   * @type {{x: number, y: number, onHandle: boolean}|null}
   */
  #press = null;

  /**
   * The canvas listeners, to remove them again.
   * @type {Array<[string, function(Event): void]>}
   */
  #canvasListeners = [];

  /**
   * @param {Document} document A document.
   * @returns {boolean} Whether its browser can show the 3D view.
   */
  static isAvailable(document) {
    return Boolean(document.createElement('canvas').getContext?.('webgl2'));
  }

  /**
   * @param {HTMLElement} container The element the view fills.
   * @param {import('../../../core/viewer-api.js').ViewerApi} api The viewer's routes.
   * @param {function(string): string} objectUrl The URL of an object model's mesh.
   * @param {PlanSceneListeners} listeners What the view reports.
   */
  constructor(container, api, objectUrl, listeners) {
    this.#objectUrl = objectUrl;
    this.#listeners = listeners;
    this.#loader = new SceneLoader(api);
    this.#view = new SceneView(container);
    this.#view.scene.add(this.#lighting.group, this.#markers);
    this.#showFloor();
    this.#handles = new TransformControls(this.#view.camera, this.#view.renderer.domElement);
    this.#handles.addEventListener(ViewEvent.DRAGGING_CHANGED, (event) => {
      this.#view.controls.enabled = !event.value;
      if (!event.value) this.#placed();
    });
    this.#handles.addEventListener(ViewEvent.CHANGED, () => this.#view.requestRender());
    this.#view.scene.add(this.#handles.getHelper());
    this.#listenOnCanvas(ViewEvent.POINTER_DOWN, (event) => {
      this.#press = { x: event.clientX, y: event.clientY, onHandle: this.#handles.axis !== null };
    });
    this.#listenOnCanvas(ViewEvent.POINTER_UP, (event) => this.#pick(event));
    this.#view.start(() => false);
  }

  /**
   * Show an environment bundle, or an empty floor.
   * @param {string|null} name The bundle's name, or null.
   * @returns {Promise<void>} Settles once the environment is shown or failed.
   */
  async showEnvironment(name) {
    this.#loading?.abort();
    this.#environment?.dispose();
    this.#environment = null;
    if (name === null) {
      this.#view.content.clear();
      this.#showFloor();
      return;
    }
    const loading = (this.#loading = new AbortController());
    const loaded = await this.#loader.load(name, this.#view, this.#lighting, loading.signal, () => {}).catch((error) => {
      if (!loading.signal.aborted) this.#listeners.onError(error);
      return null;
    });
    if (loaded && !loading.signal.aborted) this.#environment = loaded;
  }

  /**
   * Show the plan's robots and objects, and the edited robot's targets; poses the live
   * world reports win over the plan's while it runs.
   * @param {import('./plan-state.js').PlanState} state The plan.
   * @param {{objects: Map<string, Array<number>>, robots: Map<string, Array<number>>}=} live
   *   The live world's poses by the plan's identities.
   */
  show(state, live = { objects: new Map(), robots: new Map() }) {
    const wanted = new Map();
    const want = (selection, pose, signature, grounded, build) => wanted.set(selection.key, { selection, pose, signature, grounded, build });
    const edited = state.activeRobot()?.[PlannedRobotKey.IDENTIFIER];
    for (const robot of state.robots()) {
      const identifier = robot[PlannedRobotKey.IDENTIFIER];
      const isEdited = identifier === edited;
      const color = isEdited ? MarkerColor.EDITED_ROBOT : MarkerColor.ROBOT;
      const label = robot[PlannedRobotKey.LABEL];
      want(new Selection(MarkerKind.ROBOT, identifier), live.robots.get(identifier) ?? robot[PlannedRobotKey.POSE], `${color}${label}`, true, () => this.#robotMarker(color, label, isEdited));
    }
    for (const item of state.objects()) {
      const identifier = item[PlannedObjectKey.IDENTIFIER];
      const model = item[PlannedObjectKey.MODEL];
      const color = item[PlannedObjectKey.COLOR] ?? null;
      want(new Selection(MarkerKind.OBJECT, identifier), live.objects.get(identifier) ?? item[PlannedObjectKey.POSE], `${model}${color}`, false, () => this.#objectMarker(model, color, false));
    }
    for (const step of state.steps()) {
      for (const target of state.targets(step)) {
        const selection = new Selection(MarkerKind.TARGET, step[PlanStepKey.IDENTIFIER], target.field);
        const putDown = state.objects().find((item) => item[PlannedObjectKey.IDENTIFIER] === target.object);
        if (!putDown) {
          want(selection, target.pose, MarkerKind.TARGET, false, () => this.#targetMarker());
          continue;
        }
        const model = putDown[PlannedObjectKey.MODEL];
        want(selection, target.pose, model, false, () => this.#objectMarker(model, null, true));
      }
    }
    for (const [key, marker] of this.#byKey) {
      if (wanted.get(key)?.signature === marker.userData.signature) continue;
      this.#markers.remove(marker);
      this.#byKey.delete(key);
    }
    for (const [key, entry] of wanted) {
      if (!this.#byKey.has(key)) {
        const marker = entry.build();
        marker.userData[SELECTION_DATA] = entry.selection;
        marker.userData.signature = entry.signature;
        marker.userData.grounded = entry.grounded;
        this.#byKey.set(key, marker);
        this.#markers.add(marker);
      }
      const marker = this.#byKey.get(key);
      if (!(this.#handles.dragging && this.#handles.object === marker)) this.#pose(marker, entry.pose);
    }
    this.select(this.#selection && this.#byKey.has(this.#selection.key) ? this.#selection : null);
    this.#view.requestRender();
  }

  /**
   * @param {Selection|null} selection The marker to put the handles on, or null.
   */
  select(selection) {
    this.#selection = selection;
    const marker = selection && this.#byKey.get(selection.key);
    if (!marker) {
      this.#handles.detach();
      this.#view.requestRender();
      return;
    }
    if (this.#handles.object !== marker) this.#handles.attach(marker);
    this.#applyMode();
  }

  /**
   * @param {string} mode A `TransformMode` value.
   */
  setMode(mode) {
    this.#mode = mode;
    this.#applyMode();
  }

  /**
   * Look at the shown environment, or at the markers on an empty floor.
   */
  frame() {
    const bounds = this.#view.contentBounds() ?? this.#markerBounds() ?? FLOOR_REGION;
    this.#view.frame(bounds);
  }

  /**
   * Look at the plan's markers.
   */
  frameMarkers() {
    this.#view.frame(this.#markerBounds() ?? FLOOR_REGION);
  }

  /**
   * Stop rendering and release the view, the handles and the environment.
   */
  dispose() {
    this.#loading?.abort();
    this.#environment?.dispose();
    for (const [type, listener] of this.#canvasListeners) this.#view.renderer.domElement.removeEventListener(type, listener);
    this.#handles.detach();
    this.#handles.dispose();
    this.#view.dispose();
  }

  // %% markers

  /**
   * @param {number} color The disc's colour.
   * @param {string} label The robot's name.
   * @param {boolean} edited Whether its plan is the one edited.
   * @returns {THREE.Group} A robot: a disc with an arrow along its heading and its name
   *   above it.
   */
  #robotMarker(color, label, edited) {
    const material = new THREE.MeshStandardMaterial({ color });
    const disc = new THREE.Mesh(new THREE.CylinderGeometry(MarkerSize.ROBOT_RADIUS, MarkerSize.ROBOT_RADIUS, MarkerSize.ROBOT_HEIGHT, SEGMENTS), material);
    disc.rotation.x = Math.PI / 2;
    disc.position.z = MarkerSize.ROBOT_HEIGHT / 2;
    const arrow = this.#arrow(material);
    arrow.position.z = MarkerSize.ROBOT_HEIGHT;
    const group = new THREE.Group();
    group.add(disc, arrow, this.#nameLabel(label, edited));
    return group;
  }

  /**
   * @param {string} text A robot's name.
   * @param {boolean} edited Whether its plan is the one edited.
   * @returns {THREE.Sprite} The name, facing the camera and drawn over the environment
   *   so a robot inside furniture is still named.
   */
  #nameLabel(text, edited) {
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    context.font = RobotLabel.FONT;
    canvas.width = Math.ceil(context.measureText(text).width) + 2 * RobotLabel.PADDING;
    canvas.height = RobotLabel.FONT_SIZE + 2 * RobotLabel.PADDING;
    context.font = RobotLabel.FONT;
    context.fillStyle = edited ? RobotLabel.EDITED_BACKGROUND : RobotLabel.BACKGROUND;
    context.beginPath();
    context.roundRect(0, 0, canvas.width, canvas.height, canvas.height / 2);
    context.fill();
    context.fillStyle = RobotLabel.TEXT;
    context.textBaseline = 'middle';
    context.fillText(text, RobotLabel.PADDING, canvas.height / 2);
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, depthTest: false, transparent: true, sizeAttenuation: false }));
    sprite.renderOrder = 1;
    sprite.scale.set((LABEL_SCREEN_HEIGHT * canvas.width) / canvas.height, LABEL_SCREEN_HEIGHT, 1);
    sprite.position.z = MarkerSize.LABEL_LIFT;
    return sprite;
  }

  /**
   * @returns {THREE.Group} A pose target: a ring with an arrow along the heading.
   */
  #targetMarker() {
    const material = new THREE.MeshStandardMaterial({ color: MarkerColor.TARGET });
    const ring = new THREE.Mesh(new THREE.TorusGeometry(MarkerSize.TARGET_RADIUS, MarkerSize.TARGET_TUBE, SEGMENTS / 2, SEGMENTS), material);
    ring.position.z = MarkerSize.TARGET_TUBE;
    const group = new THREE.Group();
    group.add(ring, this.#arrow(material));
    return group;
  }

  /**
   * @param {THREE.Material} material The arrow's material.
   * @returns {THREE.Mesh} An arrow head pointing along x.
   */
  #arrow(material) {
    const arrow = new THREE.Mesh(new THREE.ConeGeometry(MarkerSize.ARROW_RADIUS, MarkerSize.ARROW_LENGTH, SEGMENTS), material);
    arrow.rotation.z = -Math.PI / 2;
    arrow.position.x = MarkerSize.ROBOT_RADIUS;
    return arrow;
  }

  /**
   * @param {string} model The object model's identifier.
   * @param {string|null} color The object's colour, or null for the default.
   * @param {boolean} ghost Whether the marker is a see-through put-down target.
   * @returns {THREE.Group} The object, a small box until its mesh is loaded.
   */
  #objectMarker(model, color, ghost) {
    const material = new THREE.MeshStandardMaterial({
      color: ghost ? MarkerColor.PUT_DOWN : (color ?? MarkerColor.OBJECT),
      transparent: ghost,
      opacity: ghost ? TARGET_OPACITY : 1,
    });
    const group = new THREE.Group();
    const placeholder = new THREE.Mesh(new THREE.BoxGeometry(MarkerSize.PLACEHOLDER, MarkerSize.PLACEHOLDER, MarkerSize.PLACEHOLDER), material);
    group.add(placeholder);
    this.#mesh(model)
      .then((mesh) => {
        const copy = mesh.clone();
        copy.traverse((child) => {
          if (child.isMesh) {
            child.material = material;
            child.castShadow = !ghost;
          }
        });
        group.remove(placeholder);
        group.add(copy);
        this.#view.requestRender();
      })
      .catch((error) => this.#listeners.onError(error));
    return group;
  }

  /**
   * @param {string} model An object model's identifier.
   * @returns {Promise<THREE.Object3D>} Its mesh, or a library model's links as its URDF
   *   describes them at rest, loaded once.
   */
  #mesh(model) {
    if (!this.#meshes.has(model)) {
      const manager = new THREE.LoadingManager();
      const loading = new MeshLoading(manager, () => {});
      const url = this.#objectUrl(model);
      this.#meshes.set(model, model.toLowerCase().endsWith(DESCRIPTION_SUFFIX) ? PlanScene.#described(url, manager, loading) : loading.load(url));
    }
    return this.#meshes.get(model);
  }

  /**
   * @param {string} url A library model's URDF.
   * @param {THREE.LoadingManager} manager Tracks the loader's requests.
   * @param {MeshLoading} loading Loads the meshes the URDF names.
   * @returns {Promise<THREE.Object3D>} The model's links, once every mesh they name
   *   arrived: the loader hands the links over before, and markers copy them.
   */
  static #described(url, manager, loading) {
    const meshesLoaded = new Promise((resolve) => {
      manager.onLoad = resolve;
    });
    const loader = new URDFLoader(manager);
    loader.parseCollision = false;
    loader.loadMeshCb = (meshUrl, _manager, material, done) => {
      loading.load(meshUrl, material).then((mesh) => done(mesh), (error) => done(null, error));
    };
    return loader.loadAsync(url).then((model) => meshesLoaded.then(() => model));
  }

  /**
   * @param {THREE.Object3D} marker A marker.
   * @param {Array<number>} pose Its pose.
   */
  #pose(marker, pose) {
    marker.position.set(...PlanPose.position(pose));
    marker.quaternion.set(...PlanPose.orientation(pose));
  }

  /**
   * @returns {Bounds|null} The box around the markers, or null without any.
   */
  #markerBounds() {
    const box = new THREE.Box3().setFromObject(this.#markers);
    return box.isEmpty() ? null : new Bounds(box.min.toArray(), box.max.toArray());
  }

  /**
   * Light an empty floor and look at it.
   */
  #showFloor() {
    this.#lighting.showStudio(this.#view.renderer, this.#view.scene, FLOOR_REGION);
    this.#view.frame(FLOOR_REGION);
  }

  // %% handles

  /**
   * Let the handles move or turn the selection; robots stay on the floor, and every
   * marker turns about the vertical only.
   */
  #applyMode() {
    const grounded = this.#handles.object?.userData.grounded ?? true;
    this.#handles.setMode(this.#mode);
    this.#handles.showX = this.#mode === TransformMode.MOVE;
    this.#handles.showY = this.#mode === TransformMode.MOVE;
    this.#handles.showZ = this.#mode === TransformMode.TURN || !grounded;
    this.#view.requestRender();
  }

  /**
   * Report the dragged marker's new pose.
   */
  #placed() {
    const marker = this.#handles.object;
    if (!marker || !this.#selection) return;
    const pose = [...marker.position.toArray(), ...marker.quaternion.toArray()].map(PlanPose.rounded);
    this.#listeners.onPlace(this.#selection, pose);
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
   * Select the marker a click hits, or nothing for a click beside every marker.
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
    ray.setFromCamera(pointer, this.#view.camera);
    const hit = ray.intersectObjects([...this.#byKey.values()], true)[0];
    let current = hit?.object ?? null;
    while (current && current.userData[SELECTION_DATA] === undefined) current = current.parent;
    const selection = current ? current.userData[SELECTION_DATA] : null;
    this.select(selection);
    this.#listeners.onPick(selection);
  }
}
