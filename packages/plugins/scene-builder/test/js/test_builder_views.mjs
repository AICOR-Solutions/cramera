import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { AppearanceKey, CatalogKey, DraftKey, DraftSummaryKey, IndexEntryKey, InstanceKey, NoticeKey, ResourceCategory, ResourceKey } from 'cramera-viewer/protocol.js';
import { DraftCheck } from '../../src/cramera_scene_builder/web/builder/draft-check.js';
import { BuilderHeader, DraftMenu, MenuActions, SourceUnit, ViewToolbar } from '../../src/cramera_scene_builder/web/builder/draft-menu.js';
import { TransformMode } from '../../src/cramera_scene_builder/web/builder/draft-view.js';
import { BuilderAction, DomEvent, Elements } from '../../src/cramera_scene_builder/web/builder/elements.js';
import { DEGREES_PER_RADIAN, InspectorActions, InspectorView, MILLIMETRES_PER_METRE, MissingNumber } from '../../src/cramera_scene_builder/web/builder/inspector-view.js';
import { InstanceList, MISSING_RESOURCE } from '../../src/cramera_scene_builder/web/builder/instance-list.js';
import { CATEGORY_LABELS, LIBRARY_PAGE_SIZE, LibraryView } from '../../src/cramera_scene_builder/web/builder/library-view.js';
import { JointType } from '../../src/cramera_scene_builder/web/builder/placed-instance.js';
import { FakeDocument } from 'cramera-testing/fake-document.mjs';

const read = (name) => JSON.parse(readFileSync(new URL(`dataset/${name}`, import.meta.url), 'utf8'));
const catalog = read('catalog.json');
const resources = catalog[CatalogKey.RESOURCES];
const draft = new DraftCheck(catalog[CatalogKey.LIMITS], catalog[CatalogKey.DEFAULT_APPEARANCE]).draft(read('draft.json'));
const resourceOf = (identifier) => resources.find((resource) => resource[ResourceKey.IDENTIFIER] === identifier);

const byAction = (root, action) => root.findAll((element) => element.dataset.action === action);

/**
 * Records every call of every action.
 */
function recorder(names) {
  const calls = [];
  const callbacks = Object.fromEntries(names.map((name) => [name, (...values) => calls.push([name, ...values])]));
  return { calls, callbacks };
}

const INSPECTOR_ACTIONS = ['rename', 'duplicate', 'remove', 'chooseLink', 'place', 'scale', 'setProportional', 'setAppearance', 'resetLink', 'setJoint', 'noticeUrl'];
const MENU_ACTIONS = ['rename', 'undo', 'redo', 'save', 'newDraft', 'openScene', 'loadDraft', 'importFile', 'exportDraft', 'upload', 'setMode', 'frameSelection', 'frameAll'];

// %% elements

test('disposing elements removes every listener they added', () => {
  const elements = new Elements(new FakeDocument());
  const button = elements.button('Go', BuilderAction.SAVE, () => {});
  const input = elements.input('number', BuilderAction.POSITION, () => {});
  assert.equal(button.listenerCount(DomEvent.CLICK), 1);
  elements.dispose();
  assert.equal(button.listenerCount(DomEvent.CLICK), 0);
  assert.equal(input.listenerCount(DomEvent.CHANGE), 0);
});

test('text is inserted as text', () => {
  const element = new Elements(new FakeDocument()).create('p', '', '<b>bold</b>');
  assert.equal(element.textContent, '<b>bold</b>');
  assert.equal(element.children.length, 0);
});

// %% library

test('the library lists resources and places the clicked one', () => {
  const added = [];
  const library = new LibraryView(new Elements(new FakeDocument()), (identifier) => added.push(identifier));
  library.show(resources);
  const cards = byAction(library.element, BuilderAction.ADD);
  assert.equal(cards.length, resources.length);
  cards[1].dispatch(DomEvent.CLICK);
  assert.deepEqual(added, [resources[1][ResourceKey.IDENTIFIER]]);
});

