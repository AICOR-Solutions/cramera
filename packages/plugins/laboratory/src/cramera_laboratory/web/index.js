/**
 * Connects the laboratory page's controls to its simulation and local PR2 task.
 */

import * as THREE from 'three';

import {
  ContactPhysicsKey,
  LaboratoryDemo,
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
 * How often a running robot demo's state is asked for, in milliseconds.
 */
const DEMO_INTERVAL = 2000;

/**
 * Connect the laboratory controls and simulation to a native 3D view. The dedicated
 * laboratory page mounts these controls directly, without a viewer sidebar tab.
 * @param {Object} context The event bus, viewer API and 3D view.
 * @param {function(string): void} showScene Shows a laboratory scene in this view.
 * @param {Document} document The page.
 * @param {import('./simulation-follower.js').BrowserTimer} timer Schedules state requests.
 * @param {function(string, Object=): Promise<Response>} fetch Fetches a URL.
 * @param {function(LaboratoryPanel): void=} onFollow Called when a simulation is shown.
 * @param {function(string, Object): void=} onDemo Called with each robot demo and its state.
 * @returns {Promise<Object>} Controls, followers and their shared cleanup.
 */
export async function connectLaboratory(context, showScene, document, timer, fetch, onFollow = () => {}, onDemo = () => {}) {
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
  const demos = Object.values(LaboratoryDemo);
  const demoTimers = new Map();
  const generations = new Map(demos.map((demo) => [demo, 0]));
  let demoError = null;
  const dispose = () => {
    disposed = true;
    for (const demo of demos) {
      generations.set(demo, generations.get(demo) + 1);
      timer.cancel(demoTimers.get(demo) ?? null);
    }
    unsubscribe();
    follower.dispose();
    gesture.dispose();
  };
  let catalogs;
  try {
    catalogs = await Promise.all([client.laboratories(), client.devices(), ...demos.map((demo) => client.demo(demo))]);
  } catch (error) {
    dispose();
    throw error;
  }
  const [laboratories, devices, ...runs] = catalogs;
  panel.showLaboratories(laboratories);
  panel.showDevices(devices);
  const show = (demo, run) => {
    panel.showDemo(demo, run, () => followDemo(demo));
    onDemo(demo, run);
    if (run[TaskRunKey.STATE] === TaskRunState.RUNNING) demoTimers.set(demo, timer.after(DEMO_INTERVAL, () => followDemo(demo)));
  };
  const followDemo = async (demo) => {
    if (disposed) return;
    timer.cancel(demoTimers.get(demo) ?? null);
    demoTimers.delete(demo);
    const generation = generations.get(demo) + 1;
    generations.set(demo, generation);
    try {
      const run = await client.demo(demo);
      if (disposed || generation !== generations.get(demo)) return;
      if (demoError && panel.message.textContent === demoError) panel.showMessage('');
      demoError = null;
      show(demo, run);
    } catch (error) {
      if (disposed || generation !== generations.get(demo)) return;
      demoError = error.reason ?? error.message;
      panel.showMessage(demoError, true);
      demoTimers.set(demo, timer.after(DEMO_INTERVAL, () => followDemo(demo)));
    }
  };
  demos.forEach((demo, index) => show(demo, runs[index]));
  return { panel, follower, gesture, dispose };
}
