import { test } from 'node:test';
import assert from 'node:assert/strict';

import { StatusPage } from '../../src/cramera/web/app/status.js';
import { BuildKey, IndexEntryKey, IndexKey, PageReportKey, PluginKey, ViewerInfoKey } from '../../src/cramera/web/protocol.js';
import { FakeDocument } from './support/fake-document.mjs';

/**
 * @returns {FakeDocument} A document with the status page's elements.
 */
function statusDocument() {
  const document = new FakeDocument();
  const elements = {};
  for (const id of ['build-facts', 'scene-list', 'shot-caption', 'shot']) {
    elements[id] = document.createElement('div');
    document.body.append(elements[id]);
  }
  document.getElementById = (id) => elements[id];
  document.createTextNode = (text) => Object.assign(document.createElement('text'), { textContent: text });
  return document;
}

const INFO = {
  [ViewerInfoKey.VERSION]: '1.0.0',
  [ViewerInfoKey.PROTOCOL_VERSION]: '1.0',
  [ViewerInfoKey.PLUGINS]: [{ [PluginKey.NAME]: 'questions', [PluginKey.VERSION]: '1.0.0' }],
  [ViewerInfoKey.BUILD]: { [BuildKey.COMMIT]: 'abcdef0123456789', [BuildKey.BUILT_AT]: '2026-10-22T13:00:00Z', [BuildKey.SOURCE]: 'https://github.com/sunava/cramera' },
};

const INDEX = { [IndexKey.SCENES]: [{ [IndexEntryKey.NAME]: 'pr2 warehouse', [IndexEntryKey.ROBOT]: 'PR2', [IndexEntryKey.TASK]: 'transport' }] };

test('the status page names the build, links its commit and lists the scenes', async () => {
  const document = statusDocument();
  const api = { info: async () => INFO, scenes: async () => INDEX };
  await new StatusPage(document, api).show(async () => ({ [PageReportKey.STATUS]: 'Showing pr2', [PageReportKey.BROWSER]: 'chrome' }));
  const facts = document.getElementById('build-facts');
  const link = facts.findAll((element) => element.tagName === 'A')[0];
  assert.equal(link.href, 'https://github.com/sunava/cramera/commit/abcdef0123456789');
  assert.match(facts.innerText, /questions 1\.0\.0/);
  const scene = document.getElementById('scene-list').children[0].children[0];
  assert.equal(scene.href, './?scene=pr2%20warehouse');
  assert.match(document.getElementById('shot-caption').textContent, /headless chrome\. The page reported: Showing pr2/);
});

test('without a build stamp or a screenshot the page says so', async () => {
  const document = statusDocument();
  const api = { info: async () => ({ [ViewerInfoKey.VERSION]: '1.0.0' }), scenes: async () => ({}) };
  await new StatusPage(document, api).show(async () => null);
  assert.match(document.getElementById('build-facts').innerText, /not a published build/);
  assert.equal(document.getElementById('shot').hidden, true);
});

test('a build without a repository shows its commit as text', async () => {
  const document = statusDocument();
  const build = { [BuildKey.COMMIT]: 'abc', [BuildKey.BUILT_AT]: '2026-10-22T13:00:00Z' };
  const api = { info: async () => ({ ...INFO, [ViewerInfoKey.BUILD]: build }), scenes: async () => INDEX };
  await new StatusPage(document, api).show(async () => null);
  assert.match(document.getElementById('build-facts').innerText, /abc/);
});
