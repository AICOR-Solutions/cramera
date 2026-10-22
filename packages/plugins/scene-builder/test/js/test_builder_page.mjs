import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  AppearanceKey,
  BuilderPageParameter,
  CatalogKey,
  DraftKey,
  DraftListKey,
  DraftRecordKey,
  DraftSummaryKey,
  InstanceKey,
  PageState,
  PageStateAttribute,
  ResourceKey,
  ResourceKind,
  ViewerEvent,
} from 'cramera-viewer/protocol.js';
import { EventBus } from 'cramera-viewer/core/event-bus.js';
import { PanelHost } from 'cramera-viewer/panels/panel-host.js';
import { BuilderEnvironment, BuilderPage } from '../../src/cramera_scene_builder/web/builder/builder-page.js';
import { SourceUnit } from '../../src/cramera_scene_builder/web/builder/draft-menu.js';
import { RECOVERY_KEY } from '../../src/cramera_scene_builder/web/builder/draft-recovery.js';
import { Selection, TransformMode } from '../../src/cramera_scene_builder/web/builder/draft-view.js';
import { BuilderAction, DomEvent } from '../../src/cramera_scene_builder/web/builder/elements.js';
import { PANEL_TITLE, register } from '../../src/cramera_scene_builder/web/index.js';
import { FakeDocument, FakeStorage } from 'cramera-testing/fake-document.mjs';

const read = (name) => JSON.parse(readFileSync(new URL(`dataset/${name}`, import.meta.url), 'utf8'));
const byAction = (root, action) => root.findAll((element) => element.dataset.action === action);
const settled = () => new Promise((resolve) => setImmediate(resolve));

/**
 * Answers the builder's requests from the test catalog and records what was asked.
 */
class FakeApi {
  constructor() {
    this.catalogAnswer = read('catalog.json');
    this.saved = [];
    this.uploads = [];
    this.templates = [];
  }

  async catalog() {
    return structuredClone(this.catalogAnswer);
  }

  async template(scene) {
    this.templates.push(scene);
    return { ...read('draft.json'), [DraftKey.SOURCE_SCENE]: scene };
  }

  async drafts() {
    return { [DraftListKey.DRAFTS]: this.saved.map((record) => ({ [DraftSummaryKey.IDENTIFIER]: record[DraftRecordKey.IDENTIFIER], [DraftSummaryKey.NAME]: record[DraftRecordKey.DOCUMENT][DraftKey.NAME] })) };
  }

  async draft(identifier) {
    return structuredClone(this.saved.find((record) => record[DraftRecordKey.IDENTIFIER] === identifier));
  }

  async save(draft, identifier) {
    const record = { [DraftRecordKey.IDENTIFIER]: identifier ?? `draft-${this.saved.length + 1}`, [DraftRecordKey.DOCUMENT]: draft };
    this.saved.push(record);
    return structuredClone(record);
  }

  async upload(file, format) {
    this.uploads.push([file.name, format]);
    return this.catalogAnswer[CatalogKey.RESOURCES].find((resource) => resource[ResourceKey.KIND] === ResourceKind.POINT_CLOUD);
  }

  assetUrl(identifier) {
    return `assets/${identifier}`;
  }
}

/**
 * A 3D view that records what the page shows and selects.
 */
class RecordingView {
  constructor(listeners) {
    this.listeners = listeners;
    this.shown = [];
    this.selections = [];
    this.modes = [];
    this.disposed = false;
  }

  show(draft) {
    this.shown.push(draft);
  }

  select(selection) {
    this.selections.push(selection);
  }

  setMode(mode) {
    this.modes.push(mode);
  }

  setProportional() {}

  structure() {
    return { links: ['body', 'drawer'], joints: [] };
  }

  frameAll() {}

  isLoading() {
    return this.loading ?? false;
  }

  frameSelection() {}

  dispose() {
    this.disposed = true;
  }
}

