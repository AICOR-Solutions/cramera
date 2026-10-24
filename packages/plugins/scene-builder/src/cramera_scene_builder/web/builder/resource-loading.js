/**
 * Loading the resources a draft places: URDF models with their meshes, single meshes,
 * and the display samples of point clouds. A model is given once every file it
 * refers to has arrived, with its meshes casting and receiving shadows.
 */

import * as THREE from 'three';
import URDFLoader from 'urdf-loader';

import { PrimitiveShape, ResourceKey, ResourceKind } from '../../../protocol.js';
import { LoadingProgress } from '../../../scene/loading-progress.js';
import { MeshLoading } from '../../../scene/mesh-loading.js';
import { dressModel } from '../../../scene/model-appearance.js';
import { PointCloudSample } from './point-cloud-sample.js';

// %% errors

/**
 * A mesh a model refers to that could not be loaded.
 */
export class MissingMesh extends Error {
  /**
   * @param {string} url The mesh's URL.
   * @param {string} reason Why it could not be loaded.
   */
  constructor(url, reason) {
    super(`${url} could not be loaded: ${reason}`);
    /**
     * The mesh's URL.
     * @type {string}
     */
    this.url = url;
    /**
     * Why it could not be loaded.
     * @type {string}
     */
    this.reason = reason;
  }
}

// %% primitive shapes

/**
 * How a primitive shape is drawn: a plain, light blue stand-in with its edges outlined,
 * so it reads as a placeholder for an object still to be designed.
 */
export const PrimitiveLook = Object.freeze({
  COLOR: 0x8fb8de,
  ROUGHNESS: 0.6,
  EDGE_COLOR: 0x1f3b57,
  CURVE_SEGMENTS: 48,
});

/**
 * The geometry of each primitive shape: one metre across, z up, standing on its base.
 */
const PRIMITIVE_GEOMETRY = Object.freeze({
  [PrimitiveShape.BOX]: () => new THREE.BoxGeometry(1, 1, 1),
  [PrimitiveShape.CYLINDER]: () => new THREE.CylinderGeometry(0.5, 0.5, 1, PrimitiveLook.CURVE_SEGMENTS).rotateX(Math.PI / 2),
  [PrimitiveShape.SPHERE]: () => new THREE.SphereGeometry(0.5, PrimitiveLook.CURVE_SEGMENTS, PrimitiveLook.CURVE_SEGMENTS / 2),
});

/**
 * @param {string} identifier A primitive shape's resource identifier, `primitives/<shape>`.
 * @returns {THREE.Object3D} The shape, with its edges outlined.
 * @throws {Error} For a shape there is none of.
 */
export function primitiveObject(identifier) {
  const shape = identifier.split('/').at(-1);
  const geometry = PRIMITIVE_GEOMETRY[shape]?.();
  if (!geometry) throw new Error(`There is no primitive shape ${shape}.`);
  geometry.translate(0, 0, 0.5);
  const root = new THREE.Group();
  const body = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: PrimitiveLook.COLOR, roughness: PrimitiveLook.ROUGHNESS }));
  const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 20), new THREE.LineBasicMaterial({ color: PrimitiveLook.EDGE_COLOR }));
  root.add(body, edges);
  return root;
}

// %% loading

export class ResourceLoading {
  /**
   * The builder's routes.
   * @type {import('./builder-api.js').BuilderApi}
   */
  #api;

  /**
   * Called with every mesh or companion file that could not be loaded.
   * @type {function(MissingMesh): void}
   */
  #onMissing;

  /**
   * @param {import('./builder-api.js').BuilderApi} api The builder's routes.
   * @param {function(MissingMesh): void} onMissing Called with every file a model
   *   refers to that could not be loaded; the model is shown without it.
   */
  constructor(api, onMissing) {
    this.#api = api;
    this.#onMissing = onMissing;
  }

  /**
   * @param {Object} resource A catalog resource.
   * @param {Object|null} appearance How a point cloud is shown, by `AppearanceKey`.
   * @returns {Promise<THREE.Object3D>} The resource, in its file's coordinates.
   */
  async load(resource, appearance) {
    const identifier = resource[ResourceKey.IDENTIFIER];
    if (resource[ResourceKey.KIND] === ResourceKind.PRIMITIVE) {
      const shape = primitiveObject(identifier);
      shape.traverse((child) => {
        if (child.isMesh) child.castShadow = child.receiveShadow = true;
      });
      return shape;
    }
    if (resource[ResourceKey.KIND] === ResourceKind.POINT_CLOUD) {
      return PointCloudSample.fromBytes(await this.#api.sample(identifier)).points(appearance);
    }
    const progress = new LoadingProgress();
    const meshes = new MeshLoading(progress.manager, (url, reason) => this.#onMissing(new MissingMesh(url, reason)));
    const url = this.#api.assetUrl(identifier);
    const root = resource[ResourceKey.KIND] === ResourceKind.URDF ? await this.#loadUrdf(url, progress.manager, meshes) : await meshes.load(url, new THREE.MeshStandardMaterial());
    progress.settleIfUnused();
    await progress.idle();
    // a scene's URDF is a piece of environment, whose uncoloured parts get the colour of
    // what they are; a lone mesh keeps its own colours
    dressModel(root, resource[ResourceKey.KIND] === ResourceKind.URDF);
    root.traverse((child) => {
      if (child.isMesh) child.castShadow = child.receiveShadow = true;
    });
    return root;
  }

  /**
   * @param {string} url The URDF's URL.
   * @param {THREE.LoadingManager} manager Tracks the loaders' requests.
   * @param {MeshLoading} meshes Loads the meshes.
   * @returns {Promise<Object>} The parsed URDF robot.
   */
  #loadUrdf(url, manager, meshes) {
    const loader = new URDFLoader(manager);
    loader.parseCollision = false;
    loader.loadMeshCb = (meshUrl, _manager, material, done) => {
      meshes.load(meshUrl, material).then(
        (mesh) => done(mesh),
        (error) => {
          this.#onMissing(new MissingMesh(meshUrl, String(error.message ?? error)));
          done(null, error);
        },
      );
    };
    return loader.loadAsync(url);
  }
}
