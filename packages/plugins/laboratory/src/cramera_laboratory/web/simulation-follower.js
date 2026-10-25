/**
 * Follows the contact simulation while the viewer shows its bundle: asks for the
 * simulation's state, poses the shown models and objects as measured and draws the
 * liquid, the contacts and the pull target.
 */

import * as THREE from 'three';

import {
  ContactPhysicsKey,
  LaboratorySceneKey,
  SimulationAnswerKey,
  SimulationState,
  SnapshotKey,
  ViewerEvent,
} from '../../protocol.js';
import { SimulationView } from './simulation-view.js';

/**
 * How often a running simulation's state is asked for, in milliseconds.
 */
export const RUNNING_INTERVAL = 50;

/**
 * How often an idle or failed simulation's state is asked for, in milliseconds.
 */
export const IDLE_INTERVAL = 1000;

// %% timer

export class BrowserTimer {
  /**
   * @param {number} milliseconds The delay.
   * @param {function(): void} callback Called once the delay is over.
   * @returns {number} The handle that cancels the call.
   */
  after(milliseconds, callback) {
    return setTimeout(callback, milliseconds);
  }

  /**
   * @param {number|null} handle A handle `after` returned, or null.
   */
  cancel(handle) {
    clearTimeout(handle ?? undefined);
  }
}

// %% follower

export class SimulationFollower {
  /**
   * The application's event bus.
   * @type {import('../../core/event-bus.js').EventBus}
   */
  #bus;

  /**
   * The 3D view.
   * @type {import('../../scene/scene-view.js').SceneView}
   */
  #view;

  /**
   * The laboratory's routes.
   * @type {import('./laboratory-client.js').LaboratoryClient}
   */
  #client;

  /**
   * Schedules the next question.
   * @type {BrowserTimer}
   */
  #timer;

  /**
   * Called with every answer that belongs to the shown scene.
   * @type {function(Object, Object): void}
   */
  #onAnswer;

  /**
   * Called when the state cannot be asked for.
   * @type {function(Error): void}
   */
  #onFailure;

  /**
   * Called when a simulated scene is followed.
   * @type {function(): void}
   */
  #onFollow;

  /**
   * The shown scene, while it shows a simulation.
   * @type {import('../../scene/scene-loader.js').LoadedScene|null}
   */
  scene = null;

  /**
   * The shown simulation's controls, while a simulation is shown.
   * @type {Object|null}
   */
  controls = null;

  /**
   * The drawing over the scene, while a simulation is shown.
   * @type {SimulationView|null}
   */
  drawing = null;

  /**
   * The model owning each joint of the shown scene.
   * @type {Map<string, string>}
   */
  #jointModels = new Map();

  /**
   * The pending question's handle.
   * @type {number|null}
   */
  #pending = null;

  /**
   * Counts the scenes followed, so an answer for an earlier one is dropped.
   * @type {number}
   */
  #generation = 0;

  /**
   * Removes the bus subscriptions.
   * @type {Array<function(): void>}
   */
  #unsubscribe = [];

