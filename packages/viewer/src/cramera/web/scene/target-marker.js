/**
 * The mark in the 3D view where the running step of a plan acts: a small sphere with
 * the target's axes, attached to the body the target is given in, so it moves with
 * that body while the run plays, drawn over the geometry it may sit inside.
 */

import * as THREE from 'three';

import { highlightedParts } from './scene-highlights.js';

/**
 * The colour of the mark.
 */
export const TARGET_COLOR = 0xffb648;

/**
 * The sphere's radius, in metres.
 */
export const TARGET_RADIUS = 0.02;

/**
 * The length of the target's axes, in metres.
 */
export const TARGET_AXES = 0.1;

/**
 * The names of the frames the scene's content is given in, which a target given in
 * one of them is attached to when no link or object carries the name.
 */
export const WORLD_FRAMES = Object.freeze(['map', 'world_root', 'world']);

/**
 * @param {THREE.Object3D} content The scene's content.
 * @param {{keys: Array<string>, frame: string}} target A target.
 * @returns {THREE.Object3D|null} What the target is attached to: the link or the free
 *   object it is given in, the content for a world frame, else null.
 */
export function targetFrame(content, target) {
  const [part] = highlightedParts(content, target.keys ?? []);
  if (part) return part;
  return WORLD_FRAMES.includes(target.frame) ? content : null;
}

/**
 * @returns {THREE.Group} The mark, drawn over everything else; an overlay, which the
 *   highlights of the body it is attached to leave out.
 */
export function markObject() {
  const mark = new THREE.Group();
  mark.name = 'step-target';
  mark.userData.overlay = true;
  const sphere = new THREE.Mesh(
    new THREE.SphereGeometry(TARGET_RADIUS, 20, 14),
    new THREE.MeshBasicMaterial({ color: TARGET_COLOR, depthTest: false, transparent: true, opacity: 0.9 }),
  );
  const axes = new THREE.AxesHelper(TARGET_AXES);
  axes.material.depthTest = false;
  for (const part of [sphere, axes]) {
    part.renderOrder = 999;
    mark.add(part);
  }
  return mark;
}

export class TargetMarker {
  /**
   * The mark.
   * @type {THREE.Group}
   */
  mark = markObject();

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
   * Attach the mark to the body a target is given in, at the target's pose; a target
   * whose body the scene does not show, or none, takes the mark away.
   * @param {{keys: Array<string>, frame: string, pose: Array<number>|null, label: string}|null} target
   *   The target, or null.
   */
  show(target) {
    this.clear();
    const frame = target ? targetFrame(this.#view.content, target) : null;
    if (!frame) return;
    const [x, y, z, qx, qy, qz, qw] = target.pose ?? [0, 0, 0, 0, 0, 0, 1];
    this.mark.position.set(x, y, z);
    this.mark.quaternion.set(qx, qy, qz, qw);
    this.mark.userData.label = target.label;
    frame.add(this.mark);
  }

  /**
   * Take the mark away.
   */
  clear() {
    this.mark.removeFromParent();
  }
}
