import assert from 'node:assert/strict';
import { test } from 'node:test';

import { RequestFailed } from 'cramera-viewer/core/viewer-api.js';
import { LaboratoryName, LaboratoryRoute, ViewerRoute } from 'cramera-viewer/protocol.js';

import { LaboratoryClient } from '../../src/cramera_laboratory/web/laboratory-client.js';
import { FakeApi, FakeFetch } from './fakes.mjs';

const routeUrl = (route) => `http://viewer${ViewerRoute.PLUGIN_API}${LaboratoryName.PLUGIN}/${route}`;

test('the routes lie below the plugin prefix', () => {
  const client = new LaboratoryClient(() => null, new FakeApi());
  assert.equal(client.url(LaboratoryRoute.STATE), routeUrl(LaboratoryRoute.STATE));
  assert.equal(
    client.deviceFileUrl('tube rack', 'model.urdf'),
    routeUrl(`${LaboratoryRoute.DEVICE_FILES}tube%20rack/model.urdf`),
  );
});

test('reading the catalog asks the viewer api', async () => {
  const api = new FakeApi();
  api.answers.set(routeUrl(LaboratoryRoute.LABORATORIES), { laboratories: [] });
  const client = new LaboratoryClient(() => null, api);
  assert.deepEqual(await client.laboratories(), { laboratories: [] });
});

test('a command posts its document as JSON', async () => {
  const network = new FakeFetch();
  const client = new LaboratoryClient((url, options) => network.fetch(url, options), new FakeApi());
  network.answer(routeUrl(LaboratoryRoute.RESET), 200, { state: 'running' });
  const answer = await client.send(LaboratoryRoute.RESET);
  assert.deepEqual(answer, { state: 'running' });
  assert.equal(network.requests[0].options.method, 'POST');
  assert.deepEqual(network.requests[0].body, {});
});

test('a refused command throws the laboratory’s reason', async () => {
  const network = new FakeFetch();
  const client = new LaboratoryClient((url, options) => network.fetch(url, options), new FakeApi());
  network.answer(routeUrl(LaboratoryRoute.TARE), 409, { error: 'Wait for the scale’s reading to settle.' });
  await assert.rejects(client.send(LaboratoryRoute.TARE), (error) => error instanceof RequestFailed && error.status === 409 && error.reason.startsWith('Wait'));
});
