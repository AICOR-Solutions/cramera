import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import * as THREE from 'three';

import { AppearanceKey, CatalogKey, DraftKey, InstanceKey, LinkOffsetKey } from 'cramera-viewer/protocol.js';
import { DraftCheck } from '../../src/cramera_scene_builder/web/builder/draft-check.js';
import { JointType, PickMark, PlacedInstance, placementOf, transformOf, UnknownModelPart } from '../../src/cramera_scene_builder/web/builder/placed-instance.js';
import { MalformedSample, PointCloudSample, SampleHeader } from '../../src/cramera_scene_builder/web/builder/point-cloud-sample.js';

const read = (name) => readFileSync(new URL(`dataset/${name}`, import.meta.url));
const json = (name) => JSON.parse(read(name).toString('utf8'));
const catalog = json('catalog.json');
const draft = new DraftCheck(catalog[CatalogKey.LIMITS], catalog[CatalogKey.DEFAULT_APPEARANCE]).draft(json('draft.json'));
const bytes = (name) => {
  const buffer = read(name);
  return buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength);
};

/**
 * A model shaped like a parsed URDF: a body link with a drawer link below it, joined by
 * a prismatic joint.
 */
function cabinet() {
  const root = new THREE.Group();
  const body = new THREE.Group();
  const drawer = new THREE.Group();
  drawer.position.set(0.2, 0, 0.4);
  drawer.add(new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.1, 0.1), new THREE.MeshBasicMaterial()));
  body.add(drawer);
  root.add(body);
  const slide = { jointType: JointType.PRISMATIC, limit: { lower: 0, upper: 0.4 }, values: [], setJointValue(value) { this.values.push(value); } };
  root.links = { body, drawer };
  root.joints = { slide, fixed: { jointType: 'fixed', limit: {} } };
  return root;
}

// %% samples

test('a sample decodes into the positions and colours the server wrote', () => {
  const sample = PointCloudSample.fromBytes(bytes('colored_ascii_sample.bin'));
  const expected = json('colored_ascii_sample.json');
  assert.deepEqual([...sample.positions], expected.positions);
  assert.deepEqual([...sample.colors], expected.colors);
  assert.equal(sample.pointCount, expected.positions.length / 3);
});

test('a colourless sample has no colours', () => {
  const sample = PointCloudSample.fromBytes(bytes('missing_measurements_sample.bin'));
  assert.deepEqual([...sample.positions], json('missing_measurements_sample.json').positions);
  assert.equal(sample.colors, null);
});

test('bytes shorter than their header declares are refused', () => {
  const whole = bytes('colored_ascii_sample.bin');
  assert.throws(() => PointCloudSample.fromBytes(whole.slice(0, whole.byteLength - 4)), MalformedSample);
  assert.throws(() => PointCloudSample.fromBytes(whole.slice(0, SampleHeader.LENGTH - 1)), MalformedSample);
});

test('points are shown with the appearance of the reference', () => {
  const appearance = draft[DraftKey.INSTANCES][1][InstanceKey.POINT_CLOUD];
  const points = PointCloudSample.fromBytes(bytes('colored_ascii_sample.bin')).points(appearance);
  assert.equal(points.material.size, appearance[AppearanceKey.POINT_SIZE]);
  assert.equal(points.material.opacity, appearance[AppearanceKey.OPACITY]);
  assert.equal(points.material.vertexColors, true);
  assert.equal(points.geometry.getAttribute('position').count, 3);
});

// %% transforms

test('a placement read back from its transform is the placement', () => {
  const placement = placementOf(transformOf([1, 2, 3], [0.3, -0.4, 1.1], [2, 2, 2]));
  assert.deepEqual(placement.position.map((value) => Number(value.toFixed(9))), [1, 2, 3]);
  assert.deepEqual(placement.rotation.map((value) => Number(value.toFixed(9))), [0.3, -0.4, 1.1]);
  assert.deepEqual(placement.scale.map((value) => Number(value.toFixed(9))), [2, 2, 2]);
});

