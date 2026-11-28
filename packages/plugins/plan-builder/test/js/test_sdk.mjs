import { test } from 'node:test';
import assert from 'node:assert/strict';

import * as sdk from 'cramera-viewer/sdk/v1/index.js';

// %% the plugin SDK, version 1

test('the SDK offers the plan builder\'s view and API and the viewer\'s API', () => {
  for (const name of ['PlanScene', 'PlanSceneListeners', 'SceneOverlay', 'PlanBuilderApi', 'ViewerApi', 'Bounds', 'RequestFailed', 'RequestRefused']) {
    assert.equal(typeof sdk[name], 'function', name);
  }
  assert.equal(typeof sdk.MarkerKind.OBJECT, 'string');
});

test('the SDK offers the protocol\'s keys', () => {
  assert.equal(typeof sdk.PlannedObjectKey.IDENTIFIER, 'string');
  assert.equal(typeof sdk.PlannedRobotKey.MODEL, 'string');
  assert.equal(typeof sdk.PlanStepKey.IDENTIFIER, 'string');
});

test('a page frames the view on a box of its own through the SDK', () => {
  assert.equal(typeof sdk.PlanScene.prototype.frameOn, 'function');
});

test('the SDK is version 1', () => {
  assert.equal(sdk.SDK_VERSION.split('.')[0], '1');
});
