import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  PerceptionReportKey,
  PlanStepKey,
  ReportedObjectKey,
  ReportedObjectVerdict,
  RunEventKey,
  RunEventKind,
  RunStatusKey,
  StepState,
  SurfaceDepthKey,
} from 'cramera-viewer/protocol.js';
import { Elements } from '../../src/cramera_plan_builder/web/builder/elements.js';
import { PerceptionViewClass, askedText, objectText, perceptionSentence } from '../../src/cramera_plan_builder/web/builder/perception-view.js';
import { RunProgress, RunView, RunViewClass } from '../../src/cramera_plan_builder/web/builder/run-view.js';
import { FakeDocument } from 'cramera-testing/fake-document.mjs';

/**
 * The run of the red cube's pick on the real table on 2026-11-12: the cube was seen
 * 19 cm from where the plan was validated, beside the table top reported as two grey
 * objects, then three table-wide searches found nothing and the step gave up.
 */
const seen = (position, colors, verdict, distance = null) => ({
  [ReportedObjectKey.POSITION]: position,
  [ReportedObjectKey.SIZE]: [0.066, 0.061, 0.022],
  [ReportedObjectKey.COLORS]: colors,
  [ReportedObjectKey.TYPE]: '',
  [ReportedObjectKey.VERDICT]: verdict,
  [ReportedObjectKey.DISTANCE]: distance,
});

const grounded = {
  [PerceptionReportKey.TARGET]: 'red_cube',
  [PerceptionReportKey.TYPE]: 'plannedgraspable',
  [PerceptionReportKey.COLOR]: 'red',
  [PerceptionReportKey.BOX]: [[0.525, 0.03, 0.83], [0.675, 0.18, 0.98]],
  [PerceptionReportKey.TABLE_WIDE]: false,
  [PerceptionReportKey.GROUNDED]: [0.6, 0.105, 0.905],
  [PerceptionReportKey.TOLERANCE]: 0.02,
  [PerceptionReportKey.ANSWERED]: true,
  [PerceptionReportKey.OBJECTS]: [
    seen([0.79, 0.145, 0.905], ['red'], ReportedObjectVerdict.OUTSIDE_BOX, 0.194),
    seen([0.82, 0.3, 0.9], ['grey'], ReportedObjectVerdict.WRONG_COLOR, 0.28),
  ],
  [PerceptionReportKey.SUMMARY]: 'red_cube was seen 19 cm from where the plan was validated, outside the search within 7.5 cm of where the plan was validated.',
};

const tableWide = {
  [PerceptionReportKey.TARGET]: null,
  [PerceptionReportKey.TYPE]: 'plannedgraspable',
  [PerceptionReportKey.COLOR]: 'red',
  [PerceptionReportKey.BOX]: [[0.0, -0.8, 0.8], [1.18, 0.8, 1.1]],
  [PerceptionReportKey.TABLE_WIDE]: true,
  [PerceptionReportKey.ANSWERED]: true,
  [PerceptionReportKey.OBJECTS]: [],
  [PerceptionReportKey.SUMMARY]: 'A table-wide search found no red object.',
};

const perception = (report) => ({ [RunEventKey.KIND]: RunEventKind.PERCEPTION, [RunEventKey.STEP]: 'step_2', [RunEventKey.PERCEPTION]: report });

const failedRun = () => RunProgress.of(
  [{ [PlanStepKey.IDENTIFIER]: 'step_1' }, { [PlanStepKey.IDENTIFIER]: 'step_2' }],
  (step) => `label of ${step[PlanStepKey.IDENTIFIER]}`,
  {
    [RunStatusKey.EVENTS]: [
      perception(grounded),
      perception(tableWide),
      perception(tableWide),
      perception(tableWide),
      { [RunEventKey.KIND]: RunEventKind.STEP, [RunEventKey.STEP]: 'step_2', [RunEventKey.STATE]: StepState.FAILED, [RunEventKey.ATTEMPT]: 3, [RunEventKey.ATTEMPTS]: 3, [RunEventKey.REASON]: 'red_cube was not detected on the table again' },
    ],
  },
);

const rendered = (progress) => {
  const view = new RunView(new Elements(new FakeDocument()));
  view.render(progress);
  return view.element;
};

const byClass = (root, name) => root.findAll((element) => element.className === name);

test('a step whose detections failed says why in one sentence beside it', () => {
  const view = rendered(failedRun());
  const failed = byClass(view, RunViewClass.STEP)[1];
  assert.equal(
    byClass(failed, PerceptionViewClass.SENTENCE)[0].textContent,
    'Perception: red_cube was seen 19 cm from where the plan was validated, outside the search within 7.5 cm of where the plan was validated; then a table-wide search found no red object (3 times).',
  );
});

