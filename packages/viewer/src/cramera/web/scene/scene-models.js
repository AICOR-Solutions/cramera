/**
 * The kinematic models of a scene, loaded from their URDF files, posed per frame.
 */

import * as THREE from 'three';
import URDFLoader from 'urdf-loader';

import { ModelKey } from '../protocol.js';
import { MeshLoading } from './mesh-loading.js';
import { dressModel } from './model-appearance.js';
import { applyPose } from './poses.js';

// %% models

export class SceneModels {
  /**
   * The loaded models by name.
   * @type {Map<string, Object>}
   */
  #robots = new Map();

  /**
   * The model descriptions by name.
   * @type {Map<string, Object>}
   */
  #descriptions = new Map();

  /**
   * The meshes that could not be loaded, with the reason.
   * @type {Array<{url: string, reason: string}>}
   */
  #meshFailures = [];

  /**
   * The group holding every model.
   * @type {THREE.Group}
   */
  group = new THREE.Group();

  /**
   * Load every model of a scene.
   * @param {Array<Object>} descriptions The scene's model descriptions.
   * @param {function(string): string} fileUrl The URL of a bundle file.
   * @param {THREE.LoadingManager} manager Tracks the loaders' requests.
   * @returns {Promise<SceneModels>} This object, once every URDF is parsed.
   */
  async load(descriptions, fileUrl, manager) {
    const meshes = new MeshLoading(manager, (url, reason) => this.#meshFailures.push({ url, reason }));
    const loaded = await Promise.all(descriptions.map((description) => this.#loadModel(description, fileUrl, manager, meshes)));
    loaded.forEach((robot, position) => {
      const description = descriptions[position];
      robot.name = description[ModelKey.NAME];
      this.#robots.set(robot.name, robot);
      this.#descriptions.set(robot.name, description);
      this.group.add(robot);
    });
    return this;
  }

  /**
   * @param {Object} description A model description.
   * @param {function(string): string} fileUrl The URL of a bundle file.
   * @param {THREE.LoadingManager} manager Tracks the loaders' requests.
   * @param {MeshLoading} meshes Loads the meshes.
   * @returns {Promise<Object>} The parsed URDF robot.
   */
  #loadModel(description, fileUrl, manager, meshes) {
    const loader = new URDFLoader(manager);
    loader.parseCollision = false;
    loader.loadMeshCb = (url, _manager, material, done) => {
      meshes.load(url, material).then(
        (mesh) => done(mesh),
        (error) => {
          this.#meshFailures.push({ url, reason: String(error.message ?? error) });
          done(null, error);
        },
      );
    };
    return loader.loadAsync(fileUrl(description[ModelKey.URDF]));
  }

  /**
   * Draw every model the way the scene draws its own objects, once its meshes are
   * loaded; an environment's uncoloured parts get the colour of what they are.
   */
  dress() {
    for (const [name, robot] of this.#robots) dressModel(robot, !this.#descriptions.get(name)[ModelKey.ROBOT]);
  }

  /**
   * @returns {Array<{url: string, reason: string}>} The meshes that could not be loaded.
   */
  meshFailures() {
    return [...this.#meshFailures];
  }

  /**
   * @returns {Array<string>} The names of the loaded models.
   */
  names() {
    return [...this.#robots.keys()];
  }

  /**
   * @param {string} name A model name.
   * @returns {Object|undefined} The loaded URDF robot.
   */
  model(name) {
    return this.#robots.get(name);
  }

  /**
   * @returns {Array<Object>} The loaded robot models.
   */
  robotModels() {
    return this.names().filter((name) => this.#descriptions.get(name)[ModelKey.ROBOT]).map((name) => this.#robots.get(name));
  }

  /**
   * Set the joint values of one frame.
   * @param {Map<string, Map<string, number>>} values The joint values of each model.
   */
  setJointValues(values) {
    for (const [name, joints] of values) {
      const robot = this.#robots.get(name);
      if (!robot) continue;
      for (const [joint, value] of joints) robot.setJointValue(joint, value);
    }
  }

  /**
   * Place the robot model at its recorded root pose.
   * @param {Array<number>|null} pose The robot's root pose, or null to keep it.
   */
  setRobotPose(pose) {
    if (!pose) return;
    for (const robot of this.robotModels()) applyPose(robot, pose);
  }

  /**
   * Place each robot instance at its recorded root pose.
   * @param {Map<string, Array<number>>} poses Root poses by instance identifier.
   */
  setInstancePoses(poses) {
    for (const [name, description] of this.#descriptions) {
      const pose = poses.get(description[ModelKey.IDENTIFIER]);
      if (pose) applyPose(this.#robots.get(name), pose);
    }
  }

  /**
   * Free every geometry, material and texture of the models.
   */
  dispose() {
    this.group.traverse((child) => {
      child.geometry?.dispose();
      for (const material of [child.material].flat().filter(Boolean)) {
        for (const value of Object.values(material)) if (value?.isTexture) value.dispose();
        material.dispose();
      }
    });
    this.group.removeFromParent();
    this.#robots.clear();
    this.#descriptions.clear();
  }
}
