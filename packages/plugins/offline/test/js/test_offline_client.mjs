import { test } from 'node:test';
import assert from 'node:assert/strict';

import { BundleCheckKey, ErrorKey, OfflineParameter, OfflineRoute, PluginName, ViewerRoute } from 'cramera-viewer/protocol.js';
import { OfflineClient } from '../../src/cramera_offline/web/offline-client.js';
import { FakeAnswer, FakeApi, FakeNetwork } from './fakes.mjs';

/**
 * A route of the offline plugin as the fake API addresses it.
 * @param {string} route An `OfflineRoute` value.
 * @returns {string} The route's URL path.
 */
function pathOf(route) {
  return new URL(new FakeApi().url(`${ViewerRoute.PLUGIN_API}${PluginName.OFFLINE}/${route}`)).pathname;
}

// %% storyboard

test('a storyboard is read from the plugin route below the page base', async () => {
  const storyboard = { title: 'A tour' };
  const network = new FakeNetwork({ [pathOf(OfflineRoute.STORYBOARD)]: new FakeAnswer(200, storyboard) });
  const answer = await new OfflineClient(network.fetch(), new FakeApi()).storyboard();
  assert.deepEqual(answer.storyboard, storyboard);
  assert.equal(answer.problem, null);
});

test('without a storyboard there is neither a storyboard nor a problem', async () => {
  const answer = await new OfflineClient(new FakeNetwork({}).fetch(), new FakeApi()).storyboard();
  assert.equal(answer.storyboard, null);
  assert.equal(answer.problem, null);
});

test('a damaged storyboard is reported with the reason', async () => {
  const reason = 'not JSON';
  const network = new FakeNetwork({ [pathOf(OfflineRoute.STORYBOARD)]: new FakeAnswer(400, { [ErrorKey.ERROR]: reason }) });
  const answer = await new OfflineClient(network.fetch(), new FakeApi()).storyboard();
  assert.equal(answer.problem, reason);
});

// %% bundle check

test('the bundle check names the scene in its query', async () => {
  const report = { [BundleCheckKey.BUNDLE]: 'cell', [BundleCheckKey.PROBLEMS]: [] };
  const network = new FakeNetwork({ [pathOf(OfflineRoute.BUNDLE_CHECK)]: new FakeAnswer(200, report) });
  const answer = await new OfflineClient(network.fetch(), new FakeApi()).bundleCheck('cell');
  assert.deepEqual(answer, report);
  assert.equal(new URL(network.requested[0]).searchParams.get(OfflineParameter.SCENE), 'cell');
});

test('a server without the bundle check answers none', async () => {
  const answer = await new OfflineClient(new FakeNetwork({}).fetch(), new FakeApi()).bundleCheck('cell');
  assert.equal(answer, null);
});
