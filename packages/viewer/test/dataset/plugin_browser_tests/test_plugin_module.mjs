import { test } from 'node:test';
import assert from 'node:assert/strict';

import { ViewerEvent } from 'cramera-viewer/protocol.js';
import { FakeDocument } from 'cramera-testing/fake-document.mjs';

import { register } from '../plugin_web/index.js';

test('a plugin module and the viewer modules it reaches resolve as the viewer serves them', () => {
  const context = { document: new FakeDocument() };
  assert.equal(register(context), context);
  assert.equal(ViewerEvent.SCENE_LOADED, 'scene:loaded');
});
