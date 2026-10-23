import { test } from 'node:test';
import assert from 'node:assert/strict';

import { DetailsPanel } from '../../src/cramera/web/panels/details-panel.js';
import { DuplicatePanel, PanelHost, SidePanel } from '../../src/cramera/web/panels/panel-host.js';
import { SceneChoice } from '../../src/cramera/web/panels/scene-choice.js';
import { ScenePickerView } from '../../src/cramera/web/panels/scene-picker-view.js';
import { PlaybackClock } from '../../src/cramera/web/playback/playback-clock.js';
import { formatSeconds, MarkKind, marksOf, SPEEDS, TimelineView } from '../../src/cramera/web/playback/timeline-view.js';
import { IndexEntryKey, IndexKey, SceneKey, SegmentKey } from '../../src/cramera/web/protocol.js';
import { FakeDocument } from './support/fake-document.mjs';

const SEGMENTS = [
  { [SegmentKey.STEP]: 'park', [SegmentKey.START]: 0, [SegmentKey.END]: 9 },
  { [SegmentKey.STEP]: 'pick', [SegmentKey.START]: 20, [SegmentKey.END]: 29 },
];

// %% panel host

test('the first panel is shown and tabs switch between panels', () => {
  const document = new FakeDocument();
  const host = new PanelHost(document.createElement('aside'));
  const first = new SidePanel('a', 'A', document.createElement('section'));
  const second = new SidePanel('b', 'B', document.createElement('section'));
  host.add(first);
  host.add(second);
  assert.equal(host.shown, 'a');
  assert.equal(second.element.hidden, true);
  host.show('b');
  assert.equal(first.element.hidden, true);
  assert.deepEqual(host.identifiers(), ['a', 'b']);
  assert.throws(() => host.add(new SidePanel('a', 'Again', document.createElement('section'))), DuplicatePanel);
});

test('the strip wraps instead of cutting tabs off, and untabbed panels are not chosen first', () => {
  const document = new FakeDocument();
  const host = new PanelHost(document.createElement('aside'));
  host.add(new SidePanel('lab', 'Lab', document.createElement('section')), false);
  host.add(new SidePanel('a', 'A', document.createElement('section')));
  assert.equal(host.shown, 'a');
  assert.equal(host.tabbed('lab'), false);
  assert.equal(host.tabbed('a'), true);
});

test('details name the scene and every file that could not be loaded', () => {
  const document = new FakeDocument();
  const details = new DetailsPanel(document);
  details.show({
    name: 'cell',
    description: { [SceneKey.TASK]: 'pick', [SceneKey.MODELS]: [{ name: 'arm' }], [SceneKey.MISSING_ASSETS]: ['meshes/a.stl'] },
    frames: { frameCount: 10, framesPerSecond: 5 },
    missingFiles: () => ['meshes/b.mtl'],
  });
  const text = details.panel.element.innerText;
  assert.match(text, /cell/);
  assert.match(text, /meshes\/a\.stl, meshes\/b\.mtl/);
  assert.match(text, /10 at 5 per second/);
});

// %% picker

test('the scene picker offers the recorded combinations and reports the chosen bundle', () => {
  const document = new FakeDocument();
  const chosen = [];
  const index = {
    [IndexKey.SCENES]: [
      { [IndexEntryKey.NAME]: 'one', [IndexEntryKey.ROBOT]: 'pr2', [IndexEntryKey.ENVIRONMENT]: 'kitchen', [IndexEntryKey.TASK]: 'pick' },
      { [IndexEntryKey.NAME]: 'two', [IndexEntryKey.ROBOT]: 'tiago', [IndexEntryKey.ENVIRONMENT]: 'kitchen', [IndexEntryKey.TASK]: 'pick' },
    ],
  };
  const root = document.createElement('nav');
  new ScenePickerView(root, new SceneChoice(index), (name) => chosen.push(name));
  const robot = root.children[0].children[1];
  assert.equal(robot.disabled, false);
  assert.equal(root.children[1].children[1].disabled, true);
  robot.value = 'tiago';
  robot.dispatch('change');
  assert.deepEqual(chosen, ['two']);
});

// %% timeline

