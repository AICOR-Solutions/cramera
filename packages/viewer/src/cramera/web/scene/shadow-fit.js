/**
 * Fitting the key light's shadow camera to the region that must receive shadows.
 */

import * as THREE from 'three';

/**
 * The size of the vertical component of a unit direction from which a light counts
 * as straight above.
 */
const VERTICAL = 0.999;

/**
 * Metres the shadow camera reaches past the region on every side, so geometry on its
 * faces still casts.
 */
export const SHADOW_MARGIN = 0.05;

// %% errors

/**
 * A light direction without a length.
 */
export class DirectionWithoutLength extends Error {
  /**
   * @param {Array<number>} direction The direction.
   */
  constructor(direction) {
    super(`A light direction needs a length, got [${direction}].`);
    /**
     * The direction.
     * @type {Array<number>}
     */
    this.direction = direction;
  }
}

// %% fit

export class ShadowFit {
  /**
   * @param {import('./bounds.js').Bounds} bounds The region that must receive shadows.
   * @param {Array<number>} direction The way the light travels.
   * @throws {DirectionWithoutLength} For a zero direction.
   */
  constructor(bounds, direction) {
    if (!direction.some((value) => value !== 0)) throw new DirectionWithoutLength(direction);
    /**
     * The region that must receive shadows.
     * @type {import('./bounds.js').Bounds}
     */
    this.bounds = bounds;
    /**
     * The way the light travels.
     * @type {Array<number>}
     */
    this.direction = direction;
  }

  /**
   * @returns {{position: THREE.Vector3, target: THREE.Vector3, up: THREE.Vector3, left: number, right: number, top: number, bottom: number, near: number, far: number}}
   *   The light placement and the shadow camera that just encloses the region.
   */
  frustum() {
    const target = new THREE.Vector3(...this.bounds.center());
    const travel = new THREE.Vector3(...this.direction).normalize();
    const reach = Math.hypot(...this.bounds.size()) / 2 + SHADOW_MARGIN;
    const position = target.clone().addScaledVector(travel, -reach);
    const up = Math.abs(travel.z) > VERTICAL ? new THREE.Vector3(0, 1, 0) : new THREE.Vector3(0, 0, 1);
    const camera = new THREE.OrthographicCamera();
    camera.up.copy(up);
    camera.position.copy(position);
    camera.lookAt(target);
    camera.updateMatrixWorld();
    const seen = new THREE.Box3().setFromPoints(
      this.bounds.corners().map((corner) => new THREE.Vector3(...corner).applyMatrix4(camera.matrixWorldInverse)),
    );
    return {
      position,
      target,
      up,
      left: seen.min.x - SHADOW_MARGIN,
      right: seen.max.x + SHADOW_MARGIN,
      bottom: seen.min.y - SHADOW_MARGIN,
      top: seen.max.y + SHADOW_MARGIN,
      near: Math.max(0, -seen.max.z - SHADOW_MARGIN),
      far: -seen.min.z + SHADOW_MARGIN,
    };
  }

  /**
   * Aim a directional light at the region and fit its shadow camera to it.
   * @param {THREE.DirectionalLight} light The light.
   */
  applyTo(light) {
    const frustum = this.frustum();
    light.position.copy(frustum.position);
    light.target.position.copy(frustum.target);
    light.target.updateMatrixWorld();
    const camera = light.shadow.camera;
    camera.up.copy(frustum.up);
    Object.assign(camera, {
      left: frustum.left,
      right: frustum.right,
      top: frustum.top,
      bottom: frustum.bottom,
      near: frustum.near,
      far: frustum.far,
    });
    camera.updateProjectionMatrix();
  }
}
