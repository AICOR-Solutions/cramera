import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { EventBus } from 'cramera-viewer/core/event-bus.js';
import { PanelHost, SidePanel } from 'cramera-viewer/panels/panel-host.js';
import { ChapterKey, StoryboardKey, ViewerEvent } from 'cramera-viewer/protocol.js';
import { Tour } from '../../src/cramera_offline/web/tour.js';
import { ManualTimer } from './fakes.mjs';
import { FakeDocument } from 'cramera-testing/fake-document.mjs';

/**
 * The storyboard of the tests: two bundles, a played chapter, an unknown panel.
 */
const STORYBOARD = JSON.parse(readFileSync(new URL('./storyboard.json', import.meta.url), 'utf-8'));

/**
 * How many milliseconds make one second.
 */
const MILLISECONDS_PER_SECOND = 1000;

// %% fixtures

/**
 * A tour over the storyboard with a bus that records what the tour asks for.
 */
class TourSetup {
  constructor() {
    this.bus = new EventBus();
    this.requests = [];
    for (const event of [ViewerEvent.SCENE_REQUESTED, ViewerEvent.FRAME_REQUESTED, ViewerEvent.PLAYBACK_REQUESTED]) {
      this.bus.subscribe(event, (payload) => this.requests.push([event, payload]));
    }
    const document = new FakeDocument();
    this.panels = new PanelHost(document.createElement('aside'));
    for (const identifier of ['steps', 'details']) this.panels.add(new SidePanel(identifier, identifier, document.createElement('section')));
    this.timer = new ManualTimer();
    this.changes = 0;
    this.tour = new Tour(STORYBOARD, this.bus, this.panels, this.timer, () => (this.changes += 1));
  }

  /**
   * Let the application report a loaded bundle.
   * @param {string} name The bundle.
   * @param {number} frameCount Its recording's frames.
   */
  loaded(name, frameCount) {
    this.bus.publish(ViewerEvent.SCENE_LOADED, { name, frames: { frameCount } });
  }

  /**
   * @param {string} event A `ViewerEvent` value.
   * @returns {Array<*>} The payloads of the recorded requests of that event.
   */
  payloads(event) {
    return this.requests.filter(([name]) => name === event).map(([, payload]) => payload);
  }
}

/**
 * @param {number} position A chapter's position.
 * @returns {Object} The chapter.
 */
function chapter(position) {
  return STORYBOARD[StoryboardKey.CHAPTERS][position];
}

// %% chapters

test('showing a chapter of another bundle asks for the bundle and opens its panel', () => {
  const setup = new TourSetup();
  setup.tour.show(0);
  assert.deepEqual(setup.payloads(ViewerEvent.SCENE_REQUESTED), [chapter(0)[ChapterKey.SCENE]]);
  assert.equal(setup.panels.shown, chapter(0)[ChapterKey.PANEL]);
  assert.equal(setup.changes, 1);
});

test('a chapter starts at its frame once its bundle is loaded, and plays when asked', () => {
  const setup = new TourSetup();
  setup.tour.show(1);
  assert.deepEqual(setup.payloads(ViewerEvent.FRAME_REQUESTED), []);
  setup.loaded(chapter(1)[ChapterKey.SCENE], 10);
  assert.deepEqual(setup.payloads(ViewerEvent.FRAME_REQUESTED), [chapter(1)[ChapterKey.FRAME]]);
  assert.deepEqual(setup.payloads(ViewerEvent.PLAYBACK_REQUESTED), [false, true]);
});

test('a chapter of the shown bundle starts without loading it again', () => {
  const setup = new TourSetup();
  setup.loaded(chapter(2)[ChapterKey.SCENE], 5);
  setup.tour.show(2);
  assert.deepEqual(setup.payloads(ViewerEvent.SCENE_REQUESTED), []);
  assert.deepEqual(setup.payloads(ViewerEvent.FRAME_REQUESTED), [chapter(2)[ChapterKey.FRAME]]);
});

test('a chapter naming a panel the viewer does not have keeps the shown panel', () => {
  const setup = new TourSetup();
  setup.panels.show('steps');
  setup.tour.show(2);
  assert.equal(setup.panels.shown, 'steps');
});

test('a bundle loaded for another chapter does not start the waiting one', () => {
  const setup = new TourSetup();
  setup.tour.show(1);
  setup.loaded(chapter(0)[ChapterKey.SCENE], 5);
  assert.deepEqual(setup.payloads(ViewerEvent.FRAME_REQUESTED), []);
});

test('previous stops at the first chapter and next past the last pauses', () => {
  const setup = new TourSetup();
  setup.tour.previous();
  assert.equal(setup.tour.position, 0);
  setup.tour.show(2);
  setup.tour.start();
  setup.tour.next();
  assert.equal(setup.tour.position, 2);
  assert.equal(setup.tour.running, false);
});

// %% running

test('a running tour moves on once the chapter time is over', () => {
  const setup = new TourSetup();
  setup.loaded(chapter(0)[ChapterKey.SCENE], 5);
  setup.tour.start();
  assert.deepEqual([...setup.timer.pending.values()].map(({ milliseconds }) => milliseconds), [chapter(0)[ChapterKey.DURATION] * MILLISECONDS_PER_SECOND]);
  setup.timer.runAll();
  assert.equal(setup.tour.position, 1);
});

test('a played chapter waits for its recording to end before moving on', () => {
  const setup = new TourSetup();
  setup.tour.show(1);
  setup.tour.start();
  setup.loaded(chapter(1)[ChapterKey.SCENE], 10);
  setup.timer.runAll();
  assert.equal(setup.tour.position, 1);
  setup.bus.publish(ViewerEvent.FRAME_CHANGED, 5);
  assert.equal(setup.tour.position, 1);
  setup.bus.publish(ViewerEvent.FRAME_CHANGED, 9);
  assert.equal(setup.tour.position, 2);
});

test('pausing cancels the chapter time and the playback', () => {
  const setup = new TourSetup();
  setup.loaded(chapter(0)[ChapterKey.SCENE], 5);
  setup.tour.start();
  setup.tour.pause();
  assert.equal(setup.timer.pending.size, 0);
  assert.equal(setup.payloads(ViewerEvent.PLAYBACK_REQUESTED).at(-1), false);
  assert.equal(setup.tour.running, false);
});

test('a bundle that fails to load stops the tour', () => {
  const setup = new TourSetup();
  setup.tour.start();
  setup.bus.publish(ViewerEvent.SCENE_FAILED, 'missing');
  assert.equal(setup.tour.running, false);
});
