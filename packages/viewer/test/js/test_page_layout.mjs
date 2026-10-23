import { test } from 'node:test';
import assert from 'node:assert/strict';

import { ONTOLOGY_PAGE, ONTOLOGY_ROUTE, ONTOLOGY_TITLE, SCENE_PAGE, SiteHeader, ThemeSetting, localStorageOf, pageLinksOf, versionOf } from '../../src/cramera/web/app/site-header.js';
import { layoutOf, panelOf, sceneAlone, withPanel } from '../../src/cramera/web/core/scene-address.js';
import { QuerySlot, SlotPanel, SlotTaken } from '../../src/cramera/web/panels/query-slot.js';
import {
  BuildKey,
  NavigationGroup,
  NavigationKey,
  PageLayout,
  PageParameter,
  PageStorageKey,
  PluginKey,
  Theme,
  ViewerInfoKey,
} from '../../src/cramera/web/protocol.js';
import { FakeDocument, FakeStorage } from './support/fake-document.mjs';

const BASE = 'https://sunava.github.io/cramera/';

const url = (route) => new URL(route.replace(/^\//, ''), BASE).href;

/**
 * The viewer's information with plugins declaring pages and panels in mixed order.
 */
const INFO = {
  [ViewerInfoKey.VERSION]: '1.0.0',
  [ViewerInfoKey.BUILD]: { [BuildKey.COMMIT]: 'abcdef0123456789', [BuildKey.BUILT_AT]: '2026-10-23T10:00:00Z' },
  [ViewerInfoKey.PLUGINS]: [
    { [PluginKey.NAME]: 'cable-lab', [PluginKey.NAVIGATION]: { [NavigationKey.TITLE]: 'Cable Lab', [NavigationKey.GROUP]: NavigationGroup.LABORATORY, [NavigationKey.PAGE]: '/plugins/cable-lab/cable-lab.html' } },
    { [PluginKey.NAME]: 'questions' },
    { [PluginKey.NAME]: 'scene-builder', [PluginKey.NAVIGATION]: { [NavigationKey.TITLE]: 'Scene Builder', [NavigationKey.GROUP]: NavigationGroup.BUILDER, [NavigationKey.PAGE]: '/plugins/scene-builder/builder.html' } },
    { [PluginKey.NAME]: 'models', [PluginKey.NAVIGATION]: { [NavigationKey.TITLE]: 'Models', [NavigationKey.GROUP]: NavigationGroup.ANALYSIS } },
    { [PluginKey.NAME]: 'plan-builder', [PluginKey.NAVIGATION]: { [NavigationKey.TITLE]: 'Plan Builder', [NavigationKey.GROUP]: NavigationGroup.BUILDER, [NavigationKey.PAGE]: '/plugins/plan-builder/builder.html' } },
  ],
};

// %% navigation

test('the pages are the scene page, then the plugins\' entries by group and title, then the ontology', () => {
  const links = pageLinksOf(INFO, url);
  assert.deepEqual(links.map((link) => link.title), ['Scene', 'Models', 'Plan Builder', 'Scene Builder', 'Cable Lab', ONTOLOGY_TITLE]);
  assert.equal(links[0].href, BASE);
  assert.equal(links[2].href, `${BASE}plugins/plan-builder/builder.html`);
  assert.equal(links[1].panel, 'models');
  assert.equal(links[1].href, `${BASE}?${PageParameter.PANEL}=models`);
  assert.equal(links[2].panel, null);
});

test('without plugin entries only the viewer\'s own pages are offered', () => {
  assert.deepEqual(pageLinksOf({ [ViewerInfoKey.PLUGINS]: [{ [PluginKey.NAME]: 'questions' }] }, url).map((link) => link.identity), [SCENE_PAGE, ONTOLOGY_PAGE]);
});

test('the ontology is a page of the viewer\'s own', () => {
  const ontology = pageLinksOf(INFO, url).at(-1);
  assert.equal(ontology.identity, ONTOLOGY_PAGE);
  assert.equal(ontology.href, url(ONTOLOGY_ROUTE));
  assert.equal(ontology.panel, null);
});

test('the header marks its own page and shows panels on the scene page', () => {
  const document = new FakeDocument();
  const root = document.createElement('header');
  const shown = [];
  const header = new SiteHeader(root, url, new ThemeSetting(document.documentElement, null), SCENE_PAGE, (panel) => shown.push(panel));
  header.show(INFO);
  const [brand, navigation, actions] = root.children;
  assert.equal(brand.children[0].src, `${BASE}images/aicor-logo.png`);
  const anchors = navigation.children;
  assert.equal(anchors[0].getAttribute('aria-current'), 'page');
  assert.equal(anchors[1].getAttribute('aria-current'), null);
  let prevented = false;
  anchors[1].dispatch('click', { preventDefault: () => { prevented = true; } });
  assert.deepEqual(shown, ['models']);
  assert.equal(prevented, true);
  assert.equal(anchors[2].listeners.has('click'), false);
  assert.equal(actions.children[0].textContent, versionOf(INFO));
  assert.equal(actions.children[0].href, `${BASE}status.html`);
});

test('a plugin panel shown on the scene page is marked as the current page', () => {
  const document = new FakeDocument();
  const root = document.createElement('header');
  const header = new SiteHeader(root, url, new ThemeSetting(document.documentElement, null), SCENE_PAGE, () => {});
  header.show(INFO);
  header.markCurrent('models');
  const current = root.children[1].children.filter((anchor) => anchor.getAttribute('aria-current') === 'page');
  assert.deepEqual(current.map((anchor) => anchor.dataset.page), ['models']);
  header.markCurrent(SCENE_PAGE);
  assert.equal(root.children[1].children[0].getAttribute('aria-current'), 'page');
  assert.equal(root.children[1].children[1].getAttribute('aria-current'), 'false');
});

test('on a plugin page the header follows the panel links instead', () => {
  const document = new FakeDocument();
  const root = document.createElement('header');
  new SiteHeader(root, url, new ThemeSetting(document.documentElement, null), 'plan-builder').show(INFO);
  const anchors = root.children[1].children;
  assert.equal(anchors[1].listeners.has('click'), false);
  assert.equal(anchors[2].getAttribute('aria-current'), 'page');
});

test('the build stamp names the version, the short commit and the build time', () => {
  assert.equal(versionOf(INFO), 'v1.0.0 · abcdef0 · 2026-10-23T10:00:00Z');
  assert.equal(versionOf({ [ViewerInfoKey.VERSION]: '1.0.0' }), 'v1.0.0');
});

// %% theme

test('the theme is dark unless light was chosen, and the choice is kept', () => {
  const document = new FakeDocument();
  const storage = new FakeStorage();
  const theme = new ThemeSetting(document.documentElement, storage);
  theme.apply();
  assert.equal(document.documentElement.dataset.theme, Theme.DARK);
  theme.choose(Theme.LIGHT);
  assert.equal(document.documentElement.dataset.theme, Theme.LIGHT);
  assert.equal(storage.getItem(PageStorageKey.THEME), Theme.LIGHT);
  assert.equal(new ThemeSetting(document.documentElement, storage).theme, Theme.LIGHT);
  storage.setItem(PageStorageKey.THEME, 'sepia');
  assert.equal(new ThemeSetting(document.documentElement, storage).theme, Theme.DARK);
});

test('a page whose storage is refused still shows and changes its theme', () => {
  const document = new FakeDocument();
  const refusing = { getItem: () => { throw new Error('denied'); }, setItem: () => { throw new Error('denied'); } };
  const theme = new ThemeSetting(document.documentElement, refusing);
  assert.equal(theme.theme, Theme.DARK);
  theme.choose(Theme.LIGHT);
  assert.equal(document.documentElement.dataset.theme, Theme.LIGHT);
  const window = { get localStorage() { throw new Error('denied'); } };
  assert.equal(localStorageOf(window), null);
});

test('the View menu opens and changes the theme', () => {
  const document = new FakeDocument();
  const root = document.createElement('header');
  new SiteHeader(root, url, new ThemeSetting(document.documentElement, new FakeStorage()), SCENE_PAGE);
  const menu = root.children[2].children[1];
  const [toggle, list] = menu.children;
  assert.equal(list.hidden, true);
  toggle.dispatch('click');
  assert.equal(list.hidden, false);
  const choice = list.children[0].children[1];
  choice.value = Theme.LIGHT;
  choice.dispatch('change');
  assert.equal(document.documentElement.dataset.theme, Theme.LIGHT);
});

// %% addresses

test('the scene alone is the same address with the scene layout and no panel', () => {
  const shown = `${BASE}?scene=cell&${PageParameter.PANEL}=models`;
  const alone = sceneAlone(shown);
  assert.equal(layoutOf(alone.href), PageLayout.SCENE);
  assert.equal(panelOf(alone.href), null);
  assert.equal(alone.searchParams.get(PageParameter.SCENE), 'cell');
  assert.equal(layoutOf(BASE), null);
  assert.equal(panelOf(withPanel(BASE, 'workshop').href), 'workshop');
});

// %% query slot

test('one plugin fills the query slot, which is hidden until then', () => {
  const document = new FakeDocument();
  const root = document.createElement('section');
  const slot = new QuerySlot(root);
  assert.equal(root.hidden, true);
  assert.equal(slot.occupant, null);
  const aside = document.createElement('span');
  const content = document.createElement('div');
  slot.fill(new SlotPanel('questions', 'EQL', content, aside));
  assert.equal(root.hidden, false);
  assert.equal(slot.occupant, 'questions');
  const [head, body] = root.children;
  assert.deepEqual(head.children.map((child) => child.textContent || child), ['EQL', aside]);
  assert.equal(body, content);
  assert.equal(content.classList.contains('slot-body'), true);
  assert.throws(() => slot.fill(new SlotPanel('other', 'Other', document.createElement('div'))), SlotTaken);
});
