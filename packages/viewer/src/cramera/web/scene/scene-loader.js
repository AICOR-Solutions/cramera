/**
 * Loading one bundle into the 3D view: its documents, models, objects and lights.
 */

import * as THREE from 'three';

import { BundleFile, CameraKey, LiveStateKey, RenderingKey, SceneKey, TrajectoryKey } from '../protocol.js';
import { Bounds } from './bounds.js';
import { LoadingProgress } from './loading-progress.js';
import { SceneModels } from './scene-models.js';
import { SceneObjects } from './scene-objects.js';
import { LightingDescription, LightingRoom } from './stage-lighting.js';
import { TrajectoryFrames } from './trajectory-frames.js';

/**
 * The region framed and shadowed for a scene without content: a metre around the origin.
 */
const EMPTY_SCENE_BOUNDS = new Bounds([-1, -1, 0], [1, 1, 1]);

/**
 * The smallest half width of the region a robot recording is framed by, in metres:
 * enough to show the robot's surroundings.
 */
const FOCUS_HALF_WIDTH = 1.0;

// %% loaded scene

export class LoadedScene {
  /**
   * @param {string} name The bundle's name.
   * @param {Object} description The scene description.
   * @param {TrajectoryFrames} frames What each frame sets.
   * @param {SceneModels} models The loaded models.
   * @param {SceneObjects} objects The loaded free objects.
   * @param {Object|null} statecharts The statecharts document, or null.
   * @param {Array<string>} failedUrls The requests that failed.
   */
  constructor(name, description, frames, models, objects, statecharts, failedUrls) {
    /**
     * The bundle's name.
     * @type {string}
     */
    this.name = name;
    /**
     * The scene description.
     * @type {Object}
     */
    this.description = description;
    /**
     * What each frame sets.
     * @type {TrajectoryFrames}
     */
    this.frames = frames;
    /**
     * The loaded models.
     * @type {SceneModels}
     */
    this.models = models;
    /**
     * The loaded free objects.
     * @type {SceneObjects}
     */
    this.objects = objects;
    /**
     * The statecharts document, or null.
     * @type {Object|null}
     */
    this.statecharts = statecharts;
    /**
     * The requests that failed while loading.
     * @type {Array<string>}
     */
    this.failedUrls = failedUrls;
  }

  /**
   * Show one frame.
   * @param {number} frame The frame.
   */
  showFrame(frame) {
    this.models.setJointValues(this.frames.jointValues(frame));
    this.models.setRobotPose(this.frames.robotPose(frame));
    this.models.setInstancePoses(this.frames.instancePoses(frame));
    this.objects.setPoses(this.frames.objectPoses(frame));
  }

  /**
   * Show a live publisher's world state.
   * @param {Object} state A live state.
   */
  showState(state) {
    this.models.setJointValues(this.frames.jointValuesOf(state[LiveStateKey.FRAMES] ?? {}));
    this.models.setRobotPose(state[LiveStateKey.BASE] ?? null);
    this.models.setInstancePoses(new Map(Object.entries(state[LiveStateKey.MODEL_BASES] ?? {})));
    this.objects.setPoses(new Map(Object.entries(state[LiveStateKey.OBJECTS] ?? {})));
  }

  /**
   * @returns {THREE.Vector3|null} Where the first robot stands, or null for a scene
   *   without robots.
   */
  robotPosition() {
    const [robot] = this.models.robotModels();
    return robot ? robot.getWorldPosition(new THREE.Vector3()) : null;
  }

  /**
   * @returns {Array<string>} Every file that could not be loaded, each once.
   */
  missingFiles() {
    const failures = [...this.models.meshFailures(), ...this.objects.meshFailures()].map((failure) => failure.url);
    return [...new Set([...failures, ...this.failedUrls])].sort();
  }

  /**
   * Free the models and objects.
   */
  dispose() {
    this.models.dispose();
    this.objects.dispose();
  }
}

// %% loader

export class SceneLoader {
  /**
   * The viewer's routes.
   * @type {import('../core/viewer-api.js').ViewerApi}
   */
  #api;

  /**
   * @param {import('../core/viewer-api.js').ViewerApi} api The viewer's routes.
   */
  constructor(api) {
    this.#api = api;
  }

