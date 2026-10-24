/**
 * Loading the meshes a URDF or a free object references, by their file format.
 */

import * as THREE from 'three';
import { ColladaLoader } from 'three/addons/loaders/ColladaLoader.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MTLLoader } from 'three/addons/loaders/MTLLoader.js';
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';

import { MeshFormat } from '../protocol.js';

/**
 * Finds the material library an OBJ file names.
 */
const MATERIAL_LIBRARY_LINE = /^mtllib\s+(.+)$/m;

// %% errors

/**
 * A mesh file of a format the viewer cannot load.
 */
export class UnsupportedMeshFormat extends Error {
  /**
   * @param {string} url The mesh file.
   */
  constructor(url) {
    super(`${url} is not a mesh format the viewer loads.`);
    /**
     * The mesh file.
     * @type {string}
     */
    this.url = url;
  }
}

// %% formats

/**
 * @param {string} url A mesh file.
 * @returns {string|null} Its `MeshFormat` value, or null for an unknown suffix.
 */
export function meshFormatOf(url) {
  const path = new URL(url, 'http://local/').pathname.toLowerCase();
  return Object.values(MeshFormat).find((suffix) => path.endsWith(suffix)) ?? null;
}

/**
 * A COLLADA document that declares no material is drawn with the material its URDF
 * gives it, as STL and OBJ files without one are; a document with materials of its own
 * keeps them.
 * @param {{scene: THREE.Object3D, library: {materials: Object}}} collada A loaded
 *   COLLADA document.
 * @param {THREE.Material=} material The material its URDF gives it, if any.
 * @returns {THREE.Object3D} The document's scene.
 */
export function paintBareCollada(collada, material) {
  if (material && !Object.keys(collada.library.materials).length) {
    collada.scene.traverse((child) => { if (child.isMesh) child.material = material; });
  }
  return collada.scene;
}

// %% loading

export class MeshLoading {
  /**
   * Tracks every request the loaders make, so a scene knows when it is complete.
   * @type {THREE.LoadingManager}
   */
  #manager;

  /**
   * Called with a file that is missing although the mesh can be shown without it.
   * @type {function(string, string): void}
   */
  #onMissingCompanion;

  /**
   * @param {THREE.LoadingManager} manager Tracks the loaders' requests.
   * @param {function(string, string): void} onMissingCompanion Called with the URL and
   *   reason of a missing file a mesh refers to but can be shown without, such as an
   *   OBJ material library.
   */
  constructor(manager, onMissingCompanion) {
    this.#manager = manager;
    this.#onMissingCompanion = onMissingCompanion;
  }

  /**
   * @param {string} url A mesh file.
   * @param {THREE.Material=} material The material of formats that carry none.
   * @returns {Promise<THREE.Object3D>} The mesh, in the file's own coordinates.
   * @throws {UnsupportedMeshFormat} For an unknown format.
   */
  load(url, material) {
    switch (meshFormatOf(url)) {
      case MeshFormat.STL:
        return this.#loadStl(url, material);
      case MeshFormat.GLB:
      case MeshFormat.GLTF:
        return new GLTFLoader(this.#manager).loadAsync(url).then((gltf) => gltf.scene);
      case MeshFormat.COLLADA:
        return this.#loadCollada(url, material);
      case MeshFormat.OBJ:
        return this.#loadObj(url, material);
      default:
        return Promise.reject(new UnsupportedMeshFormat(url));
    }
  }

  /**
   * @param {string} url An STL file.
   * @param {THREE.Material=} material Its material.
   * @returns {Promise<THREE.Mesh>} The mesh.
   */
  async #loadStl(url, material) {
    const geometry = await new STLLoader(this.#manager).loadAsync(url);
    geometry.computeVertexNormals();
    return new THREE.Mesh(geometry, material ?? new THREE.MeshStandardMaterial());
  }

  /**
   * URDF frames are z-up already, so the loader's turn of z-up documents into a y-up
   * world is undone.
   * @param {string} url A COLLADA file.
   * @param {THREE.Material=} material Its material when the document declares none.
   * @returns {Promise<THREE.Object3D>} The document's scene.
   */
  async #loadCollada(url, material) {
    const collada = await new ColladaLoader(this.#manager).loadAsync(url);
    collada.scene.rotation.set(0, 0, 0);
    collada.scene.updateMatrix();
    return paintBareCollada(collada, material);
  }

  /**
   * @param {string} url An OBJ file.
   * @param {THREE.Material=} material Its material when it names no material library.
   * @returns {Promise<THREE.Object3D>} The mesh with the materials of its library.
   */
  async #loadObj(url, material) {
    const text = await new THREE.FileLoader(this.#manager).loadAsync(url);
    const loader = new OBJLoader(this.#manager);
    const library = text.match(MATERIAL_LIBRARY_LINE)?.[1].trim();
    const materials = library ? await this.#loadMaterialLibrary(new URL(library, url).href) : null;
    if (materials) loader.setMaterials(materials);
    const object = loader.parse(text);
    if (!materials && material) object.traverse((child) => { if (child.isMesh) child.material = material; });
    return object;
  }

  /**
   * @param {string} url The material library an OBJ file names.
   * @returns {Promise<Object|null>} The library's materials, or null when it is
   *   missing; a missing library is reported and the mesh keeps its URDF material.
   */
  #loadMaterialLibrary(url) {
    return new MTLLoader(this.#manager)
      .setResourcePath(new URL('./', url).href)
      .loadAsync(url)
      .then(
        (materials) => {
          materials.preload();
          return materials;
        },
        (error) => {
          this.#onMissingCompanion(url, String(error.message ?? error));
          return null;
        },
      );
  }
}
