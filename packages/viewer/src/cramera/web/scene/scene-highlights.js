/**
 * Lighting up the links and free objects an answer or a chosen node names: their meshes
 * glow, and one box surrounds the highlighted links of each model and each highlighted
 * free object.
 */

import * as THREE from 'three';

import { ownBounds } from './scene-picking.js';

/**
 * The colour of the glow and of the boxes around highlighted links and objects: a light
 * neon blue, apart from the teal box of the part clicked in the 3D view.
 */
export const HIGHLIGHT_COLOR = 0x00c8ff;

/**
 * How strongly a highlighted mesh glows in the highlight colour.
 */
export const GLOW_INTENSITY = 0.45;

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

/**
 * @param {Array<THREE.Object3D>} parts Highlighted links and object holders.
 * @returns {Array<Array<THREE.Object3D>>} The parts sharing a box: the links of each
 *   model together, each free object alone.
 */
export function boxedGroups(parts) {
  const groups = new Map();
  for (const part of parts) {
    let owner = part;
    while (part.isURDFLink && owner.parent && !owner.isURDFRobot) owner = owner.parent;
    const holder = owner.isURDFRobot ? owner : part;
    if (!groups.has(holder)) groups.set(holder, []);
    groups.get(holder).push(part);
  }
  return [...groups.values()];
}

/**
 * @param {THREE.Object3D} owner A link or a free object.
 * @returns {Array<THREE.Mesh>} Its own meshes; the links below a link are left out.
 */
export function ownMeshes(owner) {
  const meshes = [];
  const visit = (object) => {
    if (object !== owner && (object.isURDFLink || object.isURDFJoint)) return;
    if (object.isMesh) meshes.push(object);
    object.children.forEach(visit);
  };
  visit(owner);
  return meshes;
}

/**
 * @param {THREE.Material} material A mesh's material.
 * @returns {THREE.Material} A copy glowing in the highlight colour.
 */
export function glowing(material) {
  const copy = material.clone();
  if (copy.emissive) {
    copy.emissive.setHex(HIGHLIGHT_COLOR);
    copy.emissiveIntensity = GLOW_INTENSITY;
  } else if (copy.color) {
    copy.color.lerp(new THREE.Color(HIGHLIGHT_COLOR), GLOW_INTENSITY);
  }
  return copy;
}

// %% highlights

export class SceneHighlights {
  /**
   * The view the boxes are drawn in.
   * @type {import('./scene-view.js').SceneView}
   */
  #view;

  /**
   * The boxes, each with the parts it surrounds.
   * @type {Array<{parts: Array<THREE.Object3D>, box: THREE.Box3Helper}>}
   */
  #boxes = [];

  /**
   * The glowing meshes with the materials they had before.
   * @type {Array<{mesh: THREE.Mesh, material: THREE.Material|Array<THREE.Material>}>}
   */
  #glows = [];

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
    const parts = highlightedParts(this.#view.content, keys);
    for (const mesh of parts.flatMap(ownMeshes)) {
      if (!mesh.material) continue;
      this.#glows.push({ mesh, material: mesh.material });
      mesh.material = Array.isArray(mesh.material) ? mesh.material.map(glowing) : glowing(mesh.material);
    }
    for (const group of boxedGroups(parts)) {
      const box = new THREE.Box3Helper(this.#bounds(group), HIGHLIGHT_COLOR);
      this.#view.scene.add(box);
      this.#boxes.push({ parts: group, box });
    }
    this.#view.requestRender();
    return parts.length;
  }

  /**
   * Keep each box around its parts as the parts move.
   */
  update() {
    for (const { parts, box } of this.#boxes) box.box.copy(this.#bounds(parts));
  }

  /**
   * Remove every highlight, giving each mesh back the material it had.
   */
  clear() {
    for (const { box } of this.#boxes) {
      box.removeFromParent();
      box.dispose();
    }
    for (const { mesh, material } of this.#glows) {
      for (const copy of [mesh.material].flat()) copy.dispose();
      mesh.material = material;
    }
    this.#boxes = [];
    this.#glows = [];
    this.#view.requestRender();
  }

  /**
   * @param {Array<THREE.Object3D>} parts Links and object holders.
   * @returns {THREE.Box3} The box around their own meshes.
   */
  #bounds(parts) {
    return parts.reduce((box, part) => box.union(ownBounds(part)), new THREE.Box3());
  }
}