test('every report shows what was asked and every object with why it was not taken', () => {
  const view = rendered(failedRun());
  const reports = byClass(view, PerceptionViewClass.REPORT);
  assert.equal(reports.length, 4);
  assert.equal(byClass(reports[0], PerceptionViewClass.ASKED)[0].textContent, 'Searched within 7.5 cm of (0.60, 0.10, 0.91) m (planned), 2 cm allowed.');
  const objects = byClass(reports[0], PerceptionViewClass.OBJECT);
  assert.deepEqual(objects.map((item) => item.dataset.verdict), [ReportedObjectVerdict.OUTSIDE_BOX, ReportedObjectVerdict.WRONG_COLOR]);
  assert.match(objects[0].innerText, /red, 6\.6 × 6\.1 × 2\.2 cm, \(0\.79, 0\.14, 0\.91\) m, 19\.4 cm off: outside the search/);
});

test('an empty answer is shown as empty, with the query', () => {
  const view = rendered(failedRun());
  const last = byClass(view, PerceptionViewClass.REPORT).at(-1);
  assert.equal(last.open, true);
  assert.match(byClass(last, PerceptionViewClass.ASKED)[0].textContent, /whole table/);
  assert.match(byClass(last, PerceptionViewClass.EMPTY)[0].textContent, /Nothing reported/);
});

test('a report the person opened or closed stays so when the run view renders again', () => {
  const view = new RunView(new Elements(new FakeDocument()));
  view.render(failedRun());
  const reports = () => byClass(view.element, PerceptionViewClass.REPORT);
  for (const report of [reports()[0], reports().at(-1)]) {
    const summary = report.findAll((element) => element.tagName?.toLowerCase() === 'summary')[0];
    summary.click();
    report.open = !report.open;
  }
  view.render(failedRun());
  assert.deepEqual(reports().map((report) => report.open), [true, false, false, false]);
});

test('the log says what each detection found', () => {
  assert.ok(failedRun().log.includes('2. label of step_2: A table-wide search found no red object.'));
});

test('no report makes no sentence', () => {
  assert.equal(perceptionSentence([]), null);
});

/**
 * The red cube taken where it was validated, reported `depth` metres inside the table.
 */
const sunk = (depth, verdict = ReportedObjectVerdict.ACCEPTED) => ({
  ...seen([0.6, 0.105, 0.905 - depth], ['red'], verdict, 0.004),
  [ReportedObjectKey.INSIDE_SURFACE]: {
    [SurfaceDepthKey.SURFACE]: 'table',
    [SurfaceDepthKey.DEPTH]: depth,
  },
});

test('a cube taken a few millimetres inside the table says it was raised onto it', () => {
  assert.match(objectText(sunk(0.004)), /: used; 4 mm inside the table, raised$/);
});

test('a cube taken centimetres inside the table says it was raised onto it', () => {
  assert.match(objectText(sunk(0.04)), /: used; 40 mm inside the table, raised$/);
});

test('an object not taken says nothing of the table', () => {
  assert.doesNotMatch(objectText(sunk(0.004, ReportedObjectVerdict.WRONG_COLOR)), /inside the table/);
});

/**
 * The pick of the red cube planned again where a table-wide search found it, 19 cm from
 * where the plan was validated, its next detection finding it there.
 */
const plannedAgain = {
  ...grounded,
  [PerceptionReportKey.LOOKED_FOR]: 'the red cube',
  [PerceptionReportKey.TYPE]: 'plannedgraspablefromabove',
  [PerceptionReportKey.BOX]: [[0.715, 0.07, 0.83], [0.865, 0.22, 0.98]],
  [PerceptionReportKey.GROUNDED]: [0.79, 0.145, 0.905],
  [PerceptionReportKey.VALIDATED]: [0.6, 0.105, 0.905],
  [PerceptionReportKey.OBJECTS]: [seen([0.79, 0.145, 0.905], ['red'], ReportedObjectVerdict.ACCEPTED, 0.0)],
};

test('a box looked in that reaches unequally far along x and y says how far along each', () => {
  const wide = { ...grounded, [PerceptionReportKey.BOX]: [[0.525, 0.005, 0.83], [0.675, 0.205, 0.98]] };
  assert.match(askedText(wide), /^Searched within 7\.5 × 10 cm of \(0\.60, 0\.10, 0\.91\) m /);
});

test('what was asked never names the type checked', () => {
  const asked = askedText(plannedAgain);
  assert.match(asked, /^Searched within /);
  assert.doesNotMatch(asked, /graspable/i);
});

test('a step planned again says it looked around where the object was last seen', () => {
  assert.equal(
    askedText(plannedAgain),
    'Searched within 7.5 cm of (0.79, 0.14, 0.91) m (last seen), 2 cm allowed.',
  );
});

test('an object seen by a step planned again is measured from where it was last seen', () => {
  const [cube] = plannedAgain[PerceptionReportKey.OBJECTS];
  assert.match(objectText(cube, plannedAgain), /, 0 cm from last seen: used$/);
});