test('the controls stay disabled for a still scene and follow a recording\'s clock', () => {
  const document = new FakeDocument();
  const root = document.createElement('footer');
  const sought = [];
  const timeline = new TimelineView(root, (frame) => sought.push(frame), () => {});
  const [buttons, scrub] = root.children;
  const [play, , speed] = buttons.children;
  const [track, text] = scrub.children;
  const [slider, marks] = track.children;
  assert.equal(play.disabled, true);
  assert.equal(slider.disabled, true);
  const clock = new PlaybackClock(10, 31);
  timeline.show(clock, SEGMENTS);
  assert.equal(play.disabled, false);
  assert.equal(speed.children.length, SPEEDS.length);
  assert.equal(marks.children[1].style.left, `${(100 * 20) / 30}%`);
  play.dispatch('click');
  assert.equal(clock.playing, true);
  assert.equal(play.getAttribute('aria-pressed'), 'true');
  speed.value = '4';
  speed.dispatch('change');
  assert.equal(clock.speed, 4);
  slider.value = '12';
  slider.dispatch('input');
  assert.deepEqual(sought, [12]);
  clock.seek(25);
  timeline.update(1);
  assert.equal(marks.children[1].classList.contains('current'), true);
  assert.equal(marks.children[0].classList.contains('current'), false);
  assert.equal(text.textContent, `${formatSeconds(2.5)} / ${formatSeconds(clock.duration)}`);
  assert.equal(text.title, 'frame 25');
  marks.children[0].dispatch('click');
  assert.deepEqual(sought, [12, 0]);
  timeline.show(new PlaybackClock(10, 1), []);
  assert.equal(play.disabled, true);
  assert.equal(marks.children.length, 0);
});

test('the marks show where steps start, pick up and let go, by kind', () => {
  const segments = [
    { [SegmentKey.STEP]: 'reach', [SegmentKey.START]: 0, [SegmentKey.END]: 40, [SegmentKey.PICKS]: 'milk', [SegmentKey.ATTACH]: 10, [SegmentKey.DETACH]: 30 },
    { [SegmentKey.STEP]: 'park', [SegmentKey.START]: 41, [SegmentKey.END]: 50 },
  ];
  const marks = marksOf(segments);
  assert.deepEqual(marks.map((mark) => [mark.kind, mark.frame, mark.segment]), [
    [MarkKind.STEP, 0, 0],
    [MarkKind.PICK, 10, 0],
    [MarkKind.RELEASE, 30, 0],
    [MarkKind.STEP, 41, 1],
  ]);
  assert.match(marks[1].text, /milk/);
  const document = new FakeDocument();
  const root = document.createElement('footer');
  new TimelineView(root, () => {}, () => {}).show(new PlaybackClock(10, 51), segments);
  const drawn = root.children[1].children[0].children[1].children;
  assert.deepEqual(drawn.map((mark) => mark.className), marks.map((mark) => `mark mark-${mark.kind}`));
});

test('the save button is offered only while a live episode can be saved', () => {
  const document = new FakeDocument();
  const root = document.createElement('footer');
  let saves = 0;
  const timeline = new TimelineView(root, () => {}, () => { saves += 1; });
  const save = root.children[0].children[1];
  assert.equal(save.hidden, true);
  timeline.setSaveOffered(true);
  assert.equal(save.hidden, false);
  save.dispatch('click');
  assert.equal(saves, 1);
});

test('playback can be started and paused without a click', () => {
  const document = new FakeDocument();
  const root = document.createElement('footer');
  const timeline = new TimelineView(root, () => {}, () => {});
  timeline.setPlaying(true);
  const clock = new PlaybackClock(10, 31);
  timeline.show(clock, SEGMENTS);
  timeline.setPlaying(true);
  const play = root.children[0].children[0];
  assert.equal(clock.playing, true);
  assert.equal(play.getAttribute('aria-pressed'), 'true');
  timeline.setPlaying(false);
  assert.equal(clock.playing, false);
  assert.equal(play.getAttribute('aria-pressed'), 'false');
});

test('durations read as minutes and seconds with tenths', () => {
  assert.equal(formatSeconds(0), '0:00.0');
  assert.equal(formatSeconds(75.25), '1:15.3');
});

test('the scene picker hides when there are no scenes to choose', () => {
  const document = new FakeDocument();
  const root = document.createElement('nav');
  new ScenePickerView(root, new SceneChoice({}), () => {});
  assert.equal(root.hidden, true);
});
