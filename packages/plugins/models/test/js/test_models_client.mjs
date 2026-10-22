import { test } from 'node:test';
import assert from 'node:assert/strict';

import { RequestFailed } from 'cramera-viewer/core/viewer-api.js';
import { ErrorKey, ModelRequestKey, ModelsRoute, ModelUploadKey, PluginName, ViewerRoute } from 'cramera-viewer/protocol.js';
import { ModelsClient } from '../../src/cramera_models/web/models-client.js';
import { FakeAnswer, FakeApi } from './fakes.mjs';

/**
 * A fetch answering every request with one answer and recording the requests.
 */
class RecordingFetch {
  /**
   * @param {FakeAnswer} answer The answer.
   */
  constructor(answer) {
    this.answer = answer;
    this.requests = [];
  }

  /**
   * @returns {function(string, Object=): Promise<FakeAnswer>} The fetch.
   */
  fetch() {
    return async (url, init) => {
      this.requests.push({ url, init });
      return this.answer;
    };
  }
}

/**
 * @param {string} route A `ModelsRoute` value.
 * @returns {string} The route's URL below the fake API's base.
 */
function urlOf(route) {
  return new FakeApi().url(`${ViewerRoute.PLUGIN_API}${PluginName.MODELS}/${route}`);
}

// %% routes

test('the state is read from the plugin route below the page base', async () => {
  const state = { loaded: false };
  const recording = new RecordingFetch(new FakeAnswer(200, state));
  assert.deepEqual(await new ModelsClient(recording.fetch(), new FakeApi()).state(), state);
  assert.equal(recording.requests[0].url, urlOf(ModelsRoute.STATE));
});

test('a model file is posted as its name and its text', async () => {
  const recording = new RecordingFetch(new FakeAnswer(200, {}));
  await new ModelsClient(recording.fetch(), new FakeApi()).load('a.json', '{"x": Infinity}');
  const { url, init } = recording.requests[0];
  assert.equal(url, urlOf(ModelsRoute.LOAD));
  assert.deepEqual(JSON.parse(init.body), { [ModelUploadKey.NAME]: 'a.json', [ModelUploadKey.TEXT]: '{"x": Infinity}' });
});

test('each question is posted to its route with its documents', async () => {
  const recording = new RecordingFetch(new FakeAnswer(200, {}));
  const client = new ModelsClient(recording.fetch(), new FakeApi());
  const query = [{ variable: 'x' }];
  const evidence = [{ variable: 'color' }];
  await client.probability(query, evidence);
  await client.posterior(['x'], evidence);
  await client.mode(evidence);
  assert.deepEqual(recording.requests.map(({ url }) => url), [ModelsRoute.PROBABILITY, ModelsRoute.POSTERIOR, ModelsRoute.MODE].map(urlOf));
  assert.deepEqual(recording.requests.map(({ init }) => JSON.parse(init.body)), [
    { [ModelRequestKey.QUERY]: query, [ModelRequestKey.EVIDENCE]: evidence },
    { [ModelRequestKey.VARIABLES]: ['x'], [ModelRequestKey.EVIDENCE]: evidence },
    { [ModelRequestKey.EVIDENCE]: evidence },
  ]);
});

test('a refused request carries the reason the viewer gave', async () => {
  const reason = 'The models workbench needs plotly.';
  const recording = new RecordingFetch(new FakeAnswer(503, { [ErrorKey.ERROR]: reason }));
  await assert.rejects(new ModelsClient(recording.fetch(), new FakeApi()).state(), (error) => error instanceof RequestFailed && error.reason === reason && error.status === 503);
});

test('a refusal without a JSON body carries the status text', async () => {
  const answer = new FakeAnswer(502, null, 'text/html');
  await assert.rejects(new ModelsClient(new RecordingFetch(answer).fetch(), new FakeApi()).state(), (error) => error.reason === answer.statusText);
});
