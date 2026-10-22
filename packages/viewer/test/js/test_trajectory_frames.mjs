import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { JointAddress, MissingFrameRate, TrajectoryFrames } from '../../src/cramera/web/scene/trajectory-frames.js';
import { ModelKey, SceneKey, TrajectoryKey } from '../../src/cramera/web/protocol.js';

/**
 * @param {string} path A file of the protocol package's test dataset.
 * @returns {Object} Its JSON content.
 */
function dataset(path) {
  return JSON.parse(readFileSync(new URL(`../../../protocol/test/dataset/${path}`, import.meta.url), 'utf8'));
}

const CELL_SCENE = dataset('recorded_cell/scene.json');
const CELL_TRAJECTORY = dataset('recorded_cell/trajectory.json');

test('prefixed models drive the joints named without their prefix', () => {
  const frames = new TrajectoryFrames(CELL_SCENE, CELL_TRAJECTORY);
  const arm = CELL_SCENE[SceneKey.MODELS].find((model) => model[ModelKey.ROBOT]);
  const values = frames.jointValues(0).get(arm[ModelKey.NAME]);
  const firstJoint = arm[ModelKey.MOVABLE_JOINTS][0];
  assert.equal(values.get(firstJoint), CELL_TRAJECTORY[TrajectoryKey.FRAMES][0][`${arm[ModelKey.PREFIX]}/${firstJoint}`]);
  assert.deepEqual(frames.unassignedKeys(), []);
});

test('models without a prefix drive joints whose names already carry it', () => {
  const scene = { [SceneKey.MODELS]: [{ [ModelKey.NAME]: 'pr2', [ModelKey.PREFIX]: '', [ModelKey.MOVABLE_JOINTS]: ['pr2/torso_lift_joint'] }], [SceneKey.FRAMES_PER_SECOND]: 10 };
  const trajectory = { [TrajectoryKey.FRAMES]: [{ 'pr2/torso_lift_joint': 0.2, 'pr2/unknown_joint': 1 }] };
  const frames = new TrajectoryFrames(scene, trajectory);
  assert.equal(frames.jointValues(0).get('pr2').get('pr2/torso_lift_joint'), 0.2);
  assert.deepEqual(frames.unassignedKeys(), ['pr2/unknown_joint']);
});

test('the frame rate comes from the trajectory, then the scene, legacy keys included', () => {
  assert.equal(new TrajectoryFrames(CELL_SCENE, CELL_TRAJECTORY).framesPerSecond, CELL_TRAJECTORY[TrajectoryKey.LEGACY_FRAMES_PER_SECOND]);
  const sceneRate = new TrajectoryFrames({ [SceneKey.FRAMES_PER_SECOND]: 25 }, { [TrajectoryKey.FRAMES]: [{}, {}] });
  assert.equal(sceneRate.framesPerSecond, 25);
});

test('a single frame needs no rate, several frames do', () => {
  assert.equal(new TrajectoryFrames({}, { [TrajectoryKey.FRAMES]: [{}] }).framesPerSecond, 1);
  assert.throws(() => new TrajectoryFrames({}, { [TrajectoryKey.FRAMES]: [{}, {}] }), MissingFrameRate);
});

test('poses of the robot, its instances and its objects are read per frame', () => {
  const pose = [1, 2, 0, 0, 0, 0, 1];
  const trajectory = {
    [TrajectoryKey.FRAMES]: [{}, {}],
    [TrajectoryKey.FRAMES_PER_SECOND]: 10,
    [TrajectoryKey.BASE]: [pose, pose],
    [TrajectoryKey.MODEL_BASES]: [{ 'r100-1': pose }],
    [TrajectoryKey.OBJECTS]: [{ cup: pose, vanished: null }],
  };
  const frames = new TrajectoryFrames({}, trajectory);
  assert.deepEqual(frames.robotPose(1), pose);
  assert.deepEqual(frames.instancePoses(0).get('r100-1'), pose);
  assert.deepEqual([...frames.objectPoses(0).keys()], ['cup']);
  assert.equal(frames.robotPose(5), null);
  assert.equal(frames.objectPoses(1).size, 0);
});

test('the step of a frame is found from the scene segments', () => {
  const scene = { [SceneKey.FRAMES_PER_SECOND]: 1, [SceneKey.SEGMENTS]: [{ step: 'park', start: 0, end: 4 }, { step: 'pick', start: 5, end: 9 }] };
  const frames = new TrajectoryFrames(scene, { [TrajectoryKey.FRAMES]: [] });
  assert.deepEqual([0, 4, 5, 9, 10].map((frame) => frames.segmentAt(frame)), [0, 0, 1, 1, -1]);
});

test('a joint address names model and joint', () => {
  const address = new JointAddress('pr2', 'torso_lift_joint');
  assert.deepEqual([address.model, address.joint], ['pr2', 'torso_lift_joint']);
});
