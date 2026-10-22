import { test } from 'node:test';
import assert from 'node:assert/strict';

import { EventBus } from '../../src/cramera/web/core/event-bus.js';
import { PageStatus } from '../../src/cramera/web/core/page-status.js';
import { RequestFailed, ViewerApi } from '../../src/cramera/web/core/viewer-api.js';
import { ErrorKey, PageState, PageStateAttribute, ViewerEvent, ViewerRoute } from '../../src/cramera/web/protocol.js';
import { FakeDocument } from './support/fake-document.mjs';

// %% event bus

test('listeners receive the payloads of their event in subscription order', () => {
  const bus = new EventBus();
  const received = [];
  bus.subscribe(ViewerEvent.FRAME_CHANGED, (frame) => received.push(['first', frame]));
  bus.subscribe(ViewerEvent.FRAME_CHANGED, (frame) => received.push(['second', frame]));
  bus.subscribe(ViewerEvent.SCENE_LOADED, () => received.push(['other']));
  bus.publish(ViewerEvent.FRAME_CHANGED, 7);
  assert.deepEqual(received, [['first', 7], ['second', 7]]);
});

test('an unsubscribed listener is no longer called', () => {
  const bus = new EventBus();
  let calls = 0;
  const unsubscribe = bus.subscribe(ViewerEvent.FRAME_CHANGED, () => calls++);
  unsubscribe();
  bus.publish(ViewerEvent.FRAME_CHANGED, 1);
  assert.equal(calls, 0);
  assert.equal(bus.listenerCount(ViewerEvent.FRAME_CHANGED), 0);
});

test('a listener that unsubscribes while being called does not disturb the others', () => {
  const bus = new EventBus();
  const received = [];
  const unsubscribe = bus.subscribe(ViewerEvent.FRAME_CHANGED, () => { received.push('once'); unsubscribe(); });
  bus.subscribe(ViewerEvent.FRAME_CHANGED, () => received.push('always'));
  bus.publish(ViewerEvent.FRAME_CHANGED, 1);
  bus.publish(ViewerEvent.FRAME_CHANGED, 2);
  assert.deepEqual(received, ['once', 'always', 'always']);
});

// %% page status

test('the page status writes the state for tools and the line for people', () => {
  const document = new FakeDocument();
  const line = document.createElement('p');
  const status = new PageStatus(document.documentElement, line);
  status.loading('Loading cell');
  assert.equal(status.state, PageState.LOADING);
  status.ready('Showing cell');
  assert.equal(document.documentElement.dataset[PageStateAttribute.STATE], PageState.READY);
  assert.equal(document.documentElement.dataset[PageStateAttribute.STATUS], 'Showing cell');
  assert.equal(line.textContent, 'Showing cell');
  status.failed('Scene missing');
  assert.equal(line.dataset.state, PageState.FAILED);
});

// %% API

/**
 * @param {Object<string, {status: number, body: *, type?: string}>} answers Answers by URL.
 * @returns {{fetch: Function, requested: Array<string>}} A fetch function and the URLs it was asked for.
 */
function fakeFetch(answers) {
  const requested = [];
  const fetch = async (url) => {
    requested.push(url);
    const answer = answers[url];
    return {
      ok: answer.status < 400,
      status: answer.status,
      statusText: 'Status text',
      headers: new Map([['Content-Type', answer.type ?? 'application/json']]),
      json: async () => answer.body,
    };
  };
  return { fetch, requested };
}

test('routes resolve against the base, so the viewer works below a path', async () => {
  const base = 'https://sunava.github.io/cramera/';
  const { fetch, requested } = fakeFetch({ [`${base}api/info`]: { status: 200, body: { version: '1.0.0' } } });
  const api = new ViewerApi(fetch, base);
  assert.deepEqual(await api.info(), { version: '1.0.0' });
  assert.equal(requested[0], base + ViewerRoute.INFO.slice(1));
  assert.equal(api.sceneFileUrl('cell one', 'scene.json'), `${base}scenes/cell%20one/scene.json`);
});

test('an error answer names the reason the viewer gave', async () => {
  const base = 'http://localhost:8711/';
  const url = `${base}api/scenes`;
  const { fetch } = fakeFetch({ [url]: { status: 404, body: { [ErrorKey.ERROR]: 'No such scene.' } } });
  await assert.rejects(new ViewerApi(fetch, base).scenes(), (error) => error instanceof RequestFailed && error.status === 404 && error.reason === 'No such scene.');
});

test('an error answer that is not JSON falls back to the status text', async () => {
  const base = 'http://localhost:8711/';
  const url = `${base}scenes/cell/scene.json`;
  const { fetch } = fakeFetch({ [url]: { status: 502, body: null, type: 'text/html' } });
  await assert.rejects(new ViewerApi(fetch, base).sceneJson('cell', 'scene.json'), (error) => error.reason === 'Status text');
});

// %% scene addresses

import { SCENE_PARAMETER, sceneOf, withScene } from '../../src/cramera/web/core/scene-address.js';

test('a page address names the bundle to show', () => {
  assert.equal(sceneOf(`https://sunava.github.io/cramera/?${SCENE_PARAMETER}=cell&x=1`), 'cell');
  assert.equal(sceneOf('https://sunava.github.io/cramera/'), null);
  assert.equal(withScene('https://sunava.github.io/cramera/?x=1', 'a b').href, 'https://sunava.github.io/cramera/?x=1&scene=a+b');
});
