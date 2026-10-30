import { test } from 'node:test';
import assert from 'node:assert/strict';

import { EventBus } from '../../src/cramera/web/core/event-bus.js';
import {
  clockTime,
  eventLabel,
  EventMoment,
  eventMoments,
  FOLLOW_TEXT,
  NO_EVENTS,
  SegmindPanel,
  segmindEvents,
  shortName,
} from '../../src/cramera/web/panels/segmind-panel.js';
import { DetectedEventKey, DetectedEventKind, DetectedEventsKey, SceneKey, ViewerEvent } from '../../src/cramera/web/protocol.js';
import { FakeDocument } from './support/fake-document.mjs';

/**
 * A recording's events: the milk is picked up at frame 10, moves, and is put on the table
 * at frame 30, where it comes to rest.
 */
const EVENTS = Object.freeze([
  {
    [DetectedEventKey.NAME]: 'kitchen/milk PickUpEvent',
    [DetectedEventKey.EVENT_TYPE]: 'PickUpEvent',
    [DetectedEventKey.TIMESTAMP]: '2026-10-28T14:02:31.250000',
    [DetectedEventKey.TRACKED_OBJECT]: 'kitchen/milk',
    [DetectedEventKey.WITH_OBJECT]: 'pr2/r_gripper_tool_frame',
    [DetectedEventKey.KIND]: DetectedEventKind.PICK_AND_PLACE,
    [DetectedEventKey.FRAME]: 10,
    [DetectedEventKey.KEYS]: ['k-milk', 'r_gripper_tool_frame'],
  },
  {
    [DetectedEventKey.NAME]: 'kitchen/milk TranslationEvent',
    [DetectedEventKey.EVENT_TYPE]: 'TranslationEvent',
    [DetectedEventKey.TIMESTAMP]: '2026-10-28T14:02:32.000000',
    [DetectedEventKey.TRACKED_OBJECT]: 'kitchen/milk',
    [DetectedEventKey.KIND]: DetectedEventKind.MOTION,
    [DetectedEventKey.FRAME]: 12,
    [DetectedEventKey.KEYS]: ['k-milk'],
  },
  {
    [DetectedEventKey.NAME]: 'kitchen/milk PlacingEvent',
    [DetectedEventKey.EVENT_TYPE]: 'PlacingEvent',
    [DetectedEventKey.TIMESTAMP]: '2026-10-28T14:02:33.250000',
    [DetectedEventKey.TRACKED_OBJECT]: 'kitchen/milk',
    [DetectedEventKey.KIND]: DetectedEventKind.PICK_AND_PLACE,
    [DetectedEventKey.FRAME]: 30,
    [DetectedEventKey.KEYS]: ['k-milk'],
  },
  {
    [DetectedEventKey.NAME]: 'kitchen/milk SupportEvent',
    [DetectedEventKey.EVENT_TYPE]: 'SupportEvent',
    [DetectedEventKey.TIMESTAMP]: '2026-10-28T14:02:33.250000',
    [DetectedEventKey.TRACKED_OBJECT]: 'kitchen/milk',
    [DetectedEventKey.WITH_OBJECT]: 'kitchen/table',
    [DetectedEventKey.KIND]: DetectedEventKind.SUPPORT,
    [DetectedEventKey.FRAME]: 30,
    [DetectedEventKey.KEYS]: ['k-milk', 'kitchen/table'],
  },
]);

/**
 * @param {Array<Object>} events The scene's events.
 * @returns {Object} A loaded scene of 10 frames a second holding the milk.
 */
const scene = (events) => ({
  description: { [SceneKey.DETECTED_EVENTS]: events },
  objects: { named: () => [{ key: 'k-milk', name: 'Milk' }] },
  frames: { framesPerSecond: 10 },
});

function openPanel() {
  const bus = new EventBus();
  const published = [];
  bus.subscribe(ViewerEvent.ENTITY_HIGHLIGHTED, (keys) => published.push(['highlight', keys]));
  bus.subscribe(ViewerEvent.FRAME_REQUESTED, (frame) => published.push(['frame', frame]));
  const marks = [];
  const panel = new SegmindPanel(new FakeDocument(), bus, (shown) => marks.push(shown));
  return { bus, panel, published, marks, root: panel.panel.element };
}

