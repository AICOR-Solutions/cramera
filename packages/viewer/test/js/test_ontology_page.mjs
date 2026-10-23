import { test } from 'node:test';
import assert from 'node:assert/strict';

import { ONTOLOGY_BROWSER_URL, OntologyPage } from '../../src/cramera/web/app/ontology-page.js';
import { FakeDocument } from './support/fake-document.mjs';

/**
 * @returns {Object} A page element holding the ontology page.
 */
const shownPage = () => {
  const root = new FakeDocument().createElement('main');
  new OntologyPage(root);
  return root;
};

// %% ontology page

test('the page embeds the CRAM ontology browser without telling it where it is embedded', () => {
  const [frame] = shownPage().findAll((element) => element.tagName === 'IFRAME');
  assert.equal(frame.src, ONTOLOGY_BROWSER_URL);
  assert.equal(frame.referrerPolicy, 'no-referrer');
});

test('the page opens the ontology browser in a tab of its own', () => {
  const [link] = shownPage().findAll((element) => element.tagName === 'A');
  assert.equal(link.href, ONTOLOGY_BROWSER_URL);
  assert.equal(link.target, '_blank');
  assert.equal(link.rel, 'noopener noreferrer');
});
