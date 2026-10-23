/**
 * The names of the scene's free objects, drawn as page elements over the 3D view and
 * moved with the camera after every rendered frame.
 */

import * as THREE from 'three';

/**
 * How far above an object's frame its label sits, in metres.
 */
const LABEL_HEIGHT = 0.12;

// %% labels

export class ObjectLabels {
  /**
   * The element holding the labels, over the 3D view.
   * @type {HTMLElement}
   */
  element;

  /**
   * The labels with the frames they follow.
   * @type {Array<{label: HTMLElement, frame: THREE.Object3D}>}
   */
  #labels = [];

  /**
   * Whether the labels are shown.
   * @type {boolean}
   */
  #shown = false;

  /**
   * The 3D view.
   * @type {import('./scene-view.js').SceneView}
   */
  #view;

  /**
   * @param {HTMLElement} stage The 3D view's container.
   * @param {import('./scene-view.js').SceneView} view The 3D view.
   */
  constructor(stage, view) {
    this.#view = view;
    this.element = stage.ownerDocument.createElement('div');
    this.element.className = 'object-labels';
    this.element.setAttribute('aria-hidden', 'true');
    stage.append(this.element);
    view.onRender(() => this.update());
    this.setShown(false);
  }

  /**
   * @returns {boolean} Whether the labels are shown.
   */
  get shown() {
    return this.#shown;
  }

  /**
   * @param {boolean} shown Whether to show the labels.
   */
  setShown(shown) {
    this.#shown = shown;
    this.element.hidden = !shown;
    this.#view.requestRender();
  }

  /**
   * Label a scene's objects.
   * @param {Array<{name: string, frame: THREE.Object3D}>} objects The objects.
   */
  show(objects) {
    const document = this.element.ownerDocument;
    this.#labels = objects.map(({ name, frame }) => {
      const label = document.createElement('span');
      label.className = 'object-label';
      label.textContent = name;
      return { label, frame };
    });
    this.element.replaceChildren(...this.#labels.map(({ label }) => label));
    this.#view.requestRender();
  }

  /**
   * Put each label over its object as the camera sees it; labels behind the camera
   * are hidden.
   */
  update() {
    if (!this.#shown) return;
    const { width, height } = this.#view.size;
    const point = new THREE.Vector3();
    for (const { label, frame } of this.#labels) {
      frame.getWorldPosition(point);
      point.z += LABEL_HEIGHT;
      point.project(this.#view.camera);
      label.hidden = point.z > 1 || point.z < -1;
      label.style.left = `${((point.x + 1) / 2) * width}px`;
      label.style.top = `${((1 - point.y) / 2) * height}px`;
    }
  }
}
