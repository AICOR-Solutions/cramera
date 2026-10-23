import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { ConstraintObservationKey, DeclaredFieldKey, PlanNodeKey, SceneKey } from 'cramera-viewer/protocol.js';
import { RecordedPlans, RecordedStep } from '../../src/cramera_plan_builder/web/builder/recorded-plan.js';
import { RecordedPlanView } from '../../src/cramera_plan_builder/web/builder/recorded-plan-view.js';
import { FakeDocument } from 'cramera-testing/fake-document.mjs';

const ROOTS = JSON.parse(readFileSync(new URL('dataset/recorded_step_details.json', import.meta.url), 'utf8'))[SceneKey.PLAN_TREES];
const [TORSO, PICK_UP] = ROOTS[0][PlanNodeKey.CHILDREN];

const cardOf = (element, node) => element.findAll((child) => child.className === 'step').find((card) => card.dataset.node === node[PlanNodeKey.IDENTIFIER]);
const byClass = (element, className) => element.findAll((child) => child.className === className);
const outputs = (element) => element.findAll((child) => child.tagName === 'OUTPUT');
const shownView = () => {
  const view = new RecordedPlanView(new FakeDocument(), () => {});
  view.show(ROOTS);
  return view;
};

// %% fields of a recorded step

test('a step lists every field its action declares, in order, with the value it was given', () => {
  const pickUp = RecordedPlans.of(ROOTS).plans[0].steps[1];
  const declared = PICK_UP[PlanNodeKey.FIELDS];
  assert.deepEqual(
    pickUp.fields().map((field) => [field.label, field.required, field.value, field.default]),
    declared.map((entry) => [
      RecordedStep.fieldWords(entry[DeclaredFieldKey.NAME]),
      entry[DeclaredFieldKey.REQUIRED],
      PICK_UP[PlanNodeKey.PARAMETERS][entry[DeclaredFieldKey.NAME]] ?? null,
      entry[DeclaredFieldKey.DEFAULT] ?? null,
    ]),
  );
});

test('a field left at its default reads as its default', () => {
  const fields = RecordedPlans.of(ROOTS).plans[0].steps[1].fields();
  const given = fields.find((field) => field.value !== null);
  const named = fields.find((field) => field.value === null && field.default !== null);
  const unnamed = fields.find((field) => field.value === null && field.default === null);
  assert.equal(given.text(), given.value);
  assert.notEqual(named.text(), unnamed.text());
  assert.ok(named.text().includes(named.default));
  assert.equal(given.isDefault(), false);
  assert.equal(named.isDefault(), true);
});

test('a step recorded before actions declared their fields has none', () => {
  const { [PlanNodeKey.FIELDS]: fields, ...older } = PICK_UP;
  assert.deepEqual(new RecordedStep(older, 1).fields(), []);
});

// %% card details

test('a card shows the required fields and folds the others under more options', () => {
  const card = cardOf(shownView().element, PICK_UP);
  const fields = RecordedPlans.of(ROOTS).plans[0].steps[1].fields();
  const [shown] = byClass(card, 'step-parameters');
  const [more] = byClass(card, 'more-options');
  assert.deepEqual(outputs(shown).map((output) => output.textContent), fields.filter((field) => field.required).map((field) => field.text()));
  assert.deepEqual(outputs(more).map((output) => output.textContent), fields.filter((field) => !field.required).map((field) => field.text()));
  assert.equal(more.tagName, 'DETAILS');
  assert.equal(more.open, false);
  assert.equal(outputs(more).filter((output) => output.className === 'default').length, fields.filter((field) => !field.required && field.isDefault()).length);
});

test('a step whose action declares no optional field has no more options', () => {
  assert.deepEqual(byClass(cardOf(shownView().element, TORSO), 'more-options'), []);
});

test('unfolded options stay unfolded while the playhead moves', () => {
  const view = shownView();
  const [more] = byClass(cardOf(view.element, PICK_UP), 'more-options');
  more.open = true;
  view.showFrame(PICK_UP[PlanNodeKey.START]);
  view.showFrame(PICK_UP[PlanNodeKey.END] + 1);
  assert.equal(byClass(cardOf(view.element, PICK_UP), 'more-options')[0], more);
  assert.equal(more.open, true);
});

test('unfolding the options does not jump to the step', () => {
  const sought = [];
  const view = new RecordedPlanView(new FakeDocument(), (frame) => sought.push(frame));
  view.show(ROOTS);
  const [more] = byClass(cardOf(view.element, PICK_UP), 'more-options');
  let stopped = false;
  more.dispatch('click', { stopPropagation: () => { stopped = true; } });
  assert.equal(stopped, true);
  assert.deepEqual(sought, []);
});

test('a card shows the constraints attached to its step with their monitors', () => {
  const card = cardOf(shownView().element, PICK_UP);
  const [chip] = byClass(card, 'chip');
  const [constraint] = PICK_UP[PlanNodeKey.CONSTRAINTS];
  assert.match(chip.innerText, new RegExp(constraint[ConstraintObservationKey.TEXT]));
  assert.equal(byClass(chip, 'badge')[0].textContent, constraint[ConstraintObservationKey.MONITOR]);
  assert.equal(byClass(chip, 'observation')[0].dataset.observation, constraint[ConstraintObservationKey.OBSERVATION]);
  assert.deepEqual(byClass(cardOf(shownView().element, TORSO), 'chip'), []);
});
