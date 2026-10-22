import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { AppearanceKey, CatalogKey, DraftKey, InstanceKey, LimitsKey, LinkOffsetKey, NoticeKey, PROTOCOL_VERSION, ResourceKey } from 'cramera-viewer/protocol.js';
import { DraftCheck, InvalidDraft, UNIT_SCALE } from '../../src/cramera_scene_builder/web/builder/draft-check.js';
import {
  DraftState,
  DUPLICATE_OFFSET,
  HISTORY_LIMIT,
  LockedReference,
  UnknownInstance,
  UnknownResource,
  UNTITLED_DRAFT,
} from '../../src/cramera_scene_builder/web/builder/draft-state.js';

const read = (name) => JSON.parse(readFileSync(new URL(`dataset/${name}`, import.meta.url), 'utf8'));
const catalog = read('catalog.json');
const resources = catalog[CatalogKey.RESOURCES];
const check = () => new DraftCheck(catalog[CatalogKey.LIMITS], catalog[CatalogKey.DEFAULT_APPEARANCE]);

function state(draft) {
  const created = new DraftState(check(), draft);
  created.setResources(resources);
  return created;
}

// %% check

test('a draft takes the defaults of the fields it leaves out', () => {
  const draft = check().draft(read('draft.json'));
  const [cabinet, scan] = draft[DraftKey.INSTANCES];
  assert.equal(draft[DraftKey.FORMAT_VERSION], PROTOCOL_VERSION);
  assert.deepEqual(draft[DraftKey.NOTICES], []);
  assert.deepEqual(cabinet[InstanceKey.SCALE], UNIT_SCALE);
  assert.equal(cabinet[InstanceKey.POINT_CLOUD], undefined);
  assert.deepEqual(scan[InstanceKey.POINT_CLOUD], { ...catalog[CatalogKey.DEFAULT_APPEARANCE], [AppearanceKey.LOCKED]: false });
});

test('a draft without a version is read as the current version', () => {
  const draft = read('draft.json');
  delete draft[DraftKey.FORMAT_VERSION];
  assert.equal(check().draft(draft)[DraftKey.FORMAT_VERSION], PROTOCOL_VERSION);
});

for (const name of [
  'next_major_version',
  'unknown_instance_field',
  'prototype_joint',
  'negative_scale',
  'short_position',
  'faint_reference',
  'duplicate_identity',
  'blank_name',
  'too_many_instances',
]) {
  test(`a draft with ${name.replaceAll('_', ' ')} is refused`, () => {
    assert.throws(() => check().draft(read(`invalid/${name}.json`)), InvalidDraft);
  });
}

test('a refusal names where the refused value sits', () => {
  const draft = read('invalid/negative_scale.json');
  const identifier = draft[DraftKey.INSTANCES][0][InstanceKey.IDENTIFIER];
  assert.throws(
    () => check().draft(draft),
    (thrown) => thrown instanceof InvalidDraft && thrown.location === `${DraftKey.INSTANCES}.${identifier}.${InstanceKey.SCALE}`,
  );
});

// %% editing

test('placing a resource adds an instance at the origin with the resource notices', () => {
  const edited = state();
  const cabinet = resources[0];
  const instance = edited.add(cabinet[ResourceKey.IDENTIFIER]);
  assert.equal(instance[InstanceKey.NAME], cabinet[ResourceKey.NAME]);
  assert.deepEqual(instance[InstanceKey.POSITION], [0, 0, 0]);
  assert.deepEqual(edited.draft[DraftKey.NOTICES].map((notice) => notice[NoticeKey.ASSET]), cabinet[ResourceKey.NOTICES].map((notice) => notice[NoticeKey.ASSET]));
});

test('a placed point cloud is shown with the default appearance', () => {
  const edited = state();
  const instance = edited.add(resources[3][ResourceKey.IDENTIFIER], { name: 'room', scale: [0.01, 0.01, 0.01] });
  assert.deepEqual(instance[InstanceKey.POINT_CLOUD], catalog[CatalogKey.DEFAULT_APPEARANCE]);
  assert.deepEqual(instance[InstanceKey.SCALE], [0.01, 0.01, 0.01]);
});

test('placing a resource the catalog does not offer is refused', () => {
  assert.throws(() => state().add('library/missing.urdf'), UnknownResource);
});

test('new instances take identities no instance has', () => {
  const edited = state(read('draft.json'));
  const first = edited.add(resources[1][ResourceKey.IDENTIFIER]);
  const second = edited.add(resources[1][ResourceKey.IDENTIFIER]);
  const identities = edited.draft[DraftKey.INSTANCES].map((instance) => instance[InstanceKey.IDENTIFIER]);
  assert.notEqual(first[InstanceKey.IDENTIFIER], second[InstanceKey.IDENTIFIER]);
  assert.equal(new Set(identities).size, identities.length);
});

test('a duplicate stands beside its original under a new identity', () => {
  const edited = state(read('draft.json'));
  const original = edited.instance('cabinet-1');
  const copy = edited.duplicate('cabinet-1');
  assert.notEqual(copy[InstanceKey.IDENTIFIER], original[InstanceKey.IDENTIFIER]);
  assert.equal(copy[InstanceKey.POSITION][0], original[InstanceKey.POSITION][0] + DUPLICATE_OFFSET);
  assert.deepEqual(copy[InstanceKey.LINK_OFFSETS], original[InstanceKey.LINK_OFFSETS]);
});

