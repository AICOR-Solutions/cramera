import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  DraftRecordKey,
  ErrorKey,
  PointCloudFormat,
  SceneBuilderName,
  SceneBuilderRoute,
  TemplateParameter,
  ViewerRoute,
} from 'cramera-viewer/protocol.js';
import { RequestFailed } from 'cramera-viewer/core/viewer-api.js';
import { BuilderApi } from '../../src/cramera_scene_builder/web/builder/builder-api.js';

const BASE = 'http://localhost:8080/viewer/';
const PREFIX = `${BASE}${ViewerRoute.PLUGIN_API.replace(/^\//, '')}${SceneBuilderName.PLUGIN}/`;

/**
 * Records every request and answers each with the next prepared answer.
 */
class RecordingFetch {
  constructor(...answers) {
    this.requests = [];
    this.answers = answers;
  }

  fetch = async (url, options = {}) => {
    this.requests.push({ url, options });
    return this.answers.shift();
  };
}

function answer(body, status = 200) {
  return {
    ok: status < 400,
    status,
    statusText: 'Status',
    headers: new Map([['Content-Type', 'application/json']]),
    json: async () => body,
    arrayBuffer: async () => body,
  };
}

// %% reading

test('routes lie below the plugin prefix of the viewer base', async () => {
  const recording = new RecordingFetch(answer({}), answer({}), answer({}));
  const api = new BuilderApi(recording.fetch, BASE);
  await api.catalog();
  await api.drafts();
  await api.draft('4f 2a');
  assert.deepEqual(
    recording.requests.map((request) => request.url),
    [`${PREFIX}${SceneBuilderRoute.CATALOG}`, `${PREFIX}${SceneBuilderRoute.DRAFTS}`, `${PREFIX}${SceneBuilderRoute.DRAFT}4f%202a`],
  );
});

test('a template names its scene by the template parameter', async () => {
  const recording = new RecordingFetch(answer({}));
  await new BuilderApi(recording.fetch, BASE).template('cell & bench');
  const url = new URL(recording.requests[0].url);
  assert.equal(url.searchParams.get(TemplateParameter.SCENE), 'cell & bench');
});

test('asset addresses escape every segment of the identifier', () => {
  const api = new BuilderApi(new RecordingFetch().fetch, BASE);
  assert.equal(api.assetUrl('library/props/cup glaze.png'), `${PREFIX}${SceneBuilderRoute.ASSETS}library/props/cup%20glaze.png`);
});

test('a sample is read as bytes from the sample route', async () => {
  const bytes = new ArrayBuffer(8);
  const recording = new RecordingFetch(answer(bytes));
  assert.equal(await new BuilderApi(recording.fetch, BASE).sample('point-clouds/4f2a.ply'), bytes);
  assert.equal(recording.requests[0].url, `${PREFIX}${SceneBuilderRoute.POINT_CLOUD_SAMPLES}point-clouds/4f2a.ply`);
});

test('a refused request reports the reason the server gave', async () => {
  const recording = new RecordingFetch(answer({ [ErrorKey.ERROR]: 'No such sample.' }, 404));
  await assert.rejects(new BuilderApi(recording.fetch, BASE).sample('point-clouds/x.ply'), (error) => error instanceof RequestFailed && error.reason === 'No such sample.' && error.status === 404);
});

// %% writing

test('saving posts the draft with the identity it replaces', async () => {
  const recording = new RecordingFetch(answer({}), answer({}));
  const api = new BuilderApi(recording.fetch, BASE);
  const draft = { name: 'Kitchen' };
  await api.save(draft, '4f2a');
  await api.save(draft, null);
  const [replacing, creating] = recording.requests.map((request) => JSON.parse(request.options.body));
  assert.deepEqual(replacing, { [DraftRecordKey.DOCUMENT]: draft, [DraftRecordKey.IDENTIFIER]: '4f2a' });
  assert.deepEqual(creating, { [DraftRecordKey.DOCUMENT]: draft });
  assert.equal(recording.requests[0].url, `${PREFIX}${SceneBuilderRoute.DRAFTS}`);
});

test('an upload posts the file to its format', async () => {
  const recording = new RecordingFetch(answer({}));
  const file = { name: 'room.pcd' };
  await new BuilderApi(recording.fetch, BASE).upload(file, PointCloudFormat.PCD);
  assert.equal(recording.requests[0].url, `${PREFIX}${SceneBuilderRoute.POINT_CLOUDS}${PointCloudFormat.PCD}`);
  assert.equal(recording.requests[0].options.body, file);
});

test('a refused save reports the reason the server gave', async () => {
  const recording = new RecordingFetch(answer({ [ErrorKey.ERROR]: 'Too large.' }, 413));
  await assert.rejects(new BuilderApi(recording.fetch, BASE).save({}, null), (error) => error instanceof RequestFailed && error.reason === 'Too large.');
});
