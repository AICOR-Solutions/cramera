import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { EventBus } from '../../../core/event-bus.js';
import { PanelHost } from '../../../panels/panel-host.js';
import {
  AssetProblemKey,
  AssetProblemKind,
  BundleCheckKey,
  ChapterKey,
  ErrorKey,
  OfflineRoute,
  PluginName,
  StoryboardKey,
  ViewerEvent,
  ViewerRoute,
} from '../../../protocol.js';
import { register } from '../index.js';
import { OfflineClient } from '../offline-client.js';
import { Tour } from '../tour.js';
import { TourPanel } from '../tour-panel.js';
import { FakeAnswer, FakeApi, FakeNetwork, ManualTimer } from './fakes.mjs';
import { FakeDocument } from './support/fake-document.mjs';

/**
 * The storyboard of the tests.
 */
const STORYBOARD = JSON.parse(readFileSync(new URL('./storyboard.json', import.meta.url), 'utf-8'));

/**
 * @param {string} route An `OfflineRoute` value.
 * @returns {string} The route's URL path below the fake API's base.
 */
function pathOf(route) {
  return new URL(new FakeApi().url(`${ViewerRoute.PLUGIN_API}${PluginName.OFFLINE}/${route}`)).pathname;
}

/**
 * A page with a head and the plugin context over a network.
 */
class PageSetup {
  /**
   * @param {Object<string, FakeAnswer>} answers The network's answers by path.
   */
  constructor(answers) {
    this.document = new FakeDocument();
    this.document.head = this.document.createElement('head');
    this.bus = new EventBus();
    this.panels = new PanelHost(this.document.createElement('aside'));
    this.network = new FakeNetwork(answers);
    globalThis.fetch = this.network.fetch();
    this.context = { bus: this.bus, panels: this.panels, api: new FakeApi(), view: null };
  }

  /**
   * @returns {TourPanel} A panel over the page's network.
   */
  panel() {
    return new TourPanel(this.document, new OfflineClient(this.network.fetch(), this.context.api), this.bus);
  }
}

// %% tour controls

test('the storyboard is shown with its chapters and the shown chapter is marked', () => {
  const setup = new PageSetup({});
  const panel = setup.panel();
  const tour = new Tour(STORYBOARD, setup.bus, setup.panels, new ManualTimer(), () => panel.update());
  panel.showTour(tour);
  assert.deepEqual(panel.chapterButtons.map((button) => button.textContent), STORYBOARD[StoryboardKey.CHAPTERS].map((chapter) => chapter[ChapterKey.TITLE]));
  assert.equal(panel.chapterButtons[0].getAttribute('aria-current'), 'true');
  assert.equal(panel.narration.textContent, STORYBOARD[StoryboardKey.CHAPTERS][0][ChapterKey.NARRATION]);
  panel.chapterButtons[2].dispatch('click');
  assert.equal(tour.position, 2);
  assert.equal(panel.chapterButtons[2].getAttribute('aria-current'), 'true');
  assert.equal(panel.narration.textContent, '');
});

test('the run button starts and pauses the tour', () => {
  const setup = new PageSetup({});
  const panel = setup.panel();
  const tour = new Tour(STORYBOARD, setup.bus, setup.panels, new ManualTimer(), () => panel.update());
  panel.showTour(tour);
  const label = panel.runButton.textContent;
  panel.runButton.dispatch('click');
  assert.equal(tour.running, true);
  assert.notEqual(panel.runButton.textContent, label);
  panel.runButton.dispatch('click');
  assert.equal(tour.running, false);
  assert.equal(panel.runButton.textContent, label);
});

// %% bundle check

test('a complete bundle is reported with its file count', async () => {
  const report = { [BundleCheckKey.BUNDLE]: 'cell', [BundleCheckKey.CHECKED_FILES]: ['scene.json', 'arm.urdf'], [BundleCheckKey.PROBLEMS]: [] };
  const setup = new PageSetup({ [pathOf(OfflineRoute.BUNDLE_CHECK)]: new FakeAnswer(200, report) });
  const panel = setup.panel();
  await panel.checkBundle('cell');
  assert.match(panel.bundleCheck.innerText, new RegExp(`${report[BundleCheckKey.CHECKED_FILES].length} files`));
});

test('every reference that cannot be followed is listed', async () => {
  const problem = { [AssetProblemKey.KIND]: AssetProblemKind.MISSING, [AssetProblemKey.SOURCE]: 'arm.urdf', [AssetProblemKey.REFERENCE]: 'meshes/base.stl' };
  const report = { [BundleCheckKey.BUNDLE]: 'cell', [BundleCheckKey.CHECKED_FILES]: [], [BundleCheckKey.PROBLEMS]: [problem, problem] };
  const setup = new PageSetup({ [pathOf(OfflineRoute.BUNDLE_CHECK)]: new FakeAnswer(200, report) });
  const panel = setup.panel();
  await panel.checkBundle('cell');
  const items = panel.bundleCheck.findAll((element) => element.tagName === 'LI');
  assert.equal(items.length, report[BundleCheckKey.PROBLEMS].length);
  assert.match(items[0].textContent, new RegExp(problem[AssetProblemKey.REFERENCE]));
});

test('a check answered after another bundle was shown is dropped', async () => {
  const setup = new PageSetup({});
  const panel = setup.panel();
  const first = panel.checkBundle('cell');
  const second = panel.checkBundle('transport');
  await Promise.all([first, second]);
  assert.equal(panel.bundleCheck.findAll(() => true).length, 1);
});

test('a loaded scene is checked', async () => {
  const setup = new PageSetup({});
  const panel = setup.panel();
  setup.bus.publish(ViewerEvent.SCENE_LOADED, { name: 'cell', frames: { frameCount: 1 } });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(setup.network.requested.length, 1);
  assert.notEqual(panel.bundleCheck.innerText, '');
});

// %% registration

test('registration adds the panel and shows the storyboard tour', async () => {
  const setup = new PageSetup({ [pathOf(OfflineRoute.STORYBOARD)]: new FakeAnswer(200, STORYBOARD) });
  const panel = await register(setup.context, setup.document, new ManualTimer());
  assert.deepEqual(setup.panels.identifiers(), [PluginName.OFFLINE]);
  assert.equal(setup.panels.shown, PluginName.OFFLINE);
  assert.equal(panel.chapterButtons.length, STORYBOARD[StoryboardKey.CHAPTERS].length);
  assert.equal(setup.document.head.children.length, 1);
});

test('registration without a storyboard says so and still checks bundles', async () => {
  const setup = new PageSetup({});
  const panel = await register(setup.context, setup.document, new ManualTimer());
  assert.equal(panel.chapterButtons.length, 0);
  assert.notEqual(panel.storyboard.innerText, '');
});

test('registration with a damaged storyboard shows the reason', async () => {
  const setup = new PageSetup({ [pathOf(OfflineRoute.STORYBOARD)]: new FakeAnswer(400, { [ErrorKey.ERROR]: 'broken' }) });
  const panel = await register(setup.context, setup.document, new ManualTimer());
  assert.match(panel.storyboard.innerText, /broken/);
});