test('roll, pitch and yaw turn about the fixed x, y and z axes', () => {
  const yawThenNothing = new THREE.Vector3(1, 0, 0).applyMatrix4(transformOf([0, 0, 0], [0, 0, Math.PI / 2]));
  const rollThenYaw = new THREE.Vector3(0, 1, 0).applyMatrix4(transformOf([0, 0, 0], [Math.PI / 2, 0, Math.PI / 2]));
  assert.deepEqual(yawThenNothing.toArray().map((value) => Math.round(value) + 0), [0, 1, 0]);
  assert.deepEqual(rollThenYaw.toArray().map((value) => Math.round(value) + 0), [0, 0, 1]);
});

// %% instances

test('an instance applies its placement, link offsets and joints', () => {
  const root = cabinet();
  const instance = draft[DraftKey.INSTANCES][0];
  const placed = new PlacedInstance(instance, root);
  assert.deepEqual(placed.group.position.toArray(), instance[InstanceKey.POSITION]);
  assert.equal(placed.group.userData[PickMark.INSTANCE], instance[InstanceKey.IDENTIFIER]);
  assert.equal(root.links.drawer.userData[PickMark.LINK], 'drawer');
  const offset = instance[InstanceKey.LINK_OFFSETS].drawer[LinkOffsetKey.POSITION];
  assert.deepEqual(root.links.drawer.position.toArray().map((value) => Number(value.toFixed(9))), [0.2 + offset[0], offset[1], 0.4 + offset[2]]);
  assert.deepEqual(root.joints.slide.values, [instance[InstanceKey.JOINT_POSITIONS].slide]);
});

test('removing a link offset restores the authored placement', () => {
  const root = cabinet();
  const instance = structuredClone(draft[DraftKey.INSTANCES][0]);
  const placed = new PlacedInstance(instance, root);
  instance[InstanceKey.LINK_OFFSETS] = {};
  placed.apply(instance);
  assert.deepEqual(root.links.drawer.position.toArray(), [0.2, 0, 0.4]);
});

test('a link placement is its offset before the authored transform', () => {
  const instance = draft[DraftKey.INSTANCES][0];
  const placed = new PlacedInstance(instance, cabinet());
  const placement = placed.placement('drawer');
  assert.deepEqual(placement.position.map((value) => Number(value.toFixed(9))), instance[InstanceKey.LINK_OFFSETS].drawer[LinkOffsetKey.POSITION]);
});

test('a draft naming a link the model lacks is refused', () => {
  const instance = structuredClone(draft[DraftKey.INSTANCES][0]);
  instance[InstanceKey.LINK_OFFSETS] = { lid: instance[InstanceKey.LINK_OFFSETS].drawer };
  assert.throws(() => new PlacedInstance(instance, cabinet()), UnknownModelPart);
  assert.throws(() => new PlacedInstance(draft[DraftKey.INSTANCES][0], cabinet()).target('lid'), UnknownModelPart);
});

test('the structure lists the links and the movable joints', () => {
  const structure = new PlacedInstance(draft[DraftKey.INSTANCES][0], cabinet()).structure();
  assert.deepEqual(structure.links, ['body', 'drawer']);
  assert.deepEqual(structure.joints, [{ name: 'slide', type: JointType.PRISMATIC, lower: 0, upper: 0.4 }]);
});

test('a locked or hidden reference cannot be moved', () => {
  const instance = structuredClone(draft[DraftKey.INSTANCES][1]);
  const points = PointCloudSample.fromBytes(bytes('colored_ascii_sample.bin')).points(instance[InstanceKey.POINT_CLOUD]);
  const placed = new PlacedInstance(instance, points);
  assert.equal(placed.isPointCloud, true);
  assert.equal(placed.isEditable, true);
  instance[InstanceKey.POINT_CLOUD][AppearanceKey.LOCKED] = true;
  placed.apply(instance);
  assert.equal(placed.isEditable, false);
  instance[InstanceKey.POINT_CLOUD][AppearanceKey.LOCKED] = false;
  instance[InstanceKey.POINT_CLOUD][AppearanceKey.VISIBLE] = false;
  placed.apply(instance);
  assert.equal(placed.isEditable, false);
  assert.equal(points.visible, false);
});

test('disposing an instance frees its geometry and removes it', () => {
  const parent = new THREE.Group();
  const placed = new PlacedInstance(draft[DraftKey.INSTANCES][0], cabinet());
  parent.add(placed.group);
  let freed = 0;
  placed.group.traverse((child) => child.geometry?.addEventListener('dispose', () => (freed += 1)));
  placed.dispose();
  assert.equal(parent.children.length, 0);
  assert.equal(freed, 1);
});