  /**
   * Load a bundle into a view, replacing what the view showed.
   * @param {string} name The bundle's name.
   * @param {import('./scene-view.js').SceneView} view The view.
   * @param {import('./scene-lighting.js').SceneLighting} lighting The view's lights.
   * @param {AbortSignal} signal Cancels loading when another bundle is chosen.
   * @param {function(number, number): void} onProgress Called with loaded and total request counts.
   * @returns {Promise<LoadedScene>} The shown scene.
   */
  async load(name, view, lighting, signal, onProgress) {
    const description = await this.#api.sceneJson(name, BundleFile.SCENE, signal);
    const fileUrl = (file) => this.#api.sceneFileUrl(name, file);
    const [trajectory, statecharts, stageLights] = await Promise.all([
      this.#optionalJson(name, description[SceneKey.TRAJECTORY], signal),
      this.#optionalJson(name, description[SceneKey.STATECHARTS], signal),
      this.#optionalJson(name, description[SceneKey.RENDERING]?.[RenderingKey.ENVIRONMENT], signal),
    ]);
    const progress = new LoadingProgress(onProgress);
    const [models, objects] = await Promise.all([
      new SceneModels().load(description[SceneKey.MODELS] ?? [], fileUrl, progress.manager),
      new SceneObjects().load(description[SceneKey.OBJECTS] ?? [], fileUrl, progress.manager),
    ]);
    progress.settleIfUnused();
    await progress.idle();
    for (const group of [models.group, objects.group]) {
      group.traverse((child) => {
        if (child.isMesh) child.castShadow = child.receiveShadow = true;
      });
    }
    const frames = new TrajectoryFrames(description, trajectory ?? { [TrajectoryKey.FRAMES]: [] });
    const loaded = new LoadedScene(name, description, frames, models, objects, statecharts, progress.failedUrls());
    if (signal.aborted) {
      loaded.dispose();
      throw signal.reason;
    }
    view.content.clear();
    view.content.add(models.group, objects.group);
    loaded.showFrame(0);
    this.#present(loaded, stageLights, view, lighting);
    return loaded;
  }

  /**
   * @param {string} name The bundle's name.
   * @param {string|undefined|null} file A JSON file of the bundle, or nothing.
   * @param {AbortSignal} signal Cancels the request.
   * @returns {Promise<Object|null>} The file's content, or null when no file is named.
   */
  #optionalJson(name, file, signal) {
    return file ? this.#api.sceneJson(name, file, signal) : Promise.resolve(null);
  }

  /**
   * Set the camera, exposure, ground and lights the scene asks for.
   * @param {LoadedScene} loaded The loaded scene.
   * @param {Object|null} stageLights The stage's `lighting.json`, or null.
   * @param {import('./scene-view.js').SceneView} view The view.
   * @param {import('./scene-lighting.js').SceneLighting} lighting The view's lights.
   */
  #present(loaded, stageLights, view, lighting) {
    const description = loaded.description;
    const rendering = description[SceneKey.RENDERING] ?? {};
    const camera = description[SceneKey.CAMERA];
    view.setExposure(rendering[RenderingKey.EXPOSURE] ?? null);
    view.showGround(rendering[RenderingKey.GROUND_PLANE] ?? true);
    view.setAmbientOcclusion(rendering[RenderingKey.AMBIENT_OCCLUSION] ?? false);
    const background = description[SceneKey.BACKGROUND];
    view.setBackground(background ? this.#api.sceneFileUrl(loaded.name, background) : null);
    view.setLens(camera?.[CameraKey.FIELD_OF_VIEW] ?? null, camera?.[CameraKey.FAR] ?? null);
    const contentBounds = view.contentBounds() ?? EMPTY_SCENE_BOUNDS;
    const focus = this.#focusOf(view, loaded.models, loaded.objects) ?? contentBounds;
    const shadowBounds = rendering[RenderingKey.SHADOW_BOUNDS] ? Bounds.of(rendering[RenderingKey.SHADOW_BOUNDS]) : null;
    const described = stageLights ? LightingDescription.of(stageLights) : null;
    if (described && !described.empty) lighting.showStage(view.renderer, view.scene, new LightingRoom(described, shadowBounds));
    else lighting.showStudio(view.renderer, view.scene, shadowBounds ?? contentBounds);
    if (camera) view.lookFrom(new THREE.Vector3(...camera[CameraKey.POSITION]), new THREE.Vector3(...camera[CameraKey.TARGET]));
    else view.frame(focus);
  }

  /**
   * @param {import('./scene-view.js').SceneView} view The view.
   * @param {SceneModels} models The loaded models.
   * @param {SceneObjects} objects The loaded free objects.
   * @returns {Bounds|null} Where the run happens: the robots and the free objects,
   *   widened to at least `FOCUS_HALF_WIDTH` around their centre; null without robots.
   */
  #focusOf(view, models, objects) {
    const robots = models.robotModels();
    if (robots.length === 0) return null;
    const box = new THREE.Box3();
    for (const part of [...robots, objects.group]) box.expandByObject(part);
    const center = box.getCenter(new THREE.Vector3());
    const half = box.getSize(new THREE.Vector3()).multiplyScalar(0.5);
    const width = Math.max(half.x, half.y, FOCUS_HALF_WIDTH);
    return new Bounds([center.x - width, center.y - width, box.min.z], [center.x + width, center.y + width, box.max.z]);
  }
}
