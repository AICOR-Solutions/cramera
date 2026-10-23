/**
 * Axis triads on every link of the scene's models and on every free object: red X,
 * green Y, blue Z.
 */

import * as THREE from 'three';

/**
 * The length of each axis, in metres.
 */
const AXIS_LENGTH = 0.1;

// %% axes

export class FrameAxes {
  /**
   * The triads, one per frame.
   * @type {Array<THREE.AxesHelper>}
   */
  #triads = [];

  /**
   * Whether the triads are shown.
   * @type {boolean}
   */
  #shown = false;

  /**
   * The 3D view.
   * @type {import('./scene-view.js').SceneView}
   */
  #view;

  /**
   * @param {import('./scene-view.js').SceneView} view The 3D view.
   */
  constructor(view) {
    this.#view = view;
  }

  /**
   * @returns {boolean} Whether the triads are shown.
   */
  get shown() {
    return this.#shown;
  }

  /**
   * Put triads on a scene's frames, replacing those of the previous scene.
   * @param {Array<THREE.Object3D>} frames The frames.
   */
  show(frames) {
    for (const triad of this.#triads) {
      triad.removeFromParent();
      triad.dispose();
    }
    this.#triads = frames.map((frame) => {
      const triad = new THREE.AxesHelper(AXIS_LENGTH);
      triad.visible = this.#shown;
      frame.add(triad);
      return triad;
    });
    this.#view.requestRender();
  }

  /**
   * @param {boolean} shown Whether to show the triads.
   */
  setShown(shown) {
    this.#shown = shown;
    for (const triad of this.#triads) triad.visible = shown;
    this.#view.requestRender();
  }
}

/**
 * @param {import('./scene-loader.js').LoadedScene} scene A loaded scene.
 * @returns {Array<THREE.Object3D>} The links of its models and the frames of its free
 *   objects.
 */
export function framesOf(scene) {
  const links = scene.models.names().flatMap((name) => Object.values(scene.models.model(name).links ?? {}));
  const objects = scene.objects.named().map(({ key }) => scene.objects.holderOf(key));
  return [...links, ...objects];
}