async function started({ query = '', storage = new FakeStorage(), withView = true } = {}) {
  const document = new FakeDocument();
  const root = document.createElement('div');
  const api = new FakeApi();
  const downloads = [];
  let view = null;
  const page = new BuilderPage(
    root,
    new BuilderEnvironment({
      document,
      api,
      storage,
      query: new URLSearchParams(query),
      viewerUrl: '../../',
      createView: withView ? (container, listeners) => (view = new RecordingView(listeners)) : null,
      download: (blob, name) => downloads.push([blob, name]),
    }),
  );
  await page.start();
  await settled();
  return { page, root, api, document, storage, downloads, view: () => view };
}

const status = (root) => root.findAll((element) => element.className === 'status-line')[0];

// %% starting

test('the page lists the catalog and shows an empty draft', async () => {
  const { page, root, view } = await started();
  assert.equal(byAction(root, BuilderAction.ADD).length, read('catalog.json')[CatalogKey.RESOURCES].length);
  assert.deepEqual(page.state.draft[DraftKey.INSTANCES], []);
  assert.equal(view().shown.length > 0, true);
});

test('a page naming a scene starts a draft from it', async () => {
  const { page, api, document } = await started({ query: `${BuilderPageParameter.SCENE}=cell` });
  assert.deepEqual(api.templates, ['cell']);
  assert.equal(page.state.draft[DraftKey.SOURCE_SCENE], 'cell');
  assert.equal(document.documentElement.dataset[PageStateAttribute.STATE], PageState.READY);
});

test('the page is ready once the view has shown every model', async () => {
  const { root, view, document } = await started();
  view().loading = true;
  byAction(root, BuilderAction.ADD)[0].dispatch(DomEvent.CLICK);
  await settled();
  assert.equal(document.documentElement.dataset[PageStateAttribute.STATE], PageState.LOADING);
  view().loading = false;
  view().listeners.onLoaded('instance-1');
  assert.equal(document.documentElement.dataset[PageStateAttribute.STATE], PageState.READY);
});

test('without WebGL the page says so and keeps the fields', async () => {
  const { root, page } = await started({ withView: false });
  assert.ok(root.findAll((element) => element.className === 'stage-message').length === 1);
  byAction(root, BuilderAction.ADD)[0].dispatch(DomEvent.CLICK);
  await settled();
  assert.equal(page.state.draft[DraftKey.INSTANCES].length, 1);
});

// %% editing

test('clicking a resource places and selects it', async () => {
  const { root, page, view } = await started();
  byAction(root, BuilderAction.ADD)[0].dispatch(DomEvent.CLICK);
  await settled();
  const [instance] = page.state.draft[DraftKey.INSTANCES];
  assert.deepEqual(page.selection, new Selection(instance[InstanceKey.IDENTIFIER]));
  assert.deepEqual(view().selections.at(-1), page.selection);
});

test('a handle drag places the selection as one step', async () => {
  const { root, page, view } = await started();
  byAction(root, BuilderAction.ADD)[0].dispatch(DomEvent.CLICK);
  await settled();
  const selection = page.selection;
  view().listeners.onPlace(selection, { position: [1, 2, 0], rotation: [0, 0, 0.5], scale: [1, 1, 1] });
  await settled();
  assert.deepEqual(page.state.instance(selection.instance)[InstanceKey.POSITION], [1, 2, 0]);
  page.state.undo();
  assert.deepEqual(page.state.instance(selection.instance)[InstanceKey.POSITION], [0, 0, 0]);
});

test('a scale drag sets the scale', async () => {
  const { root, page, view } = await started();
  byAction(root, BuilderAction.ADD)[0].dispatch(DomEvent.CLICK);
  await settled();
  byAction(root, BuilderAction.MODE).find((button) => button.dataset.mode === TransformMode.SCALE).dispatch(DomEvent.CLICK);
  view().listeners.onPlace(page.selection, { position: [0, 0, 0], rotation: [0, 0, 0], scale: [2, 2, 2] });
  await settled();
  assert.deepEqual(page.state.instance(page.selection.instance)[InstanceKey.SCALE], [2, 2, 2]);
});

test('selecting a link leaves the scale mode', async () => {
  const { root, page, view } = await started();
  byAction(root, BuilderAction.ADD)[0].dispatch(DomEvent.CLICK);
  await settled();
  byAction(root, BuilderAction.MODE).find((button) => button.dataset.mode === TransformMode.SCALE).dispatch(DomEvent.CLICK);
  view().listeners.onPick(new Selection(page.selection.instance, 'drawer'));
  assert.equal(view().modes.at(-1), TransformMode.MOVE);
});