test('the library filters by category and search words', () => {
  const library = new LibraryView(new Elements(new FakeDocument()), () => {});
  library.show(resources);
  const [search] = byAction(library.element, BuilderAction.SEARCH);
  const [filter] = byAction(library.element, BuilderAction.FILTER);
  filter.value = ResourceCategory.ROBOT;
  filter.dispatch(DomEvent.CHANGE);
  assert.deepEqual(byAction(library.element, BuilderAction.ADD).map((card) => card.title), resources.filter((resource) => resource[ResourceKey.CATEGORY] === ResourceCategory.ROBOT).map((resource) => resource[ResourceKey.IDENTIFIER]));
  filter.value = '';
  search.value = 'DOOR';
  search.dispatch(DomEvent.INPUT);
  assert.deepEqual(library.matching().map((resource) => resource[ResourceKey.NAME]), ['door']);
  assert.deepEqual(Object.keys(CATEGORY_LABELS).filter(Boolean).sort(), Object.values(ResourceCategory).sort());
});

test('the library lists one page and drops the listeners of earlier listings', () => {
  const many = Array.from({ length: LIBRARY_PAGE_SIZE + 1 }, (_, index) => ({ ...resources[2], [ResourceKey.IDENTIFIER]: `library/door-${index}.stl` }));
  const library = new LibraryView(new Elements(new FakeDocument()), () => {});
  library.show(many);
  const first = byAction(library.element, BuilderAction.ADD)[0];
  library.show(resources);
  assert.equal(first.listenerCount(DomEvent.CLICK), 0);
  library.show(many);
  assert.equal(byAction(library.element, BuilderAction.ADD).length, LIBRARY_PAGE_SIZE);
});

// %% instances

test('the instance list marks the selection and selects the clicked instance', () => {
  const selected = [];
  const list = new InstanceList(new Elements(new FakeDocument()), (identifier) => selected.push(identifier));
  const withMissing = structuredClone(draft);
  withMissing[DraftKey.INSTANCES][0][InstanceKey.ASSET] = 'library/missing.urdf';
  list.show(withMissing, 'scan', resourceOf);
  const rows = byAction(list.element, BuilderAction.SELECT);
  assert.deepEqual(rows.map((row) => row.getAttribute('aria-selected')), ['false', 'true']);
  assert.equal(rows[0].children[0].textContent, MISSING_RESOURCE);
  rows[0].dispatch(DomEvent.CLICK);
  assert.deepEqual(selected, [withMissing[DraftKey.INSTANCES][0][InstanceKey.IDENTIFIER]]);
});

// %% inspector

function inspector() {
  const { calls, callbacks } = recorder(INSPECTOR_ACTIONS);
  callbacks.noticeUrl = (asset) => `assets/${asset}`;
  const view = new InspectorView(new Elements(new FakeDocument()), new InspectorActions(callbacks));
  return { view, calls };
}

test('the inspector is empty without a selection', () => {
  const { view } = inspector();
  view.show(null, undefined, { links: [], joints: [] }, null);
  assert.equal(view.element.findAll((element) => element.className === 'inspector-editor')[0].hidden, true);
});

test('the inspector shows the placement in degrees and reports changes in radians', () => {
  const { view, calls } = inspector();
  const cabinet = draft[DraftKey.INSTANCES][0];
  view.show(cabinet, resourceOf(cabinet[InstanceKey.ASSET]), { links: ['body', 'drawer'], joints: [] }, null);
  const rotation = byAction(view.element, BuilderAction.ROTATION);
  assert.equal(Number(rotation[2].value), Number((cabinet[InstanceKey.ROTATION][2] * DEGREES_PER_RADIAN).toFixed(6)));
  rotation[2].value = '180';
  rotation[2].dispatch(DomEvent.CHANGE);
  const [name, position, turned] = calls.at(-1);
  assert.equal(name, 'place');
  assert.deepEqual(position, cabinet[InstanceKey.POSITION]);
  assert.equal(turned[2], Math.PI);
});

test('an empty placement field is refused', () => {
  const { view } = inspector();
  const cabinet = draft[DraftKey.INSTANCES][0];
  view.show(cabinet, resourceOf(cabinet[InstanceKey.ASSET]), { links: [], joints: [] }, null);
  const [x] = byAction(view.element, BuilderAction.POSITION);
  x.value = ' ';
  assert.throws(() => x.dispatch(DomEvent.CHANGE), MissingNumber);
});

