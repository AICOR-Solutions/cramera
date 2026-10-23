import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { PlanBuilderName, PlanNodeKey, SceneKey, ViewerEvent } from 'cramera-viewer/protocol.js';
import { EventBus } from 'cramera-viewer/core/event-bus.js';
import { PanelHost, SidePanel } from 'cramera-viewer/panels/panel-host.js';
import { RecordedPlans, RecordedStep, StepPhase } from '../../src/cramera_plan_builder/web/builder/recorded-plan.js';
import { RecordedPlanView } from '../../src/cramera_plan_builder/web/builder/recorded-plan-view.js';
import { register } from '../../src/cramera_plan_builder/web/index.js';
import { FakeDocument } from 'cramera-testing/fake-document.mjs';

const ROOTS = JSON.parse(readFileSync(new URL('dataset/recorded_plans.json', import.meta.url), 'utf8'))[SceneKey.PLAN_TREES];
const [TIAGO_PLAN, STRETCH_PLAN] = ROOTS;
const [PARK, NAVIGATE, PICK_UP, PARALLEL, LAST_PARK] = TIAGO_PLAN[PlanNodeKey.CHILDREN];
const PLACE = PARALLEL[PlanNodeKey.CHILDREN][0];
const TIAGO_STEPS = [PARK, NAVIGATE, PICK_UP, PLACE, LAST_PARK];
const PAGE_URL = 'http://localhost/plugins/plan-builder/builder.html';

/**
 * @param {Array<Object>} nodes Plan nodes.
 * @returns {Array<Object>} Copies of them and their descendants without frames, as
 *   recordings written before plan nodes named them.
 */
const withoutFrames = (nodes) =>
  nodes.map(({ [PlanNodeKey.START]: start, [PlanNodeKey.END]: end, ...node }) => ({
    ...node,
    [PlanNodeKey.CHILDREN]: withoutFrames(node[PlanNodeKey.CHILDREN] ?? []),
  }));

const cards = (element) => element.findAll((child) => child.className === 'step');
const cardOf = (element, node) => cards(element).find((card) => card.dataset.node === node[PlanNodeKey.IDENTIFIER]);
const running = (element) => cards(element).filter((card) => card.dataset.phase === StepPhase.RUNNING);

// %% steps of a recorded plan

test('the steps of a plan are its outermost actions, in order', () => {
  const [tiago, stretch] = RecordedPlans.of(ROOTS).plans;
  assert.deepEqual(tiago.steps.map((step) => step.node), TIAGO_STEPS);
  assert.deepEqual(tiago.steps.map((step) => step.number), TIAGO_STEPS.map((_, index) => index + 1));
  assert.deepEqual(stretch.steps.map((step) => step.node), [STRETCH_PLAN]);
});

test('a step is named in words and shows the arm and target it was recorded with', () => {
  assert.equal(RecordedStep.words(PICK_UP[PlanNodeKey.LABEL]), 'Rail Pick Up');
  const [, navigate, pickUp] = RecordedPlans.of(ROOTS).plans[0].steps;
  assert.deepEqual(pickUp.parameters(), [
    { name: PlanNodeKey.ARM, value: PICK_UP[PlanNodeKey.ARM] },
    { name: PlanNodeKey.TARGET, value: PICK_UP[PlanNodeKey.TARGET] },
  ]);
  assert.deepEqual(navigate.parameters(), []);
});

// %% steps at the playhead

test('the running step is the one whose frames hold the playhead, from its first to its last frame', () => {
  const tiago = RecordedPlans.of(ROOTS).plans[0];
  for (const node of TIAGO_STEPS) {
    assert.equal(tiago.stepAt(node[PlanNodeKey.START]).node, node);
    assert.equal(tiago.stepAt(node[PlanNodeKey.END]).node, node);
  }
  assert.equal(tiago.stepAt(Math.floor((PLACE[PlanNodeKey.START] + PLACE[PlanNodeKey.END]) / 2)).node, PLACE);
});

test('no step runs between two steps or after the plan ended', () => {
  const [tiago, stretch] = RecordedPlans.of(ROOTS).plans;
  assert.equal(tiago.stepAt(PARK[PlanNodeKey.END] + 1), null);
  assert.equal(tiago.stepAt(STRETCH_PLAN[PlanNodeKey.START]), null);
  assert.equal(stretch.stepAt(STRETCH_PLAN[PlanNodeKey.START]).node, STRETCH_PLAN);
});

test('a step waits before its first frame, runs within its frames and is done after them', () => {
  const navigate = RecordedPlans.of(ROOTS).plans[0].steps[1];
  assert.equal(navigate.phaseAt(NAVIGATE[PlanNodeKey.START] - 1), StepPhase.WAITING);
  assert.equal(navigate.phaseAt(NAVIGATE[PlanNodeKey.START]), StepPhase.RUNNING);
  assert.equal(navigate.phaseAt(NAVIGATE[PlanNodeKey.END]), StepPhase.RUNNING);
  assert.equal(navigate.phaseAt(NAVIGATE[PlanNodeKey.END] + 1), StepPhase.DONE);
});

test('a plan recorded without step frames has steps but none at any frame', () => {
  const plans = RecordedPlans.of(withoutFrames(ROOTS));
  assert.equal(plans.hasFrames(), false);
  assert.equal(RecordedPlans.of(ROOTS).hasFrames(), true);
  const tiago = plans.plans[0];
  assert.equal(tiago.steps.length, TIAGO_STEPS.length);
  assert.equal(tiago.stepAt(NAVIGATE[PlanNodeKey.START]), null);
  assert.equal(tiago.steps[1].phaseAt(NAVIGATE[PlanNodeKey.START]), null);
});

