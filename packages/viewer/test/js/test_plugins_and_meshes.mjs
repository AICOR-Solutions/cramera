import { test } from 'node:test';
import assert from 'node:assert/strict';

import * as THREE from 'three';

import { PluginContext, PluginModules, PluginWithoutRegistration } from '../../src/cramera/web/app/plugin-modules.js';
import { PanelHost, SidePanel } from '../../src/cramera/web/panels/panel-host.js';
import { FakeDocument } from './support/fake-document.mjs';
import { MeshLoading, meshFormatOf, paintBareCollada, UnsupportedMeshFormat } from '../../src/cramera/web/scene/mesh-loading.js';
import { MeshFormat, NavigationGroup, NavigationKey, PluginKey, ViewerInfoKey } from '../../src/cramera/web/protocol.js';

// %% plugins

test('plugin modules are imported in order and registered with the context', async () => {
  const registered = [];
  const modules = {
    '/abs/plugins/a/index.js': { register: (context) => registered.push(['a', context]) },
    '/abs/plugins/b/index.js': { register: async (context) => registered.push(['b', context]) },
  };
  const info = {
    [ViewerInfoKey.PLUGINS]: [
      { [PluginKey.NAME]: 'a', [PluginKey.MODULE]: '/plugins/a/index.js' },
      { [PluginKey.NAME]: 'routes-only' },
      { [PluginKey.NAME]: 'b', [PluginKey.MODULE]: '/plugins/b/index.js' },
    ],
  };
  const context = new PluginContext('bus', 'panels', 'api', 'view');
  const names = await new PluginModules(async (url) => modules[url]).register(info, context, (path) => `/abs${path}`);
  assert.deepEqual(names, ['a', 'b']);
  assert.deepEqual(registered.map(([name]) => name), ['a', 'b']);
  assert.equal(registered[0][1].bus, 'bus');
});

test('plugins the header links to register after those that only add to the scene page', async () => {
  const registered = [];
  const module = (name) => ({ register: () => registered.push(name) });
  const modules = { '/workshop.js': module('workshop'), '/questions.js': module('questions'), '/tour.js': module('tour') };
  const info = {
    [ViewerInfoKey.PLUGINS]: [
      { [PluginKey.NAME]: 'workshop', [PluginKey.MODULE]: '/workshop.js', [PluginKey.NAVIGATION]: { [NavigationKey.TITLE]: 'Workshop', [NavigationKey.GROUP]: NavigationGroup.LABORATORY } },
      { [PluginKey.NAME]: 'questions', [PluginKey.MODULE]: '/questions.js' },
      { [PluginKey.NAME]: 'tour', [PluginKey.MODULE]: '/tour.js' },
    ],
  };
  const context = new PluginContext('bus', new PanelHost(new FakeDocument().createElement('section')), 'api', 'view', 'query', info);
  assert.deepEqual(await new PluginModules(async (url) => modules[url]).register(info, context, (path) => path), ['questions', 'tour', 'workshop']);
  assert.deepEqual(registered, ['questions', 'tour', 'workshop']);
  assert.equal(context.query, 'query');
  assert.equal(context.info, info);
});

test('a plugin the header links to adds its panel without a tab, shown only on request', async () => {
  const document = new FakeDocument();
  const root = document.createElement('section');
  const panels = new PanelHost(root);
  const section = (name) => new SidePanel(name, name, document.createElement('section'));
  const workshop = section('workshop');
  const modules = {
    '/workshop.js': { register: (context) => context.panels.add(workshop) },
    '/questions.js': { register: (context) => context.panels.add(section('knowledge')) },
  };
  const info = {
    [ViewerInfoKey.PLUGINS]: [
      { [PluginKey.NAME]: 'workshop', [PluginKey.MODULE]: '/workshop.js', [PluginKey.NAVIGATION]: { [NavigationKey.TITLE]: 'Workshop', [NavigationKey.GROUP]: NavigationGroup.LABORATORY } },
      { [PluginKey.NAME]: 'questions', [PluginKey.MODULE]: '/questions.js' },
    ],
  };
  await new PluginModules(async (url) => modules[url]).register(info, new PluginContext('bus', panels, 'api', 'view', 'query', info), (path) => path);
  panels.add(section('steps'));
  const tabs = root.children[0].children;
  assert.deepEqual(tabs.map((tab) => tab.textContent), ['knowledge', 'steps']);
  assert.deepEqual(panels.identifiers(), ['knowledge', 'workshop', 'steps']);
  assert.equal(panels.shown, 'knowledge');
  assert.equal(workshop.element.hidden, true);
  panels.show('workshop');
  assert.equal(workshop.element.hidden, false);
  assert.deepEqual(tabs.map((tab) => tab.getAttribute('aria-selected')), ['false', 'false']);
});

test('a plugin module without register is refused', async () => {
  const info = { [ViewerInfoKey.PLUGINS]: [{ [PluginKey.NAME]: 'broken', [PluginKey.MODULE]: '/x.js' }] };
  await assert.rejects(new PluginModules(async () => ({})).register(info, new PluginContext(), (path) => path), PluginWithoutRegistration);
});

// %% meshes

test('mesh formats are read from the path, ignoring case and queries', () => {
  assert.equal(meshFormatOf('meshes/base.STL'), MeshFormat.STL);
  assert.equal(meshFormatOf('http://localhost/scenes/a/arm.glb?version=2'), MeshFormat.GLB);
  assert.equal(meshFormatOf('meshes/robot.dae'), MeshFormat.COLLADA);
  assert.equal(meshFormatOf('meshes/readme.txt'), null);
});

test('a mesh of an unknown format is refused', async () => {
  const loading = new MeshLoading(new THREE.LoadingManager(), () => {});
  await assert.rejects(loading.load('meshes/model.fbx'), UnsupportedMeshFormat);
});

test('a COLLADA document without materials takes its URDF material, one with materials keeps them', () => {
  const urdfMaterial = new THREE.MeshPhongMaterial({ color: 0xd98229 });
  const document = (materials) => {
    const scene = new THREE.Group();
    scene.add(new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshPhongMaterial()));
    return { scene, library: { materials } };
  };
  const bare = paintBareCollada(document({}), urdfMaterial);
  const painted = paintBareCollada(document({ wood: {} }), urdfMaterial);
  const unnamed = paintBareCollada(document({}), undefined);
  assert.equal(bare.children[0].material, urdfMaterial);
  assert.notEqual(painted.children[0].material, urdfMaterial);
  assert.notEqual(unnamed.children[0].material, urdfMaterial);
});
