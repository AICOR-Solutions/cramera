/**
 * One placed copy of a resource in the 3D view. A link's offset is applied in its
 * parent's frame before its authored transform, so removing it restores the model as
 * authored; the model's own files are never changed.
 */

import * as THREE from 'three';

import { AppearanceKey, InstanceKey, LinkOffsetKey } from '../../../protocol.js';
import { PointCloudSample } from './point-cloud-sample.js';

/**
 * The order URDF applies roll, pitch and yaw in: about the fixed x, y and z axes, so
 * the rotation is `Rz · Ry · Rx`.
 */
export const ROTATION_ORDER = 'ZYX';

/**
 * The URDF joint types whose value a person can set.
 */
export const JointType = Object.freeze({ REVOLUTE: 'revolute', CONTINUOUS: 'continuous', PRISMATIC: 'prismatic' });

/**
 * The joint types whose value a person can set.
 */
export const MOVABLE_JOINT_TYPES = Object.freeze(Object.values(JointType));

/**
 * The marks the instance leaves in `userData`, so a picked mesh finds its instance and
 * link.
 */
export const PickMark = Object.freeze({ INSTANCE: 'sceneBuilderInstance', LINK: 'sceneBuilderLink' });

// %% errors

/**
 * A draft naming a link or joint the model does not have.
 */
export class UnknownModelPart extends Error {
  /**
   * @param {string} instance The instance's identity.
   * @param {string} part The link or joint name.
   */
  constructor(instance, part) {
    super(`${instance} has no link or joint named ${part}.`);
    /**
     * The instance's identity.
     * @type {string}
     */
    this.instance = instance;
    /**
     * The link or joint name.
     * @type {string}
     */
    this.part = part;
  }
}

// %% transforms

/**
 * @param {Array<number>} position A position.
 * @param {Array<number>} rotation A roll, pitch and yaw.
 * @param {Array<number>=} scale The factor along each axis.
 * @returns {THREE.Matrix4} The transform.
 */
export function transformOf(position, rotation, scale = [1, 1, 1]) {
  const quaternion = new THREE.Quaternion().setFromEuler(new THREE.Euler(...rotation, ROTATION_ORDER));
  return new THREE.Matrix4().compose(new THREE.Vector3(...position), quaternion, new THREE.Vector3(...scale));
}

/**
 * @param {THREE.Matrix4} matrix A transform.
 * @returns {{position: Array<number>, rotation: Array<number>, scale: Array<number>}} Its
 *   position, roll, pitch and yaw, and scale.
 */
export function placementOf(matrix) {
  const position = new THREE.Vector3();
  const quaternion = new THREE.Quaternion();
  const scale = new THREE.Vector3();
  matrix.decompose(position, quaternion, scale);
  const rotation = new THREE.Euler().setFromQuaternion(quaternion, ROTATION_ORDER);
  return { position: position.toArray(), rotation: [rotation.x, rotation.y, rotation.z], scale: scale.toArray() };
}

// %% instance

export class PlacedInstance {
  /**
   * The authored transform of each URDF link in its parent's frame.
   * @type {Map<string, THREE.Matrix4>}
   */
  #authored = new Map();

  /**
   * The group the instance's placement is applied to.
   * @type {THREE.Group}
   */
  group = new THREE.Group();

  /**
   * @param {Object} instance The draft's instance.
   * @param {THREE.Object3D} root The loaded resource: a URDF robot, a mesh or points.
   */
  constructor(instance, root) {
    /**
     * The instance's identity.
     * @type {string}
     */
    this.identifier = instance[InstanceKey.IDENTIFIER];
    /**
     * The resource the instance shows.
     * @type {string}
     */
    this.asset = instance[InstanceKey.ASSET];
    /**
     * The loaded resource.
     * @type {THREE.Object3D}
     */
    this.root = root;
    /**
     * How the reference is shown, or null for a model.
     * @type {Object|null}
     */
    this.appearance = null;
    this.group.userData[PickMark.INSTANCE] = this.identifier;
    this.group.add(root);
    for (const [name, link] of Object.entries(root.links ?? {})) {
      link.updateMatrix();
      this.#authored.set(name, link.matrix.clone());
      link.userData[PickMark.LINK] = name;
    }
    this.apply(instance);
  }

