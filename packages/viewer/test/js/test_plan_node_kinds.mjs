import { test } from 'node:test';
import assert from 'node:assert/strict';

import { planNodeKindOf } from '../../src/cramera/web/core/plan-node-kinds.js';
import { LegacyPlanNodeKind, PlanNodeKind } from '../../src/cramera/web/protocol.js';

test('a kind is read as itself', () => {
  assert.equal(planNodeKindOf(PlanNodeKind.ACTION), PlanNodeKind.ACTION);
});

test('the class names of earlier recordings are read as their kinds', () => {
  for (const [member, className] of Object.entries(LegacyPlanNodeKind)) {
    assert.equal(planNodeKindOf(className), PlanNodeKind[member]);
  }
});

test('a class name no kind stands for is another node', () => {
  assert.equal(planNodeKindOf('TryAllNode'), PlanNodeKind.OTHER);
});
