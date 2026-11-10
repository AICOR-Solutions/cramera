import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { MonitorObservation, PerceptionImageKey, PlanStepKey, RunStatusKey, StepState } from 'cramera-viewer/protocol.js';
import { Elements } from '../../src/cramera_plan_builder/web/builder/elements.js';
import { RunProgress, RunView, RunViewClass } from '../../src/cramera_plan_builder/web/builder/run-view.js';
import { FakeDocument } from 'cramera-testing/fake-document.mjs';

/**
 * Event sequences recorded from runs in MuJoCo: the sort template run through the plan
 * builder, a run whose red cube was nudged once detected and whose blue cube was taken
 * away, and a pick a low workspace stopped.
 */
const RECORDED = JSON.parse(readFileSync(new URL('dataset/run_events.json', import.meta.url), 'utf8'));

/**
 * @param {string} name A recorded run.
 * @returns {RunProgress} Its progress, its steps labelled by their identities.
 */
const progressOf = (name) => {
  const recorded = RECORDED[name];
  const steps = recorded.steps.map((identifier) => ({ [PlanStepKey.IDENTIFIER]: identifier }));
  return RunProgress.of(steps, (step) => `label of ${step[PlanStepKey.IDENTIFIER]}`, { [RunStatusKey.EVENTS]: recorded.events });
};

/**
 * @param {RunProgress} progress A run's progress.
 * @param {Array<Object>=} images The camera images shown.
 * @returns {import('cramera-testing/fake-document.mjs').FakeElement} The rendered view.
 */
const rendered = (progress, images = []) => {
  const view = new RunView(new Elements(new FakeDocument()));
  view.render(progress, images);
  return view.element;
};

const byClass = (root, name) => root.findAll((element) => element.className === name);

// %% progress

test('a sorted run ends with every step done and each cube perceived in its color', () => {
  const progress = progressOf('sort');
  assert.ok(progress.steps().every((step) => step.state === StepState.DONE));
  assert.deepEqual(
    progress.perceived.map((seen) => [seen.target, seen.color]),
    [
      ['red_cube', 'red'],
      ['yellow_cube', 'yellow'],
      ['blue_cube', 'blue'],
    ],
  );
  assert.equal(progress.safety, MonitorObservation.HOLDS);
  assert.match(progress.summary(), /^13 of 13 steps done\.$/);
});

test('a step retried after its cube moved is done on its second attempt, with the reason logged', () => {
  const progress = progressOf('retry');
  const pick = progress.step('step_3');
  assert.equal(pick.state, StepState.DONE);
  assert.equal(pick.attempt, 2);
  assert.ok(pick.arm);
  assert.deepEqual(pick.badges(), ['look-at: in view ✓']);
  assert.ok(progress.log.some((line) => line.startsWith('3. label of step_3: attempt 1/3 failed, retrying: red_cube lies')));
});

test('a step that used up its attempts fails the run and the summary says why', () => {
  const progress = progressOf('retry');
  const pick = progress.step('step_5');
  assert.equal(pick.state, StepState.FAILED);
  assert.equal(pick.attempt, 3);
  assert.match(pick.reason, /blue_cube was not detected on the table again/);
  assert.match(progress.summary(), /^Aborted at 5\. label of step_5: blue_cube was not detected/);
  assert.equal(progress.step('step_6').state, StepState.PENDING);
});

test('a safety stop fails its step, violates the safety monitor and is logged', () => {
  const progress = progressOf('safetyStop');
  assert.equal(progress.step('step_2').state, StepState.FAILED);
  assert.equal(progress.safety, MonitorObservation.VIOLATED);
  assert.equal(progress.safetyStop, 'Left arm workspace');
  assert.match(progress.summary(), /^Stopped by a safety limit in 2\. label of step_2: Left arm workspace\./);
  assert.equal(progress.log.at(-1), 'Safety stop in 2. label of step_2: Left arm workspace; the robot holds.');
});

test('every event is a line of the log', () => {
  for (const name of Object.keys(RECORDED)) assert.equal(progressOf(name).log.length, RECORDED[name].events.length);
});

// %% rendering

test('the step list shows each step with its state, arm and attempt', () => {
  const view = rendered(progressOf('retry'));
  const steps = byClass(view, RunViewClass.STEP);
  assert.deepEqual(
    steps.map((step) => [step.dataset.step, step.dataset.state]),
    [
      ['step_1', StepState.DONE],
      ['step_2', StepState.DONE],
      ['step_3', StepState.DONE],
      ['step_4', StepState.DONE],
      ['step_5', StepState.FAILED],
      ['step_6', StepState.PENDING],
    ],
  );
  const [, , pick, , failed] = steps;
  assert.equal(byClass(pick, RunViewClass.ATTEMPT)[0].textContent, 'attempt 2/3');
  assert.match(byClass(pick, RunViewClass.ARM)[0].textContent, /^(left|right) arm$/);
  assert.match(byClass(failed, RunViewClass.REASON)[0].textContent, /was not detected on the table again/);
});

test('monitor badges show the look-at of a step and the safety monitor of the run', () => {
  const retried = rendered(progressOf('retry'));
  const [lookAt] = byClass(retried, RunViewClass.BADGE);
  assert.equal(lookAt.textContent, 'look-at: in view ✓');
  assert.equal(lookAt.dataset.observation, MonitorObservation.HOLDS);
  const stopped = rendered(progressOf('safetyStop'));
  const [safety] = byClass(byClass(stopped, RunViewClass.BADGES)[0], RunViewClass.BADGE);
  assert.equal(safety.textContent, 'safety: limit violated ✗');
  assert.equal(safety.dataset.observation, MonitorObservation.VIOLATED);
});

test('the perceived cubes show their colors and the log every event', () => {
  const progress = progressOf('sort');
  const view = rendered(progress);
  assert.deepEqual(
    byClass(view, RunViewClass.OBJECT).map((chip) => chip.dataset.color),
    ['red', 'yellow', 'blue'],
  );
  const log = byClass(view, RunViewClass.LOG)[0];
  assert.deepEqual(
    log.children.map((line) => line.textContent),
    progress.log,
  );
});

test('the camera panel shows the latest perception images or says none was taken', () => {
  const none = rendered(progressOf('sort'));
  assert.match(byClass(none, RunViewClass.CAMERA)[0].innerText, /No camera image yet/);
  const image = { [PerceptionImageKey.TITLE]: 'camera', [PerceptionImageKey.FILE]: 'node_4_0', url: '/live/perception_image?key=node_4_0' };
  const camera = byClass(rendered(progressOf('sort'), [image]), RunViewClass.CAMERA)[0];
  const [picture] = camera.findAll((element) => element.tagName === 'IMG');
  assert.equal(picture.src, image.url);
  assert.match(camera.innerText, /latest perception step ended: camera/);
});
