/**
 * Connects the laboratory page's controls to its simulation and local PR2 task.
 */

import * as THREE from 'three';

import {
  ContactPhysicsKey,
  LaboratoryRoute,
  TargetRequestKey,
  TaskRunKey,
  TaskRunState,
  ViewerEvent,
} from '../../protocol.js';
import { LaboratoryClient } from './laboratory-client.js';
import { LaboratoryPanel } from './laboratory-panel.js';
import { PullGesture } from './pull-gesture.js';
import { SimulationFollower } from './simulation-follower.js';

/**
 * How often a running task demo's state is asked for, in milliseconds.
 */
const TRANSFER_INTERVAL = 2000;

/**
 * Connect the laboratory controls and simulation to a native 3D view. The dedicated
 * laboratory page mounts these controls directly, without a viewer sidebar tab.
 * @param {Object} context The event bus, viewer API and 3D view.
 * @param {function(string): void} showScene Shows a laboratory scene in this view.
 * @param {Document} document The page.
 * @param {import('./simulation-follower.js').BrowserTimer} timer Schedules state requests.
 * @param {function(string, Object=): Promise<Response>} fetch Fetches a URL.
 * @param {function(LaboratoryPanel): void=} onFollow Called when a simulation is shown.
 * @param {function(Object): void=} onTransfer Called with each transfer state.
 * @returns {Promise<Object>} Controls, followers and their shared cleanup.
 */
export async function connectLaboratory(context, showScene, document, timer, fetch, onFollow = () => {}, onTransfer = () => {}) {
  const client = new LaboratoryClient(fetch, context.api);
  const lookFrom = (position, target) => context.view.lookFrom(new THREE.Vector3(...position), new THREE.Vector3(...target));
  const panel = new LaboratoryPanel(document, client, showScene, lookFrom);
  const follower = new SimulationFollower(
    context.bus,
    context.view,
    client,
    timer,
    (answer, controls) => panel.showAnswer(answer, controls, follower.scene.description),
    () => {
      onFollow(panel);
      gesture.attach(follower.scene.objects.group, follower.controls[ContactPhysicsKey.OBJECTS]);
    },
    (error) => panel.showMessage(error.reason ?? error.message, true),
  );
  const gesture = new PullGesture(
    context.view.renderer.domElement,
    context.view.camera,
    context.view.controls,
    (key, position) => panel.command(LaboratoryRoute.TARGET, { [TargetRequestKey.KEY]: key, [TargetRequestKey.POSITION]: position }),
    () => panel.command(LaboratoryRoute.RELEASE),
  );
  const unsubscribe = context.bus.subscribe(ViewerEvent.SCENE_LOADING, () => {
    panel.hideSimulation();
    gesture.detach();
  });
  let disposed = false;
  let transferTimer = null;
  let transferGeneration = 0;
  let transferError = null;
  const dispose = () => {
    disposed = true;
    transferGeneration += 1;
    timer.cancel(transferTimer);
    unsubscribe();
    follower.dispose();
    gesture.dispose();
  };
  let catalogs;
  try {
    catalogs = await Promise.all([client.laboratories(), client.devices(), client.transfer()]);
  } catch (error) {
    dispose();
    throw error;
  }
  const [laboratories, devices, transfer] = catalogs;
  panel.showLaboratories(laboratories);
  panel.showDevices(devices);
  const followTransfer = async () => {
    if (disposed) return;
    timer.cancel(transferTimer);
    transferTimer = null;
    const generation = ++transferGeneration;
    try {
      const run = await client.transfer();
      if (disposed || generation !== transferGeneration) return;
      if (transferError && panel.message.textContent === transferError) panel.showMessage('');
      transferError = null;
      panel.showTransfer(run, followTransfer);
      onTransfer(run);
      if (run[TaskRunKey.STATE] === TaskRunState.RUNNING) transferTimer = timer.after(TRANSFER_INTERVAL, followTransfer);
    } catch (error) {
      if (disposed || generation !== transferGeneration) return;
      transferError = error.reason ?? error.message;
      panel.showMessage(transferError, true);
      transferTimer = timer.after(TRANSFER_INTERVAL, followTransfer);
    }
  };
  panel.showTransfer(transfer, followTransfer);
  onTransfer(transfer);
  if (transfer[TaskRunKey.STATE] === TaskRunState.RUNNING) transferTimer = timer.after(TRANSFER_INTERVAL, followTransfer);
  return { panel, follower, gesture, dispose };
}
