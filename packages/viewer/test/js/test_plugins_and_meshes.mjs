import { test } from 'node:test';
import assert from 'node:assert/strict';

import * as THREE from 'three';

import { PluginContext, PluginModules, PluginWithoutRegistration } from '../../src/cramera/web/app/plugin-modules.js';
import { MeshLoading, meshFormatOf, UnsupportedMeshFormat } from '../../src/cramera/web/scene/mesh-loading.js';
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
  const context = new PluginContext('bus', 'panels', 'api', 'view', 'query', info);
  assert.deepEqual(await new PluginModules(async (url) => modules[url]).register(info, context, (path) => path), ['questions', 'tour', 'workshop']);
  assert.deepEqual(registered, ['questions', 'tour', 'workshop']);
  assert.equal(context.query, 'query');
  assert.equal(context.info, info);
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
