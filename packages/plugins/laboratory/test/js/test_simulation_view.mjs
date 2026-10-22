import assert from 'node:assert/strict';
import { test } from 'node:test';

import { ContactPhysicsKey, LiquidStateKey, SnapshotKey, VesselInteriorKey, VesselLiquidKey } from 'cramera-viewer/protocol.js';

import { SimulationView, puddleRadius, sphereRadius, surfaceOutline } from '../../src/cramera_laboratory/web/simulation-view.js';
import { readDataset } from './fakes.mjs';

const controls = readDataset('controls.json');
const interior = controls[ContactPhysicsKey.INTERIOR];

test('a level surface outlines a circle at its offset', () => {
  const height = 0.08;
  const outline = surfaceOutline(interior, [0, 0, 1], height);
  for (const [x, y, z] of outline) {
    assert.ok(Math.abs(Math.hypot(x, y) - interior[VesselInteriorKey.RADIUS]) < 1e-9);
    assert.ok(Math.abs(z - height) < 1e-9);
  }
});

test('a tilted surface rises on the side its normal leans away from', () => {
  const normal = [Math.sin(0.3), 0, Math.cos(0.3)];
  const outline = surfaceOutline(interior, normal, 0.08, 4);
  const [positiveX, , negativeX] = outline;
  assert.ok(negativeX[2] > positiveX[2]);
});

test('a low surface narrows into the rounded bottom', () => {
  const low = interior[VesselInteriorKey.BOTTOM] + interior[VesselInteriorKey.RADIUS] / 2;
  const [first] = surfaceOutline(interior, [0, 0, 1], low);
  assert.ok(Math.hypot(first[0], first[1]) < interior[VesselInteriorKey.RADIUS]);
});

test('droplets and puddles keep their volume', () => {
  const millilitre = 1e-6;
  assert.ok(Math.abs((4 / 3) * Math.PI * sphereRadius(1) ** 3 - millilitre) < 1e-12);
  assert.ok(Math.abs(Math.PI * puddleRadius(1) ** 2 * 0.001 - millilitre) < 1e-12);
});

test('the view draws each vessel with liquid and hides an empty one', () => {
  const snapshot = readDataset('snapshot.json');
  const [filled, empty] = controls[ContactPhysicsKey.VESSELS];
  const liquids = snapshot[SnapshotKey.LIQUID][LiquidStateKey.VESSELS];
  const sample = Object.values(liquids)[0];
  snapshot[SnapshotKey.OBJECTS][empty] = [0.2, 0, 0.9, 0, 0, 0, 1];
  liquids[filled] = sample;
  liquids[empty] = { ...sample, [VesselLiquidKey.VOLUME]: 0 };
  const view = new SimulationView(interior, [filled, empty]);
  view.show(snapshot);
  const [filledGroup, emptyGroup] = view.group.children;
  assert.equal(filledGroup.visible, true);
  assert.equal(emptyGroup.visible, false);
  assert.deepEqual(filledGroup.position.toArray(), snapshot[SnapshotKey.OBJECTS][filled].slice(0, 3));
  view.dispose();
});
