/**
 * How a model loaded from a URDF is drawn: whatever its description and mesh files
 * bring, every model is lit like the scene's own objects, and an environment's parts
 * its description leaves uncoloured get the colour of what they are.
 *
 * URDF materials and COLLADA documents arrive as legacy Phong and Lambert materials,
 * which the scene's environment light does not reach, sometimes with lights of their
 * own and blown-out whites. Each is replaced by a physically based material with the
 * same colour, texture and transparency, the way the scene's objects are drawn.
 */

import * as THREE from 'three';

// %% materials

/**
 * Above this mean channel value a colour counts as blown-out white.
 */
export const BLOWN_OUT_WHITE = 0.97;

/**
 * What a blown-out white is drawn as: a white that still shows its shading.
 */
export const DRAWN_WHITE = Object.freeze([0.9, 0.9, 0.91]);

/**
 * The finish of a converted material that names none.
 */
export const DEFAULT_FINISH = Object.freeze({ roughness: 0.7, metalness: 0 });

/**
 * The colour a URDF material or a mesh without one carries when nothing coloured it.
 */
export const UNCOLOURED = 0xffffff;

/**
 * @param {THREE.Color} color A colour.
 * @returns {boolean} Whether it is a blown-out white.
 */
export function isBlownOut(color) {
  return (color.r + color.g + color.b) / 3 > BLOWN_OUT_WHITE;
}

/**
 * @param {THREE.Material} material A material a URDF or a mesh file brought.
 * @returns {THREE.MeshStandardMaterial} A physically based material with its colour,
 *   texture, transparency, vertex colours and side; a blown-out white is toned down.
 */
export function standardOf(material) {
  const standard = material.isMeshStandardMaterial ? material : new THREE.MeshStandardMaterial({
    name: material.name,
    color: material.color ? material.color.clone() : new THREE.Color(UNCOLOURED),
    map: material.map ?? null,
    opacity: material.opacity,
    transparent: material.transparent,
    vertexColors: material.vertexColors,
    side: material.side,
    ...DEFAULT_FINISH,
  });
  if (!material.vertexColors && !standard.map && isBlownOut(standard.color)) standard.color.setRGB(...DRAWN_WHITE);
  return standard;
}

// %% environment palette

/**
 * The look of an environment part by what its link is called, tried in order, the
 * first match wins: the vocabulary environment descriptions name their furniture with,
 * so it applies to any environment, not one tuned scene.
 */
export const ENVIRONMENT_LOOKS = Object.freeze([
  [/cooktop|hotplate|ceran|stove/, { color: 0x0a0b0d, roughness: 0.18, metalness: 0.15 }],
  [/countertop|worktop/, { color: 0x9c6b3f, roughness: 0.55, metalness: 0.02 }],
  [/coffee_table|table_area|bedside_table|table_top|dining|nightstand|desk/, { color: 0xb98a52, roughness: 0.5, metalness: 0.02 }],
  [/bookshelf|shelf/, { color: 0x6b4226, roughness: 0.65, metalness: 0 }],
  [/sofa|couch|armchair/, { color: 0xa85c48, roughness: 0.88, metalness: 0 }],
  [/chair/, { color: 0x8a5a3b, roughness: 0.6, metalness: 0 }],
  [/bed_|mattress/, { color: 0xe8dcc8, roughness: 0.82, metalness: 0 }],
  [/plant|flower/, { color: 0x3f7d43, roughness: 0.7, metalness: 0 }],
  [/handle|tap|sink|faucet/, { color: 0xc6ccd4, roughness: 0.28, metalness: 0.85 }],
  [/cabinet|drawer|door|wardrobe|dishwasher|oven|coffe_machine|coffee_machine|fridge|refrigerator|island|side_[ab]/, { color: 0x3b3f46, roughness: 0.42, metalness: 0.12 }],
  [/toilet|basin|paper_holder/, { color: 0xf2f2f0, roughness: 0.3, metalness: 0 }],
  [/radiator|handrail|pipe|rack/, { color: 0xb8bcc2, roughness: 0.35, metalness: 0.6 }],
  [/trash|bin_/, { color: 0x2a2d31, roughness: 0.5, metalness: 0.1 }],
  [/lamp/, { color: 0xd4c9a8, roughness: 0.5, metalness: 0.3 }],
  [/floor|ground/, { color: 0x8c8478, roughness: 0.9, metalness: 0 }],
  [/wall|window/, { color: 0xd9d4cb, roughness: 0.95, metalness: 0 }],
]);

/**
 * @param {string} linkName A link's name, with or without its model's prefix.
 * @returns {{color: number, roughness: number, metalness: number}|null} The look of
 *   the part it names, or null when the vocabulary names nothing it could be.
 */
export function environmentLookOf(linkName) {
  const name = (linkName ?? '').toLowerCase();
  const match = ENVIRONMENT_LOOKS.find(([pattern]) => pattern.test(name));
  return match ? match[1] : null;
}

// %% models

/**
 * @param {THREE.Object3D} object A part of a model.
 * @returns {string} The name of the URDF link it belongs to, or an empty name.
 */
export function linkNameOf(object) {
  for (let node = object; node; node = node.parent) if (node.isURDFLink) return node.name ?? '';
  return '';
}

/**
 * Draw a loaded model the way the scene draws its own objects.
 * @param {THREE.Object3D} model A model loaded from a URDF, with its meshes.
 * @param {boolean} environment Whether the model is an environment, whose uncoloured
 *   parts get the colour of what their link names; a robot keeps its own colours.
 */
export function dressModel(model, environment) {
  const imported = [];
  model.traverse((child) => { if (child.isLight) imported.push(child); });
  for (const light of imported) light.removeFromParent();
  model.traverse((child) => {
    if (!child.isMesh) return;
    const materials = [child.material].flat().map((material) => {
      const uncoloured = !material.map && !material.vertexColors && material.color?.getHex() === UNCOLOURED;
      const standard = standardOf(material);
      const look = environment && uncoloured ? environmentLookOf(linkNameOf(child)) : null;
      if (look) {
        standard.color.setHex(look.color);
        standard.roughness = look.roughness;
        standard.metalness = look.metalness;
      }
      if (standard !== material) material.dispose();
      return standard;
    });
    child.material = Array.isArray(child.material) ? materials : materials[0];
  });
}
