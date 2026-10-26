/**
 * Drawing the regions an answer is about as boxes, and gliding the camera onto what an
 * answer is about.
 */

import * as THREE from 'three';

import { RegionOutlineKey } from '../protocol.js';
import { highlightedParts } from './scene-highlights.js';
import { ownBounds } from './scene-picking.js';

/**
 * How a region's box is drawn: a see-through fill with bright edges.
 */
export const RegionStyle = Object.freeze({ FILL: 0x39d5c8, EDGES: 0x9ffff6, OPACITY: 0.42 });

/**
 * How the camera glides onto what an answer is about.
 */
export const GlideSetting = Object.freeze({
  /**
   * How long a glide takes unless the request says otherwise, in seconds.
   */
  SECONDS: 1.1,
  /**
   * How near the camera comes at least, in metres.
   */
  NEAREST: 0.32,
  /**
   * How many times the extent of what it glides onto the camera stays away.
   */
  SPAN: 2.6,
});

// %% regions

export class RegionOutlines {
  /**
   * The view the boxes are drawn in.
   * @type {import('./scene-view.js').SceneView}
   */
  #view;

  /**
   * The boxes drawn, each named by its region.
   * @type {THREE.Group}
   */
  group = new THREE.Group();

  /**
   * @param {import('./scene-view.js').SceneView} view The view the boxes are drawn in.
   */
  constructor(view) {
    this.#view = view;
    view.scene.add(this.group);
  }

  /**
   * Draw the regions as boxes, replacing the boxes drawn before.
   * @param {Array<Object>} outlines Region outlines; empty clears.
   */
  show(outlines) {
    this.clear();
    for (const outline of outlines) {
      const holder = new THREE.Group();
      holder.name = outline[RegionOutlineKey.IDENTIFIER];
      const pose = outline[RegionOutlineKey.POSE];
      holder.position.set(pose[0], pose[1], pose[2]);
      holder.quaternion.set(pose[3], pose[4], pose[5], pose[6]);
      const geometry = new THREE.BoxGeometry(...outline[RegionOutlineKey.SIZE]);
      holder.add(
        new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ color: RegionStyle.FILL, transparent: true, opacity: RegionStyle.OPACITY, depthWrite: false })),
        new THREE.LineSegments(new THREE.EdgesGeometry(geometry), new THREE.LineBasicMaterial({ color: RegionStyle.EDGES })),
      );
      this.group.add(holder);
    }
    this.#view.requestRender();
  }

  /**
   * Remove every box.
   */
  clear() {
    for (const holder of [...this.group.children]) {
      holder.removeFromParent();
      holder.traverse((part) => {
        part.geometry?.dispose();
        part.material?.dispose();
      });
    }
    this.#view.requestRender();
  }
}

// %% gliding

/**
 * @param {number} progress How far a glide has come, from 0 to 1.
 * @returns {number} How far the camera has moved, eased in and out.
 */
export function easedProgress(progress) {
  return progress < 0.5 ? 4 * progress ** 3 : 1 - (-2 * progress + 2) ** 3 / 2;
}

/**
 * @param {THREE.Object3D} content The shown scene's models and objects.
 * @param {THREE.Object3D} regions The drawn region boxes.
 * @param {Array<string>} keys Link names, free-object keys and region names.
 * @returns {THREE.Box3} The box around what the keys name; empty when they name nothing.
 */
export function focusBounds(content, regions, keys) {
  const box = new THREE.Box3();
  const named = new Set(keys);
  for (const region of regions.children) if (named.has(region.name)) box.expandByObject(region);
  for (const part of highlightedParts(content, keys)) box.union(ownBounds(part));
  return box;
}

export class CameraGlide {
  /**
   * The view whose camera glides.
   * @type {import('./scene-view.js').SceneView}
   */
  #view;

  /**
   * The glide under way, or null.
   * @type {{seconds: number, elapsed: number, fromTarget: THREE.Vector3, toTarget: THREE.Vector3, fromCamera: THREE.Vector3, toCamera: THREE.Vector3}|null}
   */
  #glide = null;

  /**
   * @param {import('./scene-view.js').SceneView} view The view whose camera glides.
   */
  constructor(view) {
    this.#view = view;
  }

  /**
   * Start gliding, keeping the direction the camera looks from, until the box fills the
   * view.
   * @param {THREE.Box3} box What the camera glides onto.
   * @param {number} seconds How long the glide takes.
   * @returns {boolean} Whether a glide started; an empty box starts none.
   */
  glideTo(box, seconds = GlideSetting.SECONDS) {
    if (box.isEmpty()) return false;
    const { camera, controls } = this.#view;
    const center = box.getCenter(new THREE.Vector3());
    const distance = Math.max(GlideSetting.NEAREST, box.getSize(new THREE.Vector3()).length() * GlideSetting.SPAN);
    const direction = camera.position.clone().sub(controls.target).normalize();
    this.#glide = {
      seconds,
      elapsed: 0,
      fromTarget: controls.target.clone(),
      toTarget: center,
      fromCamera: camera.position.clone(),
      toCamera: center.clone().addScaledVector(direction, distance),
    };
    return true;
  }

  /**
   * @returns {boolean} Whether a glide is under way.
   */
  get gliding() {
    return this.#glide !== null;
  }

  /**
   * Move the camera on by the time that passed.
   * @param {number} seconds The seconds since the previous frame.
   * @returns {boolean} Whether the camera moved.
   */
  advance(seconds) {
    const glide = this.#glide;
    if (!glide) return false;
    glide.elapsed = Math.min(glide.seconds, glide.elapsed + seconds);
    const eased = easedProgress(glide.seconds > 0 ? glide.elapsed / glide.seconds : 1);
    this.#view.lookFrom(
      new THREE.Vector3().lerpVectors(glide.fromCamera, glide.toCamera, eased),
      new THREE.Vector3().lerpVectors(glide.fromTarget, glide.toTarget, eased),
    );
    if (glide.elapsed >= glide.seconds) this.#glide = null;
    return true;
  }
}