test('a refused edit is reported and changes nothing', async () => {
  const { root, page } = await started();
  byAction(root, BuilderAction.ADD)[0].dispatch(DomEvent.CLICK);
  await settled();
  const before = page.state.draft;
  const [name] = byAction(root, BuilderAction.RENAME);
  name.value = '';
  name.dispatch(DomEvent.CHANGE);
  await settled();
  assert.deepEqual(page.state.draft, before);
  assert.equal(status(root).dataset.state, PageState.FAILED);
});

test('Ctrl+Z undoes and Ctrl+Shift+Z redoes outside form fields', async () => {
  const { root, page, document } = await started();
  byAction(root, BuilderAction.ADD)[0].dispatch(DomEvent.CLICK);
  await settled();
  document.dispatch(DomEvent.KEY_DOWN, { key: 'z', ctrlKey: true, target: { tagName: 'INPUT' } });
  assert.equal(page.state.draft[DraftKey.INSTANCES].length, 1);
  document.dispatch(DomEvent.KEY_DOWN, { key: 'z', ctrlKey: true, target: { tagName: 'CANVAS' } });
  assert.equal(page.state.draft[DraftKey.INSTANCES].length, 0);
  document.dispatch(DomEvent.KEY_DOWN, { key: 'Z', ctrlKey: true, shiftKey: true, target: { tagName: 'CANVAS' } });
  assert.equal(page.state.draft[DraftKey.INSTANCES].length, 1);
});

// %% saving

test('saving keeps the identity, so saving again replaces the same draft', async () => {
  const { root, page, api } = await started();
  byAction(root, BuilderAction.ADD)[0].dispatch(DomEvent.CLICK);
  await settled();
  byAction(root, BuilderAction.SAVE)[0].dispatch(DomEvent.CLICK);
  await settled();
  const identifier = page.draftIdentifier;
  byAction(root, BuilderAction.SAVE)[0].dispatch(DomEvent.CLICK);
  await settled();
  byAction(root, BuilderAction.SAVE_COPY)[0].dispatch(DomEvent.CLICK);
  await settled();
  assert.deepEqual(api.saved.map((record) => record[DraftRecordKey.IDENTIFIER]), [identifier, identifier, 'draft-3']);
  assert.equal(root.findAll((element) => element.className === 'muted save-state')[0].textContent, 'Saved');
});

test('a saved draft opens with its identity', async () => {
  const { root, page, api } = await started();
  await api.save(read('draft.json'), 'kitchen');
  const [drafts] = byAction(root, BuilderAction.LOAD_DRAFT);
  drafts.value = 'kitchen';
  drafts.dispatch(DomEvent.CHANGE);
  await settled();
  assert.equal(page.draftIdentifier, 'kitchen');
  assert.equal(page.state.draft[DraftKey.NAME], read('draft.json')[DraftKey.NAME]);
});

test('a new scene forgets the saved draft', async () => {
  const { root, page } = await started();
  byAction(root, BuilderAction.ADD)[0].dispatch(DomEvent.CLICK);
  byAction(root, BuilderAction.SAVE)[0].dispatch(DomEvent.CLICK);
  await settled();
  byAction(root, BuilderAction.NEW)[0].dispatch(DomEvent.CLICK);
  await settled();
  assert.equal(page.draftIdentifier, null);
  assert.deepEqual(page.state.draft[DraftKey.INSTANCES], []);
});

// %% files

test('an export offers the draft as a file named after it', async () => {
  const { root, page, downloads } = await started();
  byAction(root, BuilderAction.EXPORT)[0].dispatch(DomEvent.CLICK);
  await settled();
  const [[blob, name]] = downloads;
  assert.deepEqual(JSON.parse(await blob.text()), page.state.draft);
  assert.ok(name.startsWith(page.state.draft[DraftKey.NAME].replaceAll(' ', '_')));
});