test('moving a link keeps its offset apart from the instance placement', () => {
  const edited = state(read('draft.json'));
  const before = edited.instance('cabinet-1');
  edited.place('cabinet-1', { position: [0, 0.1, 0], rotation: [0, 0, 0.5] }, 'door');
  const after = edited.instance('cabinet-1');
  assert.deepEqual(after[InstanceKey.LINK_OFFSETS].door, { [LinkOffsetKey.POSITION]: [0, 0.1, 0], [LinkOffsetKey.ROTATION]: [0, 0, 0.5] });
  assert.deepEqual(after[InstanceKey.POSITION], before[InstanceKey.POSITION]);
  edited.resetLink('cabinet-1', 'door');
  assert.equal(edited.instance('cabinet-1')[InstanceKey.LINK_OFFSETS].door, undefined);
});

test('a locked reference keeps its placement and scale', () => {
  const edited = state(read('draft.json'));
  edited.setAppearance('scan', { [AppearanceKey.LOCKED]: true });
  assert.throws(() => edited.place('scan', { position: [1, 0, 0], rotation: [0, 0, 0] }), LockedReference);
  assert.throws(() => edited.setScale('scan', [1, 1, 1]), LockedReference);
  edited.setAppearance('scan', { [AppearanceKey.LOCKED]: false, [AppearanceKey.OPACITY]: 0.3 });
  edited.setScale('scan', [1, 1, 1]);
  assert.deepEqual(edited.instance('scan')[InstanceKey.SCALE], [1, 1, 1]);
  assert.equal(edited.instance('scan')[InstanceKey.POINT_CLOUD][AppearanceKey.OPACITY], 0.3);
});

test('an appearance beyond the limits is refused and the draft stays', () => {
  const edited = state(read('draft.json'));
  const before = edited.draft;
  assert.throws(() => edited.setAppearance('scan', { [AppearanceKey.POINT_SIZE]: catalog[CatalogKey.LIMITS][LimitsKey.MAXIMUM_POINT_SIZE] * 2 }), InvalidDraft);
  assert.deepEqual(edited.draft, before);
});

test('an appearance of a model is refused', () => {
  assert.throws(() => state(read('draft.json')).setAppearance('cabinet-1', { [AppearanceKey.VISIBLE]: false }), InvalidDraft);
});

test('editing an instance the draft does not hold is refused', () => {
  assert.throws(() => state().renameInstance('missing', 'name'), UnknownInstance);
  assert.throws(() => state().duplicate('missing'), UnknownInstance);
});

test('joints, names and removal are single steps', () => {
  const edited = state(read('draft.json'));
  edited.setJoint('cabinet-1', 'slide', 0.3);
  edited.renameInstance('cabinet-1', 'tall cabinet');
  edited.rename('Kitchen');
  edited.remove('scan');
  const draft = edited.draft;
  assert.equal(draft[DraftKey.INSTANCES][0][InstanceKey.JOINT_POSITIONS].slide, 0.3);
  assert.equal(draft[DraftKey.INSTANCES][0][InstanceKey.NAME], 'tall cabinet');
  assert.equal(draft[DraftKey.NAME], 'Kitchen');
  assert.equal(draft[DraftKey.INSTANCES].length, 1);
});

// %% history

test('undo and redo walk the history of steps', () => {
  const edited = state();
  const changes = [];
  edited.subscribe((draft) => changes.push(draft[DraftKey.NAME]));
  edited.rename('First');
  edited.rename('Second');
  assert.equal(edited.undo(), true);
  assert.equal(edited.draft[DraftKey.NAME], 'First');
  assert.equal(edited.redo(), true);
  assert.equal(edited.draft[DraftKey.NAME], 'Second');
  assert.deepEqual(changes, ['First', 'Second', 'First', 'Second']);
});

test('a new step after an undo drops the undone steps', () => {
  const edited = state();
  edited.rename('First');
  edited.undo();
  edited.rename('Other');
  assert.equal(edited.canRedo, false);
  assert.equal(edited.redo(), false);
});

test('a change that changes nothing is no step', () => {
  const edited = state();
  edited.rename(UNTITLED_DRAFT);
  assert.equal(edited.canUndo, false);
  assert.equal(edited.undo(), false);
});

test('the history keeps a bounded number of steps', () => {
  const edited = state();
  for (let step = 0; step <= HISTORY_LIMIT; step += 1) edited.rename(`Step ${step}`);
  let undone = 0;
  while (edited.undo()) undone += 1;
  assert.equal(undone, HISTORY_LIMIT);
});

test('resetting starts a history of its own', () => {
  const edited = state();
  edited.rename('First');
  edited.reset(read('draft.json'));
  assert.equal(edited.canUndo, false);
  assert.equal(edited.draft[DraftKey.NAME], read('draft.json')[DraftKey.NAME]);
});

test('an unsubscribed listener hears no more changes', () => {
  const edited = state();
  const heard = [];
  const unsubscribe = edited.subscribe((draft) => heard.push(draft));
  unsubscribe();
  edited.rename('Quiet');
  assert.equal(heard.length, 0);
});

test('an export is the checked draft as JSON', () => {
  const edited = state(read('draft.json'));
  assert.deepEqual(JSON.parse(edited.exportText()), edited.draft);
});

test('a copy of the draft does not reach into the state', () => {
  const edited = state(read('draft.json'));
  const copy = edited.draft;
  copy[DraftKey.INSTANCES][0][InstanceKey.POSITION][0] = 99;
  assert.notEqual(edited.instance('cabinet-1')[InstanceKey.POSITION][0], 99);
});