test('scaling one axis scales all three while proportions are kept', () => {
  const { view, calls } = inspector();
  const cabinet = draft[DraftKey.INSTANCES][0];
  view.show(cabinet, resourceOf(cabinet[InstanceKey.ASSET]), { links: [], joints: [] }, null);
  const scale = byAction(view.element, BuilderAction.SCALE).filter((element) => element.tagName === 'INPUT');
  scale[1].value = '2';
  scale[1].dispatch(DomEvent.CHANGE);
  assert.deepEqual(calls.at(-1), ['scale', [2, 2, 2]]);
  const [proportional] = byAction(view.element, BuilderAction.PROPORTIONAL);
  proportional.checked = false;
  proportional.dispatch(DomEvent.CHANGE);
  scale[1].dispatch(DomEvent.CHANGE);
  assert.deepEqual(calls.at(-1), ['scale', [1, 2, 1]]);
  assert.deepEqual(calls.find((call) => call[0] === 'setProportional'), ['setProportional', false]);
});

test('a selected link hides the scale and offers restoring it', () => {
  const { view, calls } = inspector();
  const cabinet = draft[DraftKey.INSTANCES][0];
  view.show(cabinet, resourceOf(cabinet[InstanceKey.ASSET]), { links: ['body', 'drawer'], joints: [] }, 'drawer');
  const [restore] = byAction(view.element, BuilderAction.RESET_LINK);
  const [link] = byAction(view.element, BuilderAction.CHOOSE_LINK);
  assert.equal(restore.hidden, false);
  assert.equal(link.value, 'drawer');
  restore.dispatch(DomEvent.CLICK);
  link.value = '';
  link.dispatch(DomEvent.CHANGE);
  assert.deepEqual(calls, [['resetLink'], ['chooseLink', null]]);
});

test('joint fields show degrees for turning joints and metres for sliding ones', () => {
  const { view, calls } = inspector();
  const cabinet = draft[DraftKey.INSTANCES][0];
  const joints = [
    { name: 'slide', type: JointType.PRISMATIC, lower: 0, upper: 0.4 },
    { name: 'hinge', type: JointType.REVOLUTE, lower: -1, upper: 1 },
  ];
  view.show(cabinet, resourceOf(cabinet[InstanceKey.ASSET]), { links: [], joints }, null);
  const [slide, hinge] = byAction(view.element, BuilderAction.JOINT);
  assert.equal(Number(slide.value), cabinet[InstanceKey.JOINT_POSITIONS].slide);
  assert.equal(Number(hinge.max), DEGREES_PER_RADIAN);
  hinge.value = '90';
  hinge.dispatch(DomEvent.CHANGE);
  assert.deepEqual(calls.at(-1), ['setJoint', 'hinge', Math.PI / 2]);
});

test('a reference shows its appearance and reports point sizes in metres', () => {
  const { view, calls } = inspector();
  const scan = draft[DraftKey.INSTANCES][1];
  view.show(scan, resourceOf(scan[InstanceKey.ASSET]), { links: [], joints: [] }, null);
  const [size] = byAction(view.element, BuilderAction.POINT_SIZE);
  const [locked] = byAction(view.element, BuilderAction.LOCKED);
  assert.equal(Number(size.value), scan[InstanceKey.POINT_CLOUD][AppearanceKey.POINT_SIZE] * MILLIMETRES_PER_METRE);
  size.value = '4';
  size.dispatch(DomEvent.CHANGE);
  locked.checked = true;
  locked.dispatch(DomEvent.CHANGE);
  assert.deepEqual(calls, [
    ['setAppearance', { [AppearanceKey.POINT_SIZE]: 4 / MILLIMETRES_PER_METRE }],
    ['setAppearance', { [AppearanceKey.LOCKED]: true }],
  ]);
});

test('the fields of a locked reference cannot be changed', () => {
  const { view } = inspector();
  const scan = structuredClone(draft[DraftKey.INSTANCES][1]);
  scan[InstanceKey.POINT_CLOUD][AppearanceKey.LOCKED] = true;
  view.show(scan, resourceOf(scan[InstanceKey.ASSET]), { links: [], joints: [] }, null);
  assert.ok(byAction(view.element, BuilderAction.POSITION).every((input) => input.disabled));
});

test('notices link to their files and are named as text', () => {
  const { view } = inspector();
  const cabinet = draft[DraftKey.INSTANCES][0];
  const resource = resourceOf(cabinet[InstanceKey.ASSET]);
  view.show(cabinet, resource, { links: [], joints: [] }, null);
  const links = view.element.findAll((element) => element.tagName === 'A');
  assert.deepEqual(links.map((link) => link.textContent), resource[ResourceKey.NOTICES].map((notice) => notice[NoticeKey.NAME]));
  assert.deepEqual(links.map((link) => link.href), resource[ResourceKey.NOTICES].map((notice) => `assets/${notice[NoticeKey.ASSET]}`));
});