test('an imported file becomes the draft', async () => {
  const { root, page } = await started();
  const file = { name: 'kitchen.scene.json', text: async () => JSON.stringify(read('draft.json')) };
  const imports = byAction(root, BuilderAction.IMPORT).find((element) => element.tagName === 'INPUT');
  imports.files = [file];
  imports.dispatch(DomEvent.CHANGE);
  await settled();
  assert.equal(page.state.draft[DraftKey.NAME], read('draft.json')[DraftKey.NAME]);
});

test('an imported file that is no draft is refused', async () => {
  const { root, page } = await started();
  const file = { name: 'next.scene.json', text: async () => JSON.stringify(read('invalid/next_major_version.json')) };
  const imports = byAction(root, BuilderAction.IMPORT).find((element) => element.tagName === 'INPUT');
  imports.files = [file];
  imports.dispatch(DomEvent.CHANGE);
  await settled();
  assert.deepEqual(page.state.draft[DraftKey.INSTANCES], []);
  assert.equal(status(root).dataset.state, PageState.FAILED);
});

test('an uploaded scan is placed as a locked reference in its unit', async () => {
  const { root, page, api } = await started();
  const [units, , file] = byAction(root, BuilderAction.UPLOAD);
  units.value = String(SourceUnit.MILLIMETRES);
  file.files = [{ name: 'room.PLY' }];
  file.dispatch(DomEvent.CHANGE);
  await settled();
  const [reference] = page.state.draft[DraftKey.INSTANCES];
  assert.deepEqual(api.uploads, [['room.PLY', 'ply']]);
  assert.equal(reference[InstanceKey.NAME], 'room');
  assert.deepEqual(reference[InstanceKey.SCALE], [SourceUnit.MILLIMETRES, SourceUnit.MILLIMETRES, SourceUnit.MILLIMETRES]);
  assert.equal(reference[InstanceKey.POINT_CLOUD][AppearanceKey.LOCKED], true);
});

test('a file of another format is not uploaded', async () => {
  const { root, api } = await started();
  const [, , file] = byAction(root, BuilderAction.UPLOAD);
  file.files = [{ name: 'room.obj' }];
  file.dispatch(DomEvent.CHANGE);
  await settled();
  assert.deepEqual(api.uploads, []);
  assert.equal(status(root).dataset.state, PageState.FAILED);
});

// %% recovery

test('the draft of the last visit is restored', async () => {
  const storage = new FakeStorage();
  const first = await started({ storage });
  byAction(first.root, BuilderAction.ADD)[0].dispatch(DomEvent.CLICK);
  await settled();
  const second = await started({ storage });
  assert.deepEqual(second.page.state.draft, first.page.state.draft);
});

test('an unreadable kept draft is forgotten and reported', async () => {
  const storage = new FakeStorage();
  storage.setItem(RECOVERY_KEY, '{');
  const { root, page } = await started({ storage });
  assert.deepEqual(page.state.draft[DraftKey.INSTANCES], []);
  assert.notEqual(storage.getItem(RECOVERY_KEY), '{');
  assert.equal(status(root).dataset.state, PageState.FAILED);
});

test('disposing the page removes its listeners and frees the view', async () => {
  const { page, document, view } = await started();
  page.dispose();
  assert.equal(document.listenerCount(DomEvent.KEY_DOWN), 0);
  assert.equal(view().disposed, true);
});

// %% viewer panel

test('the panel links to the builder page and follows the shown scene', () => {
  const document = new FakeDocument();
  const bus = new EventBus();
  const panels = new PanelHost(document.createElement('aside'));
  const panel = register({ bus, panels }, document, 'http://localhost/plugins/scene-builder/builder.html');
  assert.equal(panels.identifiers().length, 1);
  assert.ok(panel.element.innerText.includes(PANEL_TITLE));
  bus.publish(ViewerEvent.SCENE_LOADING, 'cell & bench');
  const links = panel.element.findAll((element) => element.tagName === 'A');
  assert.equal(new URL(links[1].href).searchParams.get(BuilderPageParameter.SCENE), 'cell & bench');
  assert.equal(links[1].textContent, 'Start a draft from cell & bench');
  panel.dispose();
  assert.equal(bus.listenerCount(ViewerEvent.SCENE_LOADING), 0);
});