test('an object of another kind says so without its type name', () => {
  const bowl = { ...seen([0.6, 0.1, 0.905], ['red'], ReportedObjectVerdict.WRONG_TYPE, 0.005), [ReportedObjectKey.TYPE]: 'PlannedGraspableFromAbove' };
  const text = objectText(bowl, grounded);
  assert.doesNotMatch(text, /planned/i);
  assert.match(text, /: wrong type$/);
});

/**
 * The pick of the red cube on a real table: its check saw the cube 34 cm away, outside
 * the box looked in, a table-wide search found it, and the check of the step planned
 * again there used it.
 */
const NOT_USED = 'The red cube seen 34 cm from where the plan was validated was not used: the step acts only on the red cube found inside the box it looked in.';

const notUsed = {
  ...grounded,
  [PerceptionReportKey.OBJECTS]: [seen([0.94, 0.105, 0.905], ['red'], ReportedObjectVerdict.OUTSIDE_BOX, 0.34)],
  [PerceptionReportKey.SUMMARY]: 'Checked before the step moved that the object still lies where the plan expects it: the red cube was seen 34 cm from where the plan was validated, outside the search within 7.5 cm of where the plan was validated.',
  [PerceptionReportKey.WARNINGS]: [NOT_USED],
};

const foundAgain = {
  ...plannedAgain,
  [PerceptionReportKey.SUMMARY]: 'Checked before the step moved that the object still lies where the plan expects it: the red cube was found 0 cm from where it was last seen, 34 cm from where the plan was validated.',
  [PerceptionReportKey.WARNINGS]: [],
};

const regroundedRun = () => RunProgress.of(
  [{ [PlanStepKey.IDENTIFIER]: 'step_1' }, { [PlanStepKey.IDENTIFIER]: 'step_2' }],
  (step) => `label of ${step[PlanStepKey.IDENTIFIER]}`,
  { [RunStatusKey.EVENTS]: [perception(notUsed), perception(foundAgain)] },
);

test('a report with a detection not used is marked as a warning and says why', () => {
  const [first, second] = byClass(rendered(regroundedRun()), PerceptionViewClass.REPORT);
  assert.equal(first.dataset.warning, 'true');
  assert.equal(second.dataset.warning, 'false');
  assert.deepEqual(byClass(first, PerceptionViewClass.WARNING).map((element) => element.textContent), [NOT_USED]);
});

test('a report whose detection was not used says which later detection of its step was', () => {
  const [first, second] = byClass(rendered(regroundedRun()), PerceptionViewClass.REPORT);
  assert.equal(byClass(first, PerceptionViewClass.INSTEAD)[0].textContent, `Used instead: ${foundAgain[PerceptionReportKey.SUMMARY]}`);
  assert.equal(byClass(second, PerceptionViewClass.INSTEAD).length, 0);
});

test('the report whose detection was used is marked as used', () => {
  const [first, second] = byClass(rendered(regroundedRun()), PerceptionViewClass.REPORT);
  assert.deepEqual([first.dataset.used, second.dataset.used], ['false', 'true']);
});

test('the log warns of a detection not used', () => {
  assert.ok(regroundedRun().log.includes(`2. label of step_2: ${notUsed[PerceptionReportKey.SUMMARY]} Warning: ${NOT_USED}`));
});

test('an object of the kind looked for outside the box says it was ignored', () => {
  assert.match(objectText(notUsed[PerceptionReportKey.OBJECTS][0], notUsed), /: outside the search$/);
});

/**
 * The red cube used where it was validated, measured 6.1 × 5.6 × 1.7 cm on the real
 * table, though it is a 5 cm cube.
 */
const flattened = {
  ...grounded,
  [PerceptionReportKey.LOOKED_FOR]: 'the red cube',
  [PerceptionReportKey.EXPECTED_SIZE]: [0.05, 0.05, 0.05],
  [PerceptionReportKey.OBJECTS]: [{
    ...seen([0.6, 0.105, 0.905], ['red'], ReportedObjectVerdict.ACCEPTED, 0.0),
    [ReportedObjectKey.SIZE]: [0.061, 0.056, 0.017],
    [ReportedObjectKey.SIZE_DIFFERS]: true,
  }],
};

test('an object measured clearly unlike the object looked for says so', () => {
  assert.match(objectText(flattened[PerceptionReportKey.OBJECTS][0], flattened), /: used; size off \(expected 5 × 5 × 5 cm\)$/);
});

test('an object measured clearly unlike the object looked for is marked', () => {
  const [report] = byClass(rendered(RunProgress.of(
    [{ [PlanStepKey.IDENTIFIER]: 'step_2' }],
    (step) => step[PlanStepKey.IDENTIFIER],
    { [RunStatusKey.EVENTS]: [perception(flattened)] },
  )), PerceptionViewClass.REPORT);
  assert.equal(byClass(report, PerceptionViewClass.OBJECT)[0].dataset.sizeDiffers, 'true');
});

test('an object measured like the object looked for says nothing of its size', () => {
  const [cube] = plannedAgain[PerceptionReportKey.OBJECTS];
  assert.doesNotMatch(objectText(cube, plannedAgain), /measured/);
});