test('renaming, duplicating and removing are reported', () => {
  const { view, calls } = inspector();
  const cabinet = draft[DraftKey.INSTANCES][0];
  view.show(cabinet, resourceOf(cabinet[InstanceKey.ASSET]), { links: [], joints: [] }, null);
  const [name] = byAction(view.element, BuilderAction.RENAME);
  name.value = '  tall cabinet ';
  name.dispatch(DomEvent.CHANGE);
  byAction(view.element, BuilderAction.DUPLICATE)[0].dispatch(DomEvent.CLICK);
  byAction(view.element, BuilderAction.REMOVE)[0].dispatch(DomEvent.CLICK);
  assert.deepEqual(calls, [['rename', 'tall cabinet'], ['duplicate'], ['remove']]);
});

// %% menus

test('the header shows the name, history and whether the draft is saved', () => {
  const { calls, callbacks } = recorder(MENU_ACTIONS);
  const header = new BuilderHeader(new Elements(new FakeDocument()), new MenuActions(callbacks), '../../');
  header.show('Kitchen', true, false, false);
  const [undo] = byAction(header.element, BuilderAction.UNDO);
  const [redo] = byAction(header.element, BuilderAction.REDO);
  assert.equal(undo.disabled, false);
  assert.equal(redo.disabled, true);
  byAction(header.element, BuilderAction.SAVE)[0].dispatch(DomEvent.CLICK);
  byAction(header.element, BuilderAction.SAVE_COPY)[0].dispatch(DomEvent.CLICK);
  assert.deepEqual(calls, [['save', false], ['save', true]]);
});

test('the drafts menu opens scenes and drafts by their names', () => {
  const { calls, callbacks } = recorder(MENU_ACTIONS);
  const menu = new DraftMenu(new Elements(new FakeDocument()), new MenuActions(callbacks));
  menu.show(catalog[CatalogKey.SCENES], catalog[CatalogKey.DRAFTS]);
  const [scenes] = byAction(menu.element, BuilderAction.OPEN_SCENE);
  const [drafts] = byAction(menu.element, BuilderAction.LOAD_DRAFT);
  scenes.dispatch(DomEvent.CHANGE);
  scenes.value = catalog[CatalogKey.SCENES][0][IndexEntryKey.NAME];
  scenes.dispatch(DomEvent.CHANGE);
  drafts.value = catalog[CatalogKey.DRAFTS][0][DraftSummaryKey.IDENTIFIER];
  drafts.dispatch(DomEvent.CHANGE);
  assert.deepEqual(calls, [
    ['openScene', catalog[CatalogKey.SCENES][0][IndexEntryKey.NAME]],
    ['loadDraft', catalog[CatalogKey.DRAFTS][0][DraftSummaryKey.IDENTIFIER]],
  ]);
});

test('a chosen point cloud file is uploaded in the chosen unit', () => {
  const { calls, callbacks } = recorder(MENU_ACTIONS);
  const menu = new DraftMenu(new Elements(new FakeDocument()), new MenuActions(callbacks));
  const [units, chooser, file] = byAction(menu.element, BuilderAction.UPLOAD);
  const room = { name: 'room.ply' };
  units.value = String(SourceUnit.CENTIMETRES);
  chooser.dispatch(DomEvent.CLICK);
  assert.equal(file.clicks, 1);
  file.files = [room];
  file.dispatch(DomEvent.CHANGE);
  assert.deepEqual(calls, [['upload', room, SourceUnit.CENTIMETRES]]);
});

test('the toolbar marks the current mode and reports a chosen one', () => {
  const { calls, callbacks } = recorder(MENU_ACTIONS);
  const toolbar = new ViewToolbar(new Elements(new FakeDocument()), new MenuActions(callbacks));
  toolbar.show(TransformMode.ROTATE, true);
  const modes = byAction(toolbar.element, BuilderAction.MODE);
  assert.deepEqual(modes.map((button) => button.getAttribute('aria-pressed')), Object.values(TransformMode).map((mode) => String(mode === TransformMode.ROTATE)));
  modes[2].dispatch(DomEvent.CLICK);
  assert.deepEqual(calls, [['setMode', modes[2].dataset.mode]]);
});