const entries = (root) => root.findAll((element) => element.className === 'segmind-event');
const kindSwitches = (root) => root.findAll((element) => element.className === 'segmind-kind');

// %% events

test('an event class name reads as words', () => {
  assert.equal(eventLabel('LossOfSupportEvent'), 'Loss of support');
  assert.equal(eventLabel('PickUpEvent'), 'Pick up');
  assert.equal(eventLabel('Wiggle'), 'Wiggle');
});

test('a body is named without its prefixes and a timestamp by its time of day', () => {
  assert.equal(shortName('kitchen/milk'), 'milk');
  assert.equal(shortName('milk'), 'milk');
  assert.equal(clockTime('2026-10-28T14:02:31.250000'), '14:02:31');
  assert.equal(clockTime('yesterday'), 'yesterday');
});

test('recorded events keep their kind, frame and keys, and older ones are other and unplaced', () => {
  const [pick] = segmindEvents(EVENTS);
  assert.equal(pick.kind, DetectedEventKind.PICK_AND_PLACE);
  assert.equal(pick.frame, 10);
  assert.deepEqual(pick.keys, ['k-milk', 'r_gripper_tool_frame']);
  const [early] = segmindEvents([{ [DetectedEventKey.NAME]: 'box SupportEvent', [DetectedEventKey.EVENT_TYPE]: 'SupportEvent', [DetectedEventKey.TIMESTAMP]: '2026-09-02T10:15:00' }]);
  assert.equal(early.kind, DetectedEventKind.OTHER);
  assert.equal(early.frame, null);
  assert.deepEqual(early.keys, []);
});

test('the event the playback passed last is current, with any at the same frame', () => {
  const events = segmindEvents(EVENTS);
  assert.deepEqual(eventMoments(events, 0), [EventMoment.FUTURE, EventMoment.FUTURE, EventMoment.FUTURE, EventMoment.FUTURE]);
  assert.deepEqual(eventMoments(events, 20), [EventMoment.PAST, EventMoment.CURRENT, EventMoment.FUTURE, EventMoment.FUTURE]);
  assert.deepEqual(eventMoments(events, 30), [EventMoment.PAST, EventMoment.PAST, EventMoment.CURRENT, EventMoment.CURRENT]);
  assert.deepEqual(eventMoments(segmindEvents([{ ...EVENTS[0], [DetectedEventKey.FRAME]: undefined }]), 5), [EventMoment.UNPLACED]);
});

// %% panel

test('a scene without events says how to record them', () => {
  const { panel, root } = openPanel();
  panel.show(scene([]));
  assert.equal(panel.panel.identifier, 'segmind');
  assert.equal(panel.panel.title, 'Segmind');
  assert.match(root.innerText, new RegExp(NO_EVENTS.slice(0, 30)));
  assert.equal(entries(root).length, 0);
});

test('every event is listed with its time into the recording, its words and its objects', () => {
  const { panel, root } = openPanel();
  panel.show(scene(EVENTS));
  const [pick, , , support] = entries(root);
  assert.equal(entries(root).length, EVENTS.length);
  assert.equal(pick.dataset.kind, DetectedEventKind.PICK_AND_PLACE);
  assert.match(pick.innerText, /0:01\.0/);
  assert.match(pick.innerText, /Pick up/);
  assert.match(pick.innerText, /Milk · r_gripper_tool_frame/);
  assert.match(support.innerText, /Milk · table/);
});

test('choosing an event lights its objects up and shows its moment', () => {
  const { panel, root, published } = openPanel();
  panel.show(scene(EVENTS));
  entries(root)[3].children[0].click();
  assert.deepEqual(published, [['highlight', ['k-milk', 'kitchen/table']], ['frame', 30]]);
});

