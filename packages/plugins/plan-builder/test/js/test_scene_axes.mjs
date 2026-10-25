import { test } from 'node:test';
import assert from 'node:assert/strict';

import * as THREE from 'three';

import { ORIGIN_AXES_NAME, SceneAxes, WORLD_AXES } from '../../src/cramera_plan_builder/web/builder/scene-axes.js';

/**
 * Hands out canvases whose 2D context records the text drawn on them.
 */
class CanvasDocument {
  constructor() {
    this.texts = [];
  }

  createElement() {
    const texts = this.texts;
    const context = { fillText: (text) => texts.push(text) };
    return { width: 0, height: 0, getContext: () => context };
  }
}

/**
 * Stands for the viewer's 3D view: a scene, a camera, and a renderer that records what
 * it draws.
 */
class FakeView {
  constructor() {
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera();
    this.size = { width: 800, height: 600 };
    this.listeners = new Set();
    this.drawn = [];
    this.viewports = [];
    this.renderer = {
      autoClear: true,
      clearDepth: () => {},
      setScissorTest: () => {},
      setScissor: () => {},
      setViewport: (...viewport) => this.viewports.push(viewport),
      render: (scene, camera) => this.drawn.push({ scene, camera, quaternion: camera.quaternion.clone() }),
    };
  }

  onRender(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  requestRender() {}

  rendered() {
    for (const listener of this.listeners) listener();
  }
}

test('the origin carries an arrow and a label along each of x, y and z', () => {
  const view = new FakeView();
  const document = new CanvasDocument();
  new SceneAxes(view, document);
  const origin = view.scene.getObjectByName(ORIGIN_AXES_NAME);
  assert.ok(origin);
  for (const axis of WORLD_AXES) {
    const arrow = origin.getObjectByName(axis.name);
    const along = new THREE.Vector3(0, 1, 0).applyQuaternion(arrow.quaternion);
    assert.ok(along.distanceTo(new THREE.Vector3(...axis.direction)) < 1e-6, axis.name);
    const label = origin.getObjectByName(`${axis.name}-label`);
    assert.ok(label.position.clone().normalize().distanceTo(new THREE.Vector3(...axis.direction)) < 1e-6, axis.name);
    arrow.traverse((child) => {
      if (child.isMesh) assert.equal(child.material.color.getHex(), axis.color);
    });
  }
  assert.deepEqual(document.texts, ['x', 'y', 'z', 'x', 'y', 'z']);
});

test('the compass turns with the camera and is drawn in a corner after each frame', () => {
  const view = new FakeView();
  new SceneAxes(view, new CanvasDocument());
  view.camera.position.set(-2, -3, 4);
  view.camera.lookAt(0, 0, 0);
  view.rendered();
  assert.equal(view.drawn.length, 1);
  const [{ scene, camera, quaternion }] = view.drawn;
  assert.notEqual(scene, view.scene);
  assert.ok(quaternion.angleTo(view.camera.quaternion) < 1e-6);
  assert.ok(camera.position.clone().normalize().distanceTo(view.camera.position.clone().normalize()) < 1e-6);
  const [corner, whole] = view.viewports;
  assert.ok(corner[2] < view.size.width && corner[3] < view.size.height);
  assert.deepEqual(whole, [0, 0, view.size.width, view.size.height]);
  assert.equal(view.renderer.autoClear, true);
});

test('a disposed map leaves the scene and the frames', () => {
  const view = new FakeView();
  const axes = new SceneAxes(view, new CanvasDocument());
  axes.dispose();
  assert.equal(view.scene.getObjectByName(ORIGIN_AXES_NAME), undefined);
  view.rendered();
  assert.equal(view.drawn.length, 0);
});
