/**
 * Pulling an object of the simulation with the pointer: Shift and drag on a free object
 * pulls it across the horizontal plane it was grabbed at, through the same bounded
 * spring the panel's buttons use; letting go of the pointer lets go of the object.
 */

import * as THREE from 'three';

/**
 * The shortest time between two pull requests while dragging, in milliseconds.
 */
export const PULL_INTERVAL = 50;

/**
 * The pointer button that drags.
 */
const PRIMARY_BUTTON = 0;

/**
 * The pointer events the gesture listens to.
 */
const PointerEvent = Object.freeze({ DOWN: 'pointerdown', MOVE: 'pointermove', UP: 'pointerup' });

// %% geometry

/**
 * @param {Array<number>} origin Where the grabbed object's origin was when grabbed.
 * @param {THREE.Vector3} grab Where the pointer grabbed it.
 * @param {THREE.Vector3} pointer Where the pointer is now on the grab plane.
 * @returns {Array<number>} The pull target: the origin moved as far as the pointer moved.
 */
export function pullTarget(origin, grab, pointer) {
  return [origin[0] + pointer.x - grab.x, origin[1] + pointer.y - grab.y, origin[2] + pointer.z - grab.z];
}

/**
 * @param {THREE.Object3D} object A part of a scene object.
 * @returns {string|null} The key of the scene object it belongs to, or null.
 */
export function objectKeyOf(object) {
  for (let current = object; current; current = current.parent) {
    if (current.userData?.objectKey !== undefined) return current.userData.objectKey;
  }
  return null;
}

// %% gesture

export class PullGesture {
  /**
   * The element the pointer moves over.
   * @type {HTMLElement}
   */
  #element;

  /**
   * The view's camera.
   * @type {THREE.Camera}
   */
  #camera;

  /**
   * The view's orbit controls, paused while dragging.
   * @type {{enabled: boolean}}
   */
  #controls;

  /**
   * Pulls an object to a target.
   * @type {function(string, Array<number>): Promise<*>}
   */
  #pull;

  /**
   * Lets go of the pulled object.
   * @type {function(): Promise<*>}
   */
  #release;

  /**
   * The scene's free objects, while a simulation is shown.
   * @type {THREE.Object3D|null}
   */
  #objects = null;

  /**
   * The keys of the objects that may be pulled.
   * @type {Set<string>}
   */
  #pullable = new Set();

  /**
   * The drag in progress: the object, its origin, the grab point and plane.
   * @type {{key: string, origin: Array<number>, grab: THREE.Vector3, plane: THREE.Plane}|null}
   */
  drag = null;

  /**
   * When the last pull request was sent, in milliseconds.
   * @type {number}
   */
  #lastPull = -Infinity;

  /**
   * Gives the time in milliseconds.
   * @type {function(): number}
   */
  #now;

  /**
   * The listeners, for removal.
   * @type {Array<[string, function(PointerEvent): void]>}
   */
  #listeners;

  /**
   * @param {HTMLElement} element The element the pointer moves over.
   * @param {THREE.Camera} camera The view's camera.
   * @param {{enabled: boolean}} controls The view's orbit controls.
   * @param {function(string, Array<number>): Promise<*>} pull Pulls an object to a target.
   * @param {function(): Promise<*>} release Lets go of the pulled object.
   * @param {function(): number=} now Gives the time in milliseconds.
   */
  constructor(element, camera, controls, pull, release, now = () => performance.now()) {
    this.#element = element;
    this.#camera = camera;
    this.#controls = controls;
    this.#pull = pull;
    this.#release = release;
    this.#now = now;
    this.#listeners = [
      [PointerEvent.DOWN, (event) => this.grab(event)],
      [PointerEvent.MOVE, (event) => this.move(event)],
      [PointerEvent.UP, () => this.letGo()],
    ];
    for (const [type, listener] of this.#listeners) element.addEventListener(type, listener);
  }

  /**
   * Let the objects of a shown simulation be pulled.
   * @param {THREE.Object3D} objects The scene's free objects.
   * @param {Array<string>} keys The keys of the objects that may be pulled.
   */
  attach(objects, keys) {
    this.#objects = objects;
    this.#pullable = new Set(keys);
  }

  /**
   * Stop letting objects be pulled.
   */
  detach() {
    this.#objects = null;
    this.#pullable = new Set();
    this.drag = null;
    this.#controls.enabled = true;
  }

  /**
   * @param {PointerEvent} event A pointer event over the element.
   * @returns {THREE.Raycaster} A ray from the camera through the pointer.
   */
  #ray(event) {
    const bounds = this.#element.getBoundingClientRect();
    const pointer = new THREE.Vector2(
      ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
      -((event.clientY - bounds.top) / bounds.height) * 2 + 1,
    );
    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(pointer, this.#camera);
    return raycaster;
  }

  /**
   * Start dragging the pullable object under the pointer, if Shift is held.
   * @param {PointerEvent} event The pointer pressed.
   */
  grab(event) {
    if (!this.#objects || !event.shiftKey || event.button !== PRIMARY_BUTTON) return;
    const hits = this.#ray(event).intersectObject(this.#objects, true);
    const hit = hits.find((candidate) => this.#pullable.has(objectKeyOf(candidate.object)));
    if (!hit) return;
    const key = objectKeyOf(hit.object);
    let holder = hit.object;
    while (holder.userData?.objectKey !== key) holder = holder.parent;
    const origin = holder.getWorldPosition(new THREE.Vector3()).toArray();
    this.drag = { key, origin, grab: hit.point.clone(), plane: new THREE.Plane(new THREE.Vector3(0, 0, 1), -hit.point.z) };
    this.#controls.enabled = false;
    event.preventDefault();
  }

  /**
   * Pull the dragged object after the pointer, at most once per interval.
   * @param {PointerEvent} event The pointer moved.
   */
  move(event) {
    if (!this.drag) return;
    const now = this.#now();
    if (now - this.#lastPull < PULL_INTERVAL) return;
    const point = this.#ray(event).ray.intersectPlane(this.drag.plane, new THREE.Vector3());
    if (!point) return;
    this.#lastPull = now;
    this.#pull(this.drag.key, pullTarget(this.drag.origin, this.drag.grab, point));
  }

  /**
   * Let go of the dragged object.
   */
  letGo() {
    if (!this.drag) return;
    this.drag = null;
    this.#controls.enabled = true;
    this.#release();
  }

  /**
   * Remove the listeners.
   */
  dispose() {
    this.detach();
    for (const [type, listener] of this.#listeners) this.#element.removeEventListener(type, listener);
  }
}
