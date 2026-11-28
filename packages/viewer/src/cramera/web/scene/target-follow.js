/**
 * The camera following the running step's target: when the target changes, the camera
 * glides onto the mark from above, keeping the side it looks from, so it looks over the
 * robot into what the target sits in; while the mark moves with its body, the camera
 * moves with it as it does with the robot when following it.
 */

import * as THREE from 'three';

import { CameraFollow } from './camera-follow.js';

/**
 * The edge of the box around the mark the camera glides onto, in metres: wide enough
 * to show the gripper reaching the target and what the target sits in.
 */
export const TARGET_VIEW = 0.35;

/**
 * How steeply the camera looks down onto the target, in radians above the horizon.
 */
export const TARGET_ELEVATION = THREE.MathUtils.degToRad(55);

/**
 * @param {THREE.Vector3} looking The direction from the target to the camera now.
 * @param {THREE.Vector3} up The camera's up direction.
 * @returns {THREE.Vector3} The direction to look onto the target from: the same side,
 *   raised to {@link TARGET_ELEVATION}; from straight above when the camera looks
 *   straight down already.
 */
export function lookingDown(looking, up) {
  const level = looking.clone().addScaledVector(up, -looking.dot(up));
  if (level.lengthSq() < 1e-12) return up.clone();
  return level.normalize().multiplyScalar(Math.cos(TARGET_ELEVATION)).addScaledVector(up, Math.sin(TARGET_ELEVATION));
}

/**
 * @param {THREE.Object3D} mark The mark of the target.
 * @returns {THREE.Box3} The box the camera glides onto, centred on the mark.
 */
export function targetView(mark) {
  const center = mark.getWorldPosition(new THREE.Vector3());
  return new THREE.Box3().setFromCenterAndSize(center, new THREE.Vector3(TARGET_VIEW, TARGET_VIEW, TARGET_VIEW));
}

export class TargetFollow {
  /**
   * Whether the camera follows the target.
   * @type {boolean}
   */
  following = false;

  /**
   * The mark of the target.
   * @type {THREE.Object3D}
   */
  #mark;

  /**
   * Glides the camera onto the mark.
   * @type {{glideTo: function(THREE.Box3, number=, THREE.Vector3=): boolean, gliding: boolean}}
   */
  #glide;

  /**
   * Moves the camera with the mark.
   * @type {CameraFollow}
   */
  #follow;

  /**
   * The 3D view.
   * @type {import('./scene-view.js').SceneView}
   */
  #view;

  /**
   * @param {import('./scene-view.js').SceneView} view The 3D view.
   * @param {THREE.Object3D} mark The mark of the target.
   * @param {{glideTo: function(THREE.Box3, number=, THREE.Vector3=): boolean, gliding: boolean}} glide
   *   Glides the camera onto boxes.
   */
  constructor(view, mark, glide) {
    this.#view = view;
    this.#mark = mark;
    this.#glide = glide;
    this.#follow = new CameraFollow(view);
  }

  /**
   * @returns {THREE.Vector3|null} Where the mark is in the world, or null while it marks
   *   nothing.
   */
  #position() {
    return this.#mark.parent ? this.#mark.getWorldPosition(new THREE.Vector3()) : null;
  }

  /**
   * Glide onto the mark from above, which now marks a new target, while following it.
   * @returns {boolean} Whether the camera glides.
   */
  aim() {
    const position = this.#position();
    this.#follow.reset(position);
    if (!this.following || !position) return false;
    const { camera, controls } = this.#view;
    const looking = lookingDown(camera.position.clone().sub(controls.target), camera.up);
    return this.#glide.glideTo(targetView(this.#mark), undefined, looking);
  }

  /**
   * Move the camera with the mark, as the shown frame moved its body; while the camera
   * glides onto it, or while not following, only note where the mark is.
   */
  follow() {
    const position = this.#position();
    this.#follow.following = this.following && !this.#glide.gliding;
    this.#follow.follow(position);
    if (!position) this.#follow.reset(null);
  }

  /**
   * Note where the mark is without moving the camera, as when another camera takes over.
   */
  reset() {
    this.#follow.reset(this.#position());
  }
}
