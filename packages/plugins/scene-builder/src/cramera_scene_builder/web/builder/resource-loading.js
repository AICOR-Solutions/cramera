/**
 * Loading the resources a draft places: URDF models with their meshes, single meshes,
 * and the display samples of point clouds. A model is given once every file it
 * refers to has arrived, with its meshes casting and receiving shadows.
 */

import * as THREE from 'three';
import URDFLoader from 'urdf-loader';

import { ResourceKey, ResourceKind } from '../../../protocol.js';
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
