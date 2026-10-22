/**
 * The laboratory plugin's browser module: adds the Laboratory panel and follows the
 * contact simulation whenever the viewer shows its bundle.
 */

import * as THREE from 'three';

import { withScene } from '../../core/scene-address.js';
import { IndexEntryKey, IndexKey, TaskRunKey, TaskRunState, ViewerEvent } from '../../protocol.js';
import { LaboratoryClient } from './laboratory-client.js';
import { LaboratoryPanel } from './laboratory-panel.js';
import { BrowserTimer, SimulationFollower } from './simulation-follower.js';

/**
 * How often a running task demo's state is asked for, in milliseconds.
 */
const TRANSFER_INTERVAL = 2000;

/**
 * The panel's stylesheet, next to this module.
 */
const STYLESHEET = new URL('./laboratory.css', import.meta.url).href;

// %% registration

/**
 * Add the Laboratory panel, list the laboratories and devices, and follow simulations.
 * @param {import('../../app/plugin-modules.js').PluginContext} context What the viewer offers plugins.
 * @param {Document=} document The page.
 * @param {BrowserTimer=} timer Schedules the simulation's state requests.
 * @param {Location=} location The page's location, loaded anew for a bundle the page does not list.
 * @param {function(string, Object=): Promise<Response>=} fetch Fetches a URL.
 * @returns {Promise<{panel: LaboratoryPanel, follower: SimulationFollower}>} The panel and the follower.
 */
export async function register(
  context,
  document = globalThis.document,
  timer = new BrowserTimer(),
  location = globalThis.location,
  fetch = (url, options) => globalThis.fetch(url, options),
) {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = STYLESHEET;
  document.head.append(link);
  const client = new LaboratoryClient(fetch, context.api);
  const index = await context.api.scenes();
  const listed = new Set((index[IndexKey.SCENES] ?? []).map((entry) => entry[IndexEntryKey.NAME]));
  const showScene = (name) => {
    if (listed.has(name)) context.bus.publish(ViewerEvent.SCENE_REQUESTED, name);
    else location.assign(withScene(location.href, name).href);
  };
  const lookFrom = (position, target) => context.view.lookFrom(new THREE.Vector3(...position), new THREE.Vector3(...target));
  const panel = new LaboratoryPanel(document, client, showScene, lookFrom);
  context.panels.add(panel.panel);
  const follower = new SimulationFollower(
    context.bus,
    context.view,
    client,
    timer,
    (answer, controls) => panel.showAnswer(answer, controls, follower.scene.description),
    () => context.panels.show(panel.panel.identifier),
    (error) => panel.showMessage(error.reason ?? error.message, true),
  );
  context.bus.subscribe(ViewerEvent.SCENE_LOADING, () => panel.hideSimulation());
  const [laboratories, devices, transfer] = await Promise.all([client.laboratories(), client.devices(), client.transfer()]);
  panel.showLaboratories(laboratories);
  panel.showDevices(devices);
  const followTransfer = async () => {
    const run = await client.transfer();
    panel.showTransfer(run, followTransfer);
    if (run[TaskRunKey.STATE] === TaskRunState.RUNNING) timer.after(TRANSFER_INTERVAL, followTransfer);
  };
  panel.showTransfer(transfer, followTransfer);
  if (transfer[TaskRunKey.STATE] === TaskRunState.RUNNING) timer.after(TRANSFER_INTERVAL, followTransfer);
  return { panel, follower };
}