  /**
   * @returns {boolean} Whether the instance shows a reference point cloud.
   */
  get isPointCloud() {
    return this.root.isPoints === true;
  }

  /**
   * @returns {boolean} Whether a person can move the instance: a visible, unlocked
   *   reference or any model.
   */
  get isEditable() {
    return this.appearance === null || (this.appearance[AppearanceKey.VISIBLE] && !this.appearance[AppearanceKey.LOCKED]);
  }

  /**
   * Show the instance as the draft places it.
   * @param {Object} instance The draft's instance.
   * @throws {UnknownModelPart} When the draft names a link or joint the model lacks.
   */
  apply(instance) {
    const offsets = instance[InstanceKey.LINK_OFFSETS] ?? {};
    const joints = instance[InstanceKey.JOINT_POSITIONS] ?? {};
    for (const name of Object.keys(offsets)) if (!this.#authored.has(name)) throw new UnknownModelPart(this.identifier, name);
    for (const name of Object.keys(joints)) if (!this.root.joints?.[name]) throw new UnknownModelPart(this.identifier, name);
    transformOf(instance[InstanceKey.POSITION], instance[InstanceKey.ROTATION], instance[InstanceKey.SCALE]).decompose(this.group.position, this.group.quaternion, this.group.scale);
    this.group.name = instance[InstanceKey.NAME];
    for (const [name, authored] of this.#authored) {
      const offset = offsets[name];
      const placed = offset ? transformOf(offset[LinkOffsetKey.POSITION], offset[LinkOffsetKey.ROTATION]).multiply(authored) : authored.clone();
      const link = this.root.links[name];
      placed.decompose(link.position, link.quaternion, link.scale);
    }
    for (const [name, joint] of Object.entries(this.root.joints ?? {})) {
      if (MOVABLE_JOINT_TYPES.includes(joint.jointType)) joint.setJointValue(joints[name] ?? 0);
    }
    if (this.isPointCloud) {
      this.appearance = { ...instance[InstanceKey.POINT_CLOUD] };
      PointCloudSample.show(this.root, this.appearance);
    }
    this.group.updateMatrixWorld(true);
  }

  /**
   * @param {string|null} link A link name, or null for the whole instance.
   * @returns {THREE.Object3D} What a transform handle moves.
   * @throws {UnknownModelPart} For a link the model lacks.
   */
  target(link) {
    if (link === null) return this.group;
    if (!this.#authored.has(link)) throw new UnknownModelPart(this.identifier, link);
    return this.root.links[link];
  }

  /**
   * @param {string|null} link A link name, or null for the whole instance.
   * @returns {{position: Array<number>, rotation: Array<number>, scale: Array<number>}}
   *   The placement a person gave the target: for a link, its offset before the
   *   authored transform.
   */
  placement(link) {
    const target = this.target(link);
    target.updateMatrix();
    const matrix = target.matrix.clone();
    if (link !== null) matrix.multiply(this.#authored.get(link).clone().invert());
    return placementOf(matrix);
  }

  /**
   * @returns {{links: Array<string>, joints: Array<{name: string, type: string, lower: number, upper: number}>}}
   *   The model's link names and movable joints.
   */
  structure() {
    const joints = Object.entries(this.root.joints ?? {})
      .filter(([, joint]) => MOVABLE_JOINT_TYPES.includes(joint.jointType))
      .map(([name, joint]) => ({ name, type: joint.jointType, lower: Number(joint.limit.lower), upper: Number(joint.limit.upper) }));
    return { links: [...this.#authored.keys()], joints };
  }

  /**
   * Free the instance's geometries, materials and textures.
   */
  dispose() {
    this.group.removeFromParent();
    this.group.traverse((child) => {
      child.geometry?.dispose();
      for (const material of [child.material].flat().filter(Boolean)) {
        for (const value of Object.values(material)) if (value?.isTexture) value.dispose();
        material.dispose();
      }
    });
  }
}
