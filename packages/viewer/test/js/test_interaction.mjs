import { test } from 'node:test';
import assert from 'node:assert/strict';

import { KeyboardShortcuts, PlaybackActions, ShortcutKey } from '../../src/cramera/web/app/keyboard-shortcuts.js';
import { DetailsPanel } from '../../src/cramera/web/panels/details-panel.js';
import { ViewPanel, ViewSwitch } from '../../src/cramera/web/panels/view-panel.js';
import { SelectionKey, SelectionKind } from '../../src/cramera/web/protocol.js';
import { selectionOf } from '../../src/cramera/web/scene/scene-picking.js';
import { FakeDocument } from './support/fake-document.mjs';

// %% selection

/**
 * @param {Object} properties The node's own properties.
 * @param {Object|null} parent Its parent.
 * @returns {Object} A scene graph node.
 */
function node(properties, parent = null) {
  return { userData: {}, ...properties, parent };
}

test('a mesh selects the innermost link it belongs to and that link\'s model', () => {
  const robot = node({ isURDFRobot: true, name: 'pr2' });
  const arm = node({ isURDFLink: true, urdfName: 'l_upper_arm_link' }, robot);
  const hand = node({ isURDFLink: true, urdfName: 'l_gripper_palm_link' }, arm);
  const mesh = node({}, node({}, hand));
  assert.deepEqual(selectionOf(mesh), {
    [SelectionKey.KIND]: SelectionKind.LINK,
    [SelectionKey.MODEL]: 'pr2',
    [SelectionKey.NAME]: 'l_gripper_palm_link',
  });
});

test('a mesh of a free object selects the object by its key', () => {
  const holder = node({ userData: { objectKey: 'milk.stl' } });
  assert.deepEqual(selectionOf(node({}, holder)), { [SelectionKey.KIND]: SelectionKind.OBJECT, [SelectionKey.NAME]: 'milk.stl' });
});

test('a mesh outside links and objects selects nothing', () => {
  assert.equal(selectionOf(node({}, node({}))), null);
});

test('details show the selection above the scene facts and clear it again', () => {
  const details = new DetailsPanel(new FakeDocument());
  details.showSelection({ [SelectionKey.KIND]: SelectionKind.LINK, [SelectionKey.MODEL]: 'pr2', [SelectionKey.NAME]: 'base_link' });
  assert.match(details.panel.element.innerText, /Selected.*Linkbase_link.*Modelpr2/s);
  details.showSelection({ [SelectionKey.KIND]: SelectionKind.OBJECT, [SelectionKey.NAME]: 'cup' });
  assert.match(details.panel.element.innerText, /Objectcup/);
  details.showSelection(null);
  assert.doesNotMatch(details.panel.element.innerText, /Selected/);
});

// %% view panel

test('view switches show and change their state', () => {
  let occlusion = false;
  const panel = new ViewPanel(new FakeDocument(), [new ViewSwitch('Ambient occlusion', () => occlusion, (enabled) => { occlusion = enabled; })]);
  const input = panel.panel.element.children[0].children[0];
  assert.equal(input.checked, false);
  input.checked = true;
  input.dispatch('change');
  assert.equal(occlusion, true);
  occlusion = false;
  panel.refresh();
  assert.equal(input.checked, false);
});

// %% keyboard

test('shortcuts play, step and jump, but not while a form control has focus', () => {
  const document = new FakeDocument();
  const calls = [];
  const shortcuts = new KeyboardShortcuts(document.documentElement, new PlaybackActions(() => calls.push('toggle'), (frames) => calls.push(['step', frames]), (last) => calls.push(['jump', last])));
  const press = (key, target = document.body, modifiers = {}) => document.documentElement.dispatch('keydown', { key, target, ...modifiers });
  press(ShortcutKey.PLAY_PAUSE);
  press(ShortcutKey.PREVIOUS_FRAME);
  press(ShortcutKey.NEXT_FRAME);
  press(ShortcutKey.FIRST_FRAME);
  press(ShortcutKey.LAST_FRAME);
  press('x');
  press(ShortcutKey.PLAY_PAUSE, document.createElement('select'));
  press(ShortcutKey.NEXT_FRAME, document.body, { ctrlKey: true });
  assert.deepEqual(calls, ['toggle', ['step', -1], ['step', 1], ['jump', false], ['jump', true]]);
  shortcuts.dispose();
  press(ShortcutKey.PLAY_PAUSE);
  assert.equal(calls.length, 5);
});

// %% highlight

import * as THREE from 'three';
import { ownBounds } from '../../src/cramera/web/scene/scene-picking.js';

test('a link\'s box encloses its own meshes, not the links below it', () => {
  const link = Object.assign(new THREE.Group(), { isURDFLink: true });
  link.add(new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1)));
  const joint = Object.assign(new THREE.Group(), { isURDFJoint: true });
  joint.position.set(5, 0, 0);
  joint.add(new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1)));
  link.add(joint);
  const box = ownBounds(link);
  assert.deepEqual(box.min.toArray(), [-0.5, -0.5, -0.5]);
  assert.deepEqual(box.max.toArray(), [0.5, 0.5, 0.5]);
});