test('the sorts of event are counted and hiding one hides it here and on the timeline', () => {
  const { panel, root, marks } = openPanel();
  panel.show(scene(EVENTS));
  assert.deepEqual(kindSwitches(root).map((button) => button.textContent), ['Pick and place 2', 'Support 1', 'Motion 1']);
  assert.deepEqual(marks.at(-1).map((mark) => mark.frame), [10, 12, 30, 30]);
  kindSwitches(root)[2].click();
  assert.equal(entries(root)[1].hidden, true);
  assert.equal(kindSwitches(root)[2].getAttribute('aria-pressed'), 'false');
  assert.deepEqual(marks.at(-1).map((mark) => mark.kind), [DetectedEventKind.PICK_AND_PLACE, DetectedEventKind.PICK_AND_PLACE, DetectedEventKind.SUPPORT]);
  kindSwitches(root)[2].click();
  assert.equal(entries(root)[1].hidden, false);
  assert.equal(marks.at(-1).length, EVENTS.length);
});

test('the playback marks the events it passed', () => {
  const { bus, panel, root } = openPanel();
  panel.show(scene(EVENTS));
  bus.publish(ViewerEvent.FRAME_CHANGED, 20);
  assert.deepEqual(entries(root).map((entry) => entry.dataset.moment), [EventMoment.PAST, EventMoment.CURRENT, EventMoment.FUTURE, EventMoment.FUTURE]);
});

test('when asked, each event lights its objects up once as the playback passes it', () => {
  const { bus, panel, published } = openPanel();
  panel.show(scene(EVENTS));
  bus.publish(ViewerEvent.FRAME_CHANGED, 11);
  assert.deepEqual(published, []);
  panel.setFollowing(true);
  bus.publish(ViewerEvent.FRAME_CHANGED, 11);
  bus.publish(ViewerEvent.FRAME_CHANGED, 30);
  bus.publish(ViewerEvent.FRAME_CHANGED, 31);
  assert.deepEqual(published, [['highlight', ['k-milk', 'r_gripper_tool_frame']], ['highlight', ['k-milk', 'kitchen/table']]]);
  assert.deepEqual(entries(panel.panel.element).map((entry) => entry.scrollRequests.length), [1, 0, 1, 0]);
});

test('live events name their time of day, mark no timeline and request no frame', () => {
  const { panel, root, published, marks } = openPanel();
  panel.show(scene([]));
  panel.showLive({ [DetectedEventsKey.EVENTS]: EVENTS.slice(0, 1) });
  assert.equal(root.findAll((element) => element.className === 'segmind-follow')[0].hidden, true);
  assert.match(entries(root)[0].innerText, /14:02:31/);
  assert.deepEqual(marks.at(-1), []);
  entries(root)[0].children[0].click();
  assert.deepEqual(published, [['highlight', ['k-milk', 'r_gripper_tool_frame']]]);
});

test('the same live events are not shown again, new ones are', () => {
  const { panel, root } = openPanel();
  panel.showLive({ [DetectedEventsKey.EVENTS]: EVENTS.slice(0, 1) });
  const [first] = entries(root);
  panel.showLive({ [DetectedEventsKey.EVENTS]: EVENTS.slice(0, 1) });
  assert.equal(entries(root)[0], first);
  panel.showLive({ [DetectedEventsKey.EVENTS]: EVENTS.slice(0, 2) });
  assert.equal(entries(root).length, 2);
});

test('the light-up button lights the event passed last at once and puts it out again', () => {
  const { bus, panel, published, root } = openPanel();
  panel.show(scene(EVENTS));
  bus.publish(ViewerEvent.FRAME_CHANGED, 12);
  const [follow] = root.findAll((element) => element.className === 'segmind-follow');
  assert.equal(follow.textContent, FOLLOW_TEXT);
  follow.click();
  assert.equal(panel.following, true);
  assert.equal(follow.getAttribute('aria-pressed'), 'true');
  follow.click();
  bus.publish(ViewerEvent.FRAME_CHANGED, 30);
  assert.equal(follow.getAttribute('aria-pressed'), 'false');
  assert.deepEqual(published, [['highlight', ['k-milk']], ['highlight', []]]);
});

test('switching the light-up off before it lit anything puts nothing out', () => {
  const { panel, published } = openPanel();
  panel.show(scene(EVENTS));
  panel.setFollowing(true);
  panel.setFollowing(false);
  assert.deepEqual(published, []);
});
