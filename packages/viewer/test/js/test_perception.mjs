import { test } from 'node:test';
import assert from 'node:assert/strict';

import { EventBus } from '../../src/cramera/web/core/event-bus.js';
import { flattened, NO_PERCEPTION, NOTHING_REPORTED, PerceptionPanel, perceptionSteps } from '../../src/cramera/web/panels/perception-panel.js';
import { LivePlanKey, LivePlanNodeKey, PlanNodeKey, ViewerEvent } from '../../src/cramera/web/protocol.js';
import { FakeDocument } from './support/fake-document.mjs';

/**
 * A recorded plan: parking the arms, then a detect action whose motion saw the milk.
 */
const TREES = Object.freeze([
  {
    [PlanNodeKey.IDENTIFIER]: 'n0',
    [PlanNodeKey.KIND]: 'SequentialNode',
    [PlanNodeKey.LABEL]: 'SequentialNode',
    [PlanNodeKey.STATUS]: 'SUCCEEDED',
    [PlanNodeKey.ROBOT]: 'PR2 1',
    [PlanNodeKey.CHILDREN]: [
      { [PlanNodeKey.IDENTIFIER]: 'n1', [PlanNodeKey.LABEL]: 'ParkArmsAction', [PlanNodeKey.STATUS]: 'SUCCEEDED', [PlanNodeKey.CHILDREN]: [] },
      {
        [PlanNodeKey.IDENTIFIER]: 'n2',
        [PlanNodeKey.LABEL]: 'DetectAction',
        [PlanNodeKey.STATUS]: 'SUCCEEDED',
        [PlanNodeKey.START]: 40,
        [PlanNodeKey.PARAMETERS]: { technique: 'TYPES', object_sem_annotation: 'Milk' },
        [PlanNodeKey.CHILDREN]: [
          {
            [PlanNodeKey.IDENTIFIER]: 'n3',
            [PlanNodeKey.LABEL]: 'DetectingMotion',
            [PlanNodeKey.STATUS]: 'SUCCEEDED',
            [PlanNodeKey.PARAMETERS]: { query: 'semantic_annotation Milk' },
            [PlanNodeKey.PERCEIVED]: ['k-milk'],
            [PlanNodeKey.CHILDREN]: [],
          },
        ],
      },
    ],
  },
]);

function openPanel() {
  const bus = new EventBus();
  const published = [];
  bus.subscribe(ViewerEvent.ENTITY_HIGHLIGHTED, (keys) => published.push(['highlight', keys]));
  bus.subscribe(ViewerEvent.FRAME_REQUESTED, (frame) => published.push(['frame', frame]));
  const panel = new PerceptionPanel(new FakeDocument(), bus);
  return { panel, published, root: panel.panel.element };
}

const scene = (trees) => ({ description: { planTrees: trees }, objects: { named: () => [{ key: 'k-milk', name: 'milk' }] } });

test('a recorded plan yields its perception steps with the action they belong to', () => {
  const [step] = perceptionSteps(flattened(TREES));
  assert.equal(step.identifier, 'n3');
  assert.equal(step.action, 'DetectAction');
  assert.deepEqual(step.parameters, { technique: 'TYPES', object_sem_annotation: 'Milk' });
  assert.deepEqual(step.perceived, ['k-milk']);
  assert.equal(step.start, 40);
  assert.equal(step.robot, 'PR2 1');
  assert.equal(perceptionSteps(flattened([TREES[0][PlanNodeKey.CHILDREN][0]])).length, 0);
});

test('nodes recorded without identities are named by their place in the plan', () => {
  const strip = (node) => {
    const { [PlanNodeKey.IDENTIFIER]: _, ...rest } = node;
    return { ...rest, [PlanNodeKey.CHILDREN]: (node[PlanNodeKey.CHILDREN] ?? []).map(strip) };
  };
  const [step] = perceptionSteps(flattened(TREES.map(strip)));
  assert.equal(step.identifier, '0.1.0');
  assert.equal(step.action, 'DetectAction');
});

test('a reported object lights up and a step with frames replays its moment', () => {
  const { panel, published, root } = openPanel();
  panel.show(scene(TREES), 'planTrees');
  const buttons = root.findAll((element) => element.tagName === 'BUTTON');
  const seen = buttons.find((button) => button.dataset.key === 'k-milk');
  assert.equal(seen.textContent, 'milk');
  seen.dispatch('click');
  buttons.find((button) => button.textContent.includes('Replay')).dispatch('click');
  assert.deepEqual(published, [['highlight', ['k-milk']], ['frame', 40]]);
});

test('a failed step of the live plan says why it saw nothing', () => {
  const { panel, root } = openPanel();
  panel.showLive({
    [LivePlanKey.NODES]: [
      { [LivePlanNodeKey.IDENTIFIER]: 'a', [LivePlanNodeKey.LABEL]: 'DetectAction', [LivePlanNodeKey.STATUS]: 'FAILED', [LivePlanNodeKey.PARAMETERS]: { technique: 'TYPES' } },
      { [LivePlanNodeKey.IDENTIFIER]: 'b', [LivePlanNodeKey.PARENT]: 'a', [LivePlanNodeKey.LABEL]: 'DetectingMotion', [LivePlanNodeKey.STATUS]: 'FAILED', [LivePlanNodeKey.PERCEIVED]: [], [LivePlanNodeKey.REASON]: 'The perception source reported no Milk.' },
    ],
  });
  assert.equal(panel.steps.length, 1);
  const entry = root.findAll((element) => element.className === 'perception-step')[0];
  assert.equal(entry.dataset.status, 'FAILED');
  assert.ok(entry.findAll((element) => element.textContent === 'The perception source reported no Milk.').length);
});

test('without perception steps the panel says where they would come from', () => {
  const { panel, root } = openPanel();
  panel.show(scene([TREES[0][PlanNodeKey.CHILDREN][0]]), 'planTrees');
  assert.ok(root.findAll((element) => element.textContent === NO_PERCEPTION).length);
  panel.showLive({ [LivePlanKey.NODES]: [{ [LivePlanNodeKey.IDENTIFIER]: 'b', [LivePlanNodeKey.LABEL]: 'DetectingMotion', [LivePlanNodeKey.STATUS]: 'RUNNING', [LivePlanNodeKey.PERCEIVED]: [] }] });
  assert.ok(root.findAll((element) => element.textContent === NOTHING_REPORTED).length);
});