  /**
   * @param {import('../../core/event-bus.js').EventBus} bus The application's event bus.
   * @param {import('../../scene/scene-view.js').SceneView} view The 3D view.
   * @param {import('./laboratory-client.js').LaboratoryClient} client The laboratory's routes.
   * @param {BrowserTimer} timer Schedules the questions.
   * @param {function(Object, Object): void} onAnswer Called with each answer and the controls.
   * @param {function(): void} onFollow Called when a simulated scene is followed.
   * @param {function(Error): void} onFailure Called when the state cannot be asked for.
   */
  constructor(bus, view, client, timer, onAnswer, onFollow, onFailure) {
    this.#bus = bus;
    this.#view = view;
    this.#client = client;
    this.#timer = timer;
    this.#onAnswer = onAnswer;
    this.#onFailure = onFailure;
    this.#onFollow = onFollow;
    this.#unsubscribe.push(
      bus.subscribe(ViewerEvent.SCENE_LOADING, () => this.release()),
      bus.subscribe(ViewerEvent.SCENE_LOADED, (loaded) => this.follow(loaded)),
    );
  }

  /**
   * Follow a loaded scene if it shows a simulation.
   * @param {import('../../scene/scene-loader.js').LoadedScene} loaded The shown scene.
   */
  follow(loaded) {
    this.release();
    const controls = loaded.description[LaboratorySceneKey.CONTACT_PHYSICS];
    if (!controls) return;
    this.scene = loaded;
    this.controls = controls;
    this.#jointModels = new Map();
    for (const name of loaded.models.names()) {
      for (const joint of Object.keys(loaded.models.model(name).joints ?? {})) this.#jointModels.set(joint, name);
    }
    this.drawing = new SimulationView(controls[ContactPhysicsKey.INTERIOR], controls[ContactPhysicsKey.VESSELS]);
    this.#view.scene.add(this.drawing.group);
    this.#view.renderer.localClippingEnabled = true;
    this.#onFollow();
    this.ask(this.#generation);
  }

  /**
   * Stop following and remove the drawing.
   */
  release() {
    this.#generation += 1;
    this.#timer.cancel(this.#pending);
    this.#pending = null;
    this.drawing?.dispose();
    this.drawing = null;
    this.scene = null;
    this.controls = null;
  }

  /**
   * Ask for the simulation's state now and again after an interval. The request is
   * the boundary where a failed answer becomes a message, so its error is caught here.
   * @param {number} generation The followed scene's generation.
   * @returns {Promise<void>} Settles once the answer is shown or dropped.
   */
  async ask(generation) {
    let running = false;
    try {
      const answer = await this.#client.state();
      if (generation !== this.#generation) return;
      running = answer[SimulationAnswerKey.STATE] === SimulationState.RUNNING;
      this.show(answer);
    } catch (error) {
      if (generation !== this.#generation) return;
      this.#onFailure(error);
    }
    this.#pending = this.#timer.after(running ? RUNNING_INTERVAL : IDLE_INTERVAL, () => this.ask(generation));
  }

  /**
   * Pose the scene as the answer measures it, if it is the shown simulation's.
   * @param {Object} answer The simulation's state.
   */
  show(answer) {
    const snapshot = answer[SimulationAnswerKey.SNAPSHOT];
    if (!this.scene || !snapshot || answer[SimulationAnswerKey.SCENE] !== this.scene.name) return;
    this.scene.objects.setPoses(new Map(Object.entries(snapshot[SnapshotKey.OBJECTS])));
    this.scene.models.setJointValues(this.jointValues(snapshot[SnapshotKey.JOINTS]));
    this.placeBodies(snapshot[SnapshotKey.BODY_POSES] ?? {});
    this.drawing.show(snapshot);
    this.#view.requestRender();
    this.#onAnswer(answer, this.controls);
  }

  /**
   * @param {Object<string, number>} joints Joint positions by joint name.
   * @returns {Map<string, Map<string, number>>} The positions by model.
   */
  jointValues(joints) {
    const values = new Map();
    for (const [joint, value] of Object.entries(joints)) {
      const model = this.#jointModels.get(joint);
      if (!model) continue;
      if (!values.has(model)) values.set(model, new Map());
      values.get(model).set(joint, value);
    }
    return values;
  }

  /**
   * Place freely moving links, such as the rack, at their measured world poses.
   * @param {Object<string, Array<number>>} poses Poses by link name.
   */
  placeBodies(poses) {
    for (const [name, pose] of Object.entries(poses)) {
      for (const model of this.scene.models.names()) {
        const link = this.scene.models.model(model).links?.[name];
        const holder = link?.parent;
        if (!holder) continue;
        holder.parent.updateWorldMatrix(true, false);
        const world = new THREE.Matrix4().compose(
          new THREE.Vector3(pose[0], pose[1], pose[2]),
          new THREE.Quaternion(pose[3], pose[4], pose[5], pose[6]),
          new THREE.Vector3(1, 1, 1),
        );
        const local = holder.parent.matrixWorld.clone().invert().multiply(world);
        local.decompose(holder.position, holder.quaternion, holder.scale);
      }
    }
  }

  /**
   * Stop following and remove the subscriptions.
   */
  dispose() {
    this.release();
    for (const unsubscribe of this.#unsubscribe) unsubscribe();
  }
}
