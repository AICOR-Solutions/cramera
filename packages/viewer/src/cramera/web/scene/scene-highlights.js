/**
 * Lighting up the links and free objects an answer names, with a box around each.
 */

import * as THREE from 'three';

import { ownBounds } from './scene-picking.js';

/**
 * The colour of the boxes around highlighted links and objects.
 */
const HIGHLIGHT_COLOR = 0xf59e0b;

// %% matching

/**
 * @param {THREE.Object3D} content The shown scene's models and objects.
 * @param {Array<string>} keys Link names and free-object keys.
 * @returns {Array<THREE.Object3D>} The links and object holders those keys name.
 */
export function highlightedParts(content, keys) {
  const wanted = new Set(keys);
  const parts = [];
  content.traverse((object) => {
    const key = object.userData?.objectKey ?? (object.isURDFLink ? object.urdfName : undefined);
    if (key !== undefined && wanted.has(key)) parts.push(object);
  });
  return parts;
}

// %% highlights

export class SceneHighlights {
  /**
   * The view the boxes are drawn in.
   * @type {import('./scene-view.js').SceneView}
   */
  #view;

  /**
   * The highlighted parts with their boxes.
   * @type {Array<{part: THREE.Object3D, box: THREE.Box3Helper}>}
   */
  #highlights = [];

  /**
   * @param {import('./scene-view.js').SceneView} view The view the boxes are drawn in.
   */
  constructor(view) {
    this.#view = view;
  }

  /**
   * Highlight what the keys name, replacing earlier highlights.
   * @param {Array<string>} keys Link names and free-object keys; empty clears.
   * @returns {number} How many parts are highlighted.
   */
  show(keys) {
    this.clear();
    for (const part of highlightedParts(this.#view.content, keys)) {
      const box = new THREE.Box3Helper(ownBounds(part), HIGHLIGHT_COLOR);
      this.#view.scene.add(box);
      this.#highlights.push({ part, box });
    }
    this.#view.requestRender();
    return this.#highlights.length;
  }

  /**
   * Keep each box around its part as the parts move.
   */
  update() {
    for (const { part, box } of this.#highlights) box.box.copy(ownBounds(part));
  }

  /**
   * Remove every highlight.
   */
  clear() {
    for (const { box } of this.#highlights) {
      box.removeFromParent();
      box.dispose();
    }
    this.#highlights = [];
    this.#view.requestRender();
  }
}
