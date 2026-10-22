/**
 * The shown workshop bundle as the contact world moves it: measured object poses and
 * drawer positions put on the loaded scene, and the workshop's camera views.
 */

import { CameraViewKey, ModelKey, SceneKey, ViewerEvent, WorkshopStateKey } from '../../protocol.js';

// %% scene

export class WorkshopScene {
  /**
   * The loaded scene.
   * @type {import('../../scene/scene-loader.js').LoadedScene}
   */
  #loaded;

  /**
   * The 3D view.
   * @type {import('../../scene/scene-view.js').SceneView}
   */
  #view;

  /**
   * The application's event bus.
   * @type {import('../../core/event-bus.js').EventBus}
   */
  #bus;

  /**
   * The model each movable joint belongs to.
   * @type {Map<string, string>}
   */
  #jointModels = new Map();

  /**
   * @param {import('../../scene/scene-loader.js').LoadedScene} loaded The loaded workshop bundle.
   * @param {import('../../scene/scene-view.js').SceneView} view The 3D view.
   * @param {import('../../core/event-bus.js').EventBus} bus The application's event bus.
   */
  constructor(loaded, view, bus) {
    this.#loaded = loaded;
    this.#view = view;
    this.#bus = bus;
    for (const model of loaded.description[SceneKey.MODELS] ?? []) {
      if (model[ModelKey.ROBOT]) continue;
      for (const joint of model[ModelKey.MOVABLE_JOINTS] ?? []) this.#jointModels.set(joint, model[ModelKey.NAME]);
    }
  }

  /**
   * Put the measured poses and drawer positions on the scene.
   * @param {Object} state The workshop's measured state.
   */
  show(state) {
    this.#loaded.objects.setPoses(new Map(Object.entries(state[WorkshopStateKey.OBJECTS] ?? {})));
    const models = new Map();
    for (const [joint, value] of Object.entries(state[WorkshopStateKey.JOINTS] ?? {})) {
      const model = this.#jointModels.get(joint);
      if (model === undefined) continue;
      if (!models.has(model)) models.set(model, new Map());
      models.get(model).set(joint, value);
    }
    this.#loaded.models.setJointValues(models);
    this.#view.requestRender();
  }

  /**
   * Look at the workshop from a named view.
   * @param {Object} view A camera view with its position and target.
   */
  look(view) {
    this.#view.camera.position.set(...view[CameraViewKey.POSITION]);
    this.#view.controls.target.set(...view[CameraViewKey.TARGET]);
    this.#view.controls.update();
    this.#view.requestRender();
  }

  /**
   * Stop the recording's playback, so it does not pose what the contact world moves.
   */
  pausePlayback() {
    this.#bus.publish(ViewerEvent.PLAYBACK_REQUESTED, false);
  }
}
