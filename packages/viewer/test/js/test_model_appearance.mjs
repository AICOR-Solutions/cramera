import { test } from 'node:test';
import assert from 'node:assert/strict';

import * as THREE from 'three';

import { DRAWN_WHITE, dressModel, environmentLookOf, standardOf } from '../../src/cramera/web/scene/model-appearance.js';

/**
 * A model as urdf-loader builds one: a link holding a mesh with the given material.
 */
function modelWith(linkName, material) {
  const model = new THREE.Group();
  const link = new THREE.Group();
  link.isURDFLink = true;
  link.name = linkName;
  link.add(new THREE.Mesh(new THREE.BoxGeometry(), material));
  model.add(link);
  return { model, mesh: () => link.children[0] };
}

test('a legacy material becomes a physically based one with its colour, texture and transparency', () => {
  const texture = new THREE.Texture();
  const phong = new THREE.MeshPhongMaterial({ color: 0x336699, map: texture, opacity: 0.5, transparent: true });
  const standard = standardOf(phong);
  assert.equal(standard.isMeshStandardMaterial, true);
  assert.equal(standard.color.getHex(), 0x336699);
  assert.equal(standard.map, texture);
  assert.deepEqual([standard.opacity, standard.transparent], [0.5, true]);
});

test('a blown-out white is toned down, a textured one keeps its texture untouched', () => {
  assert.deepEqual(standardOf(new THREE.MeshLambertMaterial({ color: 0xffffff })).color.toArray(), [...DRAWN_WHITE]);
  const textured = standardOf(new THREE.MeshPhongMaterial({ color: 0xffffff, map: new THREE.Texture() }));
  assert.equal(textured.color.getHex(), 0xffffff);
});

test('an environment part is named by the vocabulary of what it is, first match first', () => {
  assert.equal(environmentLookOf('apartment/island_countertop'), environmentLookOf('countertop'));
  assert.notEqual(environmentLookOf('cabinet1_drawer_top'), null);
  assert.notEqual(environmentLookOf('handle_cab1_drawer'), environmentLookOf('cabinet1_drawer_top'));
  assert.equal(environmentLookOf('warehouse_beam_7'), null);
});

test('an uncoloured environment part gets the colour of what it is, an authored colour stays', () => {
  const plain = modelWith('kitchen/countertop', new THREE.MeshPhongMaterial({ color: 0xffffff }));
  const authored = modelWith('kitchen/countertop', new THREE.MeshPhongMaterial({ color: 0x00ff00 }));
  dressModel(plain.model, true);
  dressModel(authored.model, true);
  assert.equal(plain.mesh().material.color.getHex(), environmentLookOf('countertop').color);
  assert.equal(authored.mesh().material.color.getHex(), 0x00ff00);
});

test('a robot keeps its colours and only loses blown-out whites', () => {
  const robot = modelWith('pr2/l_gripper_palm_link', new THREE.MeshPhongMaterial({ color: 0xffffff }));
  dressModel(robot.model, false);
  assert.deepEqual(robot.mesh().material.color.toArray(), [...DRAWN_WHITE]);
});

test('lights a model file brought are removed', () => {
  const { model } = modelWith('oven', new THREE.MeshPhongMaterial());
  model.children[0].add(new THREE.PointLight());
  dressModel(model, true);
  const lights = [];
  model.traverse((child) => { if (child.isLight) lights.push(child); });
  assert.deepEqual(lights, []);
});
