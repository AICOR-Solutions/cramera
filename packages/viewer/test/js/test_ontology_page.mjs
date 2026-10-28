import { test } from 'node:test';
import assert from 'node:assert/strict';

import { ONTOLOGY_BROWSER_URL, OntologyPage, ontologyAddress, ontologyEntityOf } from '../../src/cramera/web/app/ontology-page.js';
import { FakeDocument } from './support/fake-document.mjs';

/**
 * A page window at a fragment, whose fragment can change.
 */
class FakeWindow {
  /**
   * @param {string} hash The page's fragment, with its `#`, or ''.
   */
  constructor(hash) {
    this.location = { hash };
    this.listeners = new Map();
  }

  addEventListener(type, listener) {
    this.listeners.set(type, listener);
  }

  /**
   * @param {string} hash The new fragment.
   */
  navigate(hash) {
    this.location.hash = hash;
    this.listeners.get('hashchange')?.();
  }
}

/**
 * @param {FakeWindow=} window The page's window.
 * @returns {Object} A page element holding the ontology page.
 */
const shownPage = (window = new FakeWindow('')) => {
  const root = new FakeDocument().createElement('main');
  new OntologyPage(root, window);
  return root;
};

const frameOf = (root) => root.findAll((element) => element.tagName === 'IFRAME')[0];
const linkOf = (root) => root.findAll((element) => element.tagName === 'A')[0];

// %% ontology page

test('the page embeds the CRAM ontology browser without telling it where it is embedded', () => {
  const frame = frameOf(shownPage());
  assert.equal(frame.src, ONTOLOGY_BROWSER_URL);
  assert.equal(frame.referrerPolicy, 'no-referrer');
});

test('the page opens the ontology browser in a tab of its own', () => {
  const link = linkOf(shownPage());
  assert.equal(link.href, ONTOLOGY_BROWSER_URL);
  assert.equal(link.target, '_blank');
  assert.equal(link.rel, 'noopener noreferrer');
});

test('the page shows the entity its fragment names, and the one a new fragment names', () => {
  const window = new FakeWindow('#semantic_digital_twin:Body');
  const root = shownPage(window);
  assert.equal(frameOf(root).src, `${ONTOLOGY_BROWSER_URL}#semantic_digital_twin:Body`);
  assert.equal(linkOf(root).href, `${ONTOLOGY_BROWSER_URL}#semantic_digital_twin:Body`);
  window.navigate('#semantic_digital_twin:PR2LeftArm');
  assert.equal(frameOf(root).src, `${ONTOLOGY_BROWSER_URL}#semantic_digital_twin:PR2LeftArm`);
  assert.equal(linkOf(root).href, `${ONTOLOGY_BROWSER_URL}#semantic_digital_twin:PR2LeftArm`);
});

// %% classes

test('a class is the entity named by its top-level package and its own name', () => {
  assert.equal(ontologyEntityOf('semantic_digital_twin.robots.pr2.PR2LeftArm'), 'semantic_digital_twin:PR2LeftArm');
  assert.equal(ontologyEntityOf('semantic_digital_twin.world.World'), 'semantic_digital_twin:World');
});

test('a class is shown on the ontology page at its entity', () => {
  assert.equal(
    ontologyAddress('http://127.0.0.1:8765/ontology.html', 'semantic_digital_twin.world_description.world_entity.Body'),
    'http://127.0.0.1:8765/ontology.html#semantic_digital_twin:Body',
  );
});