// %% view

test('the view shows one list of step cards per plan', () => {
  const view = new RecordedPlanView(new FakeDocument(), () => {});
  view.show(ROOTS);
  const lists = view.element.findAll((element) => element.className === 'steps');
  assert.equal(lists.length, ROOTS.length);
  assert.deepEqual(cards(lists[0]).map((card) => card.dataset.node), TIAGO_STEPS.map((node) => node[PlanNodeKey.IDENTIFIER]));
  const name = cardOf(view.element, PICK_UP).findAll((element) => element.className === 'step-name')[0];
  assert.equal(name.textContent, RecordedStep.words(PICK_UP[PlanNodeKey.LABEL]));
  assert.match(cardOf(view.element, PICK_UP).innerText, new RegExp(PICK_UP[PlanNodeKey.TARGET]));
});

test('the card of the step at the playhead is marked running and the others waiting or done', () => {
  const view = new RecordedPlanView(new FakeDocument(), () => {});
  view.show(ROOTS);
  view.showFrame(NAVIGATE[PlanNodeKey.START]);
  assert.deepEqual(running(view.element), [cardOf(view.element, NAVIGATE)]);
  assert.equal(cardOf(view.element, PARK).dataset.phase, StepPhase.DONE);
  assert.equal(cardOf(view.element, PICK_UP).dataset.phase, StepPhase.WAITING);
  const status = (node) => cardOf(view.element, node).findAll((element) => element.className === 'node-status')[0].textContent;
  assert.equal(status(PARK), PARK[PlanNodeKey.STATUS]);
  assert.equal(status(NAVIGATE), StepPhase.RUNNING);
  view.showFrame(STRETCH_PLAN[PlanNodeKey.START]);
  assert.deepEqual(running(view.element), [cardOf(view.element, STRETCH_PLAN)]);
  assert.equal(cardOf(view.element, LAST_PARK).dataset.phase, StepPhase.DONE);
});

test('the view scrolls a step into sight once, when it starts running', () => {
  const view = new RecordedPlanView(new FakeDocument(), () => {});
  view.show(ROOTS);
  view.showFrame(NAVIGATE[PlanNodeKey.START]);
  view.showFrame(NAVIGATE[PlanNodeKey.START] + 1);
  view.showFrame(NAVIGATE[PlanNodeKey.END]);
  assert.equal(cardOf(view.element, NAVIGATE).scrollRequests.length, 1);
  view.showFrame(NAVIGATE[PlanNodeKey.START] - 1);
  view.showFrame(NAVIGATE[PlanNodeKey.START]);
  assert.equal(cardOf(view.element, NAVIGATE).scrollRequests.length, 2);
});

test('a click on a card jumps to the first frame of its step', () => {
  const sought = [];
  const view = new RecordedPlanView(new FakeDocument(), (frame) => sought.push(frame));
  view.show(ROOTS);
  cardOf(view.element, PLACE).dispatch('click');
  assert.deepEqual(sought, [PLACE[PlanNodeKey.START]]);
});

test('a plan recorded without step frames is shown with its final states and a note', () => {
  const view = new RecordedPlanView(new FakeDocument(), () => {});
  view.show(withoutFrames(ROOTS));
  view.showFrame(NAVIGATE[PlanNodeKey.START]);
  assert.deepEqual(running(view.element), []);
  assert.equal(cards(view.element).length, TIAGO_STEPS.length + 1);
  assert.equal(view.element.findAll((element) => element.className === 'empty').length, 1);
  view.show([]);
  assert.equal(cards(view.element).length, 0);
});

// %% panel

/**
 * @returns {{bus: EventBus, panels: PanelHost, panel: Object}} The plugin registered in
 *   a viewer whose first panel is another one.
 */
const registered = () => {
  const document = new FakeDocument();
  const bus = new EventBus();
  const panels = new PanelHost(document.createElement('aside'));
  panels.add(new SidePanel('steps', 'Steps', document.createElement('section')));
  const panel = register({ bus, panels }, document, PAGE_URL);
  return { bus, panels, panel };
};

test('a replayed recording shows its plan in the plan builder panel, following the playhead', () => {
  const { bus, panels, panel } = registered();
  bus.publish(ViewerEvent.SCENE_LOADED, { description: { [SceneKey.PLAN_TREES]: ROOTS } });
  assert.equal(panels.shown, PlanBuilderName.PLUGIN);
  bus.publish(ViewerEvent.FRAME_CHANGED, PICK_UP[PlanNodeKey.START]);
  assert.deepEqual(running(panel.element), [cardOf(panel.element, PICK_UP)]);
  const requested = [];
  bus.subscribe(ViewerEvent.FRAME_REQUESTED, (frame) => requested.push(frame));
  cardOf(panel.element, LAST_PARK).dispatch('click');
  assert.deepEqual(requested, [LAST_PARK[PlanNodeKey.START]]);
  panel.dispose();
  assert.equal(bus.listenerCount(ViewerEvent.FRAME_CHANGED), 0);
});

test('a scene without a recorded plan leaves the shown panel alone', () => {
  const { bus, panels, panel } = registered();
  bus.publish(ViewerEvent.SCENE_LOADED, { description: { [SceneKey.PLAN_TREES]: ROOTS } });
  panels.show('steps');
  bus.publish(ViewerEvent.SCENE_LOADED, { description: {} });
  assert.equal(panels.shown, 'steps');
  assert.equal(cards(panel.element).length, 0);
  panel.dispose();
});
