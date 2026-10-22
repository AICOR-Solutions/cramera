import { test } from 'node:test';
import assert from 'node:assert/strict';

import { DetailsPanel } from '../../src/cramera/web/panels/details-panel.js';
import { DuplicatePanel, PanelHost, SidePanel } from '../../src/cramera/web/panels/panel-host.js';
import { PlanPanel } from '../../src/cramera/web/panels/plan-panel.js';
import { SceneChoice } from '../../src/cramera/web/panels/scene-choice.js';
import { ScenePickerView } from '../../src/cramera/web/panels/scene-picker-view.js';
import { StepsPanel } from '../../src/cramera/web/panels/steps-panel.js';
import { PlaybackClock } from '../../src/cramera/web/playback/playback-clock.js';
import { formatSeconds, SPEEDS, TimelineView } from '../../src/cramera/web/playback/timeline-view.js';
import { IndexEntryKey, IndexKey, PlanNodeKey, SceneKey, SegmentKey } from '../../src/cramera/web/protocol.js';
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

// %% steps and plan

test('steps are listed, marked and jump to their start', () => {
  const document = new FakeDocument();
  const sought = [];
  const steps = new StepsPanel(document, (frame) => sought.push(frame));
  steps.show(SEGMENTS);
  const buttons = steps.panel.element.children;
  assert.equal(buttons[1].textContent, '2. pick');
  buttons[1].dispatch('click');
  assert.deepEqual(sought, [SEGMENTS[1][SegmentKey.START]]);
  steps.mark(1);
  assert.equal(buttons[1].classList.contains('current'), true);
  steps.show([]);
  assert.equal(steps.panel.element.children[0].className, 'empty');
});

test('the plan tree shows every node with its kind and state', () => {
  const document = new FakeDocument();
  const plan = new PlanPanel(document);
  plan.show([{ [PlanNodeKey.KIND]: 'SequentialNode', [PlanNodeKey.LABEL]: 'run', [PlanNodeKey.STATUS]: 'SUCCEEDED', [PlanNodeKey.CHILDREN]: [{ [PlanNodeKey.KIND]: 'ActionNode', [PlanNodeKey.LABEL]: 'pick up the cup', [PlanNodeKey.STATUS]: 'FAILED' }] }]);
  const rows = plan.panel.element.findAll((element) => element.className === 'plan-node');
  assert.equal(rows.length, 2);
  assert.equal(rows[1].dataset.status, 'FAILED');
  assert.match(rows[1].innerText, /pick up the cup/);
  plan.show([]);
  assert.match(plan.panel.element.innerText, /no recorded plan/);
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

test('the timeline hides for a still scene and follows its clock', () => {
  const document = new FakeDocument();
  const root = document.createElement('footer');
  const sought = [];
  const timeline = new TimelineView(root, (frame) => sought.push(frame));
  assert.equal(root.hidden, true);
  const clock = new PlaybackClock(10, 31);
  timeline.show(clock, SEGMENTS);
  assert.equal(root.hidden, false);
  const [play, speed, track, text] = root.children;
  assert.equal(speed.children.length, SPEEDS.length);
  assert.equal(track.children[1].children[1].style.left, `${(100 * 20) / 31}%`);
  play.dispatch('click');
  assert.equal(clock.playing, true);
  assert.equal(play.textContent, 'Pause');
  speed.value = '4';
  speed.dispatch('change');
  assert.equal(clock.speed, 4);
  track.children[0].value = '12';
  track.children[0].dispatch('input');
  assert.deepEqual(sought, [12]);
  clock.seek(25);
  timeline.update(1);
  assert.equal(track.children[1].children[1].classList.contains('current'), true);
  assert.match(text.textContent, /frame 25/);
  timeline.show(new PlaybackClock(10, 1), []);
  assert.equal(root.hidden, true);
});

test('durations read as minutes and seconds with tenths', () => {
  assert.equal(formatSeconds(0), '0:00.0');
  assert.equal(formatSeconds(75.25), '1:15.3');
});
