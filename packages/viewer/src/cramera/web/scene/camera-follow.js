/**
 * Keeps the robot in view: while it is on, the camera moves by as much as the robot
 * moved, so the view the person chose travels with the robot.
 */

import * as THREE from 'three';

// %% follow

export class CameraFollow {
  /**
   * The 3D view.
   * @type {import('./scene-view.js').SceneView}
   */
  #view;

  /**
   * Where the robot stood when last followed, or null.
   * @type {THREE.Vector3|null}
   */
  #previous = null;

  /**
   * Whether the camera follows the robot.
   * @type {boolean}
   */
  following = true;

  /**
   * @param {import('./scene-view.js').SceneView} view The 3D view.
   */
  constructor(view) {
    this.#view = view;
  }

  /**
   * Forget the robot's position, as after another scene was loaded.
   * @param {THREE.Vector3|null} position Where the robot of the new scene stands.
   */
  reset(position) {
    this.#previous = position?.clone() ?? null;
  }

  /**
   * Move the camera with the robot.
   * @param {THREE.Vector3|null} position Where the robot stands now, or null.
   */
  follow(position) {
    if (!position) return;
    if (this.following && this.#previous) {
      const moved = new THREE.Vector3().subVectors(position, this.#previous);
      if (moved.lengthSq() > 0) {
        this.#view.camera.position.add(moved);
        this.#view.controls.target.add(moved);
        this.#view.requestRender();
      }
    }
    this.#previous = position.clone();
  }
}
