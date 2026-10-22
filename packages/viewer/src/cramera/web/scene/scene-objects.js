/**
 * The free objects of a scene: drawn from their mesh or as a box, posed per frame.
 */

import * as THREE from 'three';

import { ObjectKey } from '../protocol.js';
import { MeshLoading } from './mesh-loading.js';
import { applyPose } from './poses.js';

// %% objects

export class SceneObjects {
  /**
   * The object groups by trajectory key.
   * @type {Map<string, THREE.Group>}
   */
  #objects = new Map();

  /**
   * The objects whose mesh could not be loaded, with the reason.
   * @type {Array<{url: string, reason: string}>}
   */
  #meshFailures = [];

  /**
   * The group holding every object.
   * @type {THREE.Group}
   */
  group = new THREE.Group();

  /**
   * Load every object of a scene and place it at its spawn pose.
   * @param {Array<Object>} descriptions The scene's object descriptions.
   * @param {function(string): string} fileUrl The URL of a bundle file.
   * @param {THREE.LoadingManager} manager Tracks the loaders' requests.
   * @returns {Promise<SceneObjects>} This object, once every object is loaded or has failed.
   */
  async load(descriptions, fileUrl, manager) {
    const meshes = new MeshLoading(manager, (url, reason) => this.#meshFailures.push({ url, reason }));
    await Promise.all(descriptions.map((description) => this.#loadObject(description, fileUrl, meshes)));
    return this;
  }

  /**
   * @param {Object} description An object description.
   * @param {function(string): string} fileUrl The URL of a bundle file.
   * @param {MeshLoading} meshes Loads the mesh.
   */
  async #loadObject(description, fileUrl, meshes) {
    const holder = new THREE.Group();
    holder.name = description[ObjectKey.IDENTIFIER];
    holder.userData.objectKey = description[ObjectKey.KEY];
    applyPose(holder, description[ObjectKey.SPAWN]);
    this.#objects.set(description[ObjectKey.KEY], holder);
    this.group.add(holder);
    const shape = await this.#shapeOf(description, fileUrl, meshes);
    if (!shape) return;
    shape.traverse((child) => {
      child.castShadow = true;
      child.receiveShadow = true;
    });
    holder.add(shape);
  }

  /**
   * @param {Object} description An object description.
   * @param {function(string): string} fileUrl The URL of a bundle file.
   * @param {MeshLoading} meshes Loads the mesh.
   * @returns {Promise<THREE.Object3D|null>} The object's shape, or null for an object
   *   without one or with a mesh that failed.
   */
  async #shapeOf(description, fileUrl, meshes) {
    const material = this.#materialOf(description);
    const box = description[ObjectKey.BOX];
    if (box) return new THREE.Mesh(new THREE.BoxGeometry(...box), material);
    const mesh = description[ObjectKey.MESH];
    if (!mesh) return null;
    const url = fileUrl(mesh);
    return meshes.load(url, material).then(
      (shape) => shape,
      (error) => {
        this.#meshFailures.push({ url, reason: String(error.message ?? error) });
        return null;
      },
    );
  }

  /**
   * @param {Object} description An object description.
   * @returns {THREE.Material|undefined} The object's colour as a material, or undefined
   *   when its mesh keeps its own materials or it has no colour.
   */
  #materialOf(description) {
    const color = description[ObjectKey.COLOR];
    if (description[ObjectKey.PRESERVE_MATERIALS] || !color) return undefined;
    return new THREE.MeshStandardMaterial({ color: new THREE.Color(color) });
  }

  /**
   * @returns {Array<{url: string, reason: string}>} The meshes that could not be loaded.
   */
  meshFailures() {
    return [...this.#meshFailures];
  }

  /**
   * @param {Map<string, Array<number>>} poses The poses of the objects that moved.
   */
  setPoses(poses) {
    for (const [key, pose] of poses) {
      const holder = this.#objects.get(key);
      if (holder) applyPose(holder, pose);
    }
  }

  /**
   * @returns {Array<string>} The trajectory keys of the objects.
   */
  keys() {
    return [...this.#objects.keys()];
  }

  /**
   * Free every geometry and material.
   */
  dispose() {
    this.group.traverse((child) => {
      child.geometry?.dispose();
      for (const material of [child.material].flat().filter(Boolean)) material.dispose();
    });
    this.group.removeFromParent();
    this.#objects.clear();
  }
}
