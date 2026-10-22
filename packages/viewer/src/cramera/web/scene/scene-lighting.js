/**
 * The lights of the 3D view: a converted stage's own lights when its bundle describes
 * them, else a neutral studio.
 */

import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

import { LightingRoom } from './stage-lighting.js';
import { ShadowFit } from './shadow-fit.js';

/**
 * Converts the description's intensities, where a key of 1 lights white as a luminance
 * of 1, into three's physical light units, where white reflects 1/π of its irradiance.
 */
export const PHYSICAL_INTENSITY_SCALE = Math.PI;

/**
 * The studio's settings: environment strength, the key light's way and strength, and
 * the size of the shadow map.
 */
export const Studio = Object.freeze({
  ENVIRONMENT_INTENSITY: 0.55,
  KEY_DIRECTION: Object.freeze([-0.45, -0.35, -1]),
  KEY_INTENSITY: 1.6,
  SHADOW_MAP_SIZE: 2048,
});

/**
 * How finely the environment maps are prefiltered.
 */
const ENVIRONMENT_BLUR = 0.04;

/**
 * The nearest and farthest distance the converted stage's environment is rendered at,
 * in metres.
 */
const ENVIRONMENT_RANGE = Object.freeze({ NEAR: 0.1, FAR: 1000 });

/**
 * How far shadows are pushed off surfaces, against shadow acne: along the light, in
 * depth units, and along the surface normal, in metres.
 */
const SHADOW_OFFSET = Object.freeze({ BIAS: -0.0002, NORMAL: 0.01 });

// %% lighting

export class SceneLighting {
  /**
   * The group holding the lights.
   * @type {THREE.Group}
   */
  group = new THREE.Group();

  /**
   * The renderer's environment map while shown.
   * @type {THREE.WebGLRenderTarget|null}
   */
  #environment = null;

  /**
   * Show a converted stage's lights.
   * @param {THREE.WebGLRenderer} renderer The view's renderer.
   * @param {THREE.Scene} scene The view's scene.
   * @param {LightingRoom} room The stage's lights and room.
   */
  showStage(renderer, scene, room) {
    this.#clear(scene);
    this.#environment = new THREE.PMREMGenerator(renderer).fromScene(this.#roomScene(room), ENVIRONMENT_BLUR, ENVIRONMENT_RANGE.NEAR, ENVIRONMENT_RANGE.FAR, {
      position: new THREE.Vector3(...room.probe()),
    });
    scene.environment = this.#environment.texture;
    const key = room.keyLight();
    if (key && key.shadowBounds) {
      const light = this.#keyLight(new THREE.Color(...key.color), key.intensity * PHYSICAL_INTENSITY_SCALE);
      new ShadowFit(key.shadowBounds, key.direction).applyTo(light);
      this.group.add(light, light.target);
    }
  }

  /**
   * Show the studio lights, with shadows over the given region.
   * @param {THREE.WebGLRenderer} renderer The view's renderer.
   * @param {THREE.Scene} scene The view's scene.
   * @param {import('./bounds.js').Bounds} region The region that receives shadows.
   */
  showStudio(renderer, scene, region) {
    this.#clear(scene);
    const room = new RoomEnvironment();
    room.rotation.x = Math.PI / 2;
    this.#environment = new THREE.PMREMGenerator(renderer).fromScene(room, ENVIRONMENT_BLUR);
    scene.environment = this.#environment.texture;
    scene.environmentIntensity = Studio.ENVIRONMENT_INTENSITY;
    const light = this.#keyLight(new THREE.Color(0xffffff), Studio.KEY_INTENSITY);
    new ShadowFit(region, Studio.KEY_DIRECTION).applyTo(light);
    this.group.add(light, light.target);
  }

  /**
   * @param {THREE.Color} color The light's colour.
   * @param {number} intensity The light's intensity in three's units.
   * @returns {THREE.DirectionalLight} A shadow-casting directional light.
   */
  #keyLight(color, intensity) {
    const light = new THREE.DirectionalLight(color, intensity);
    light.castShadow = true;
    light.shadow.mapSize.set(Studio.SHADOW_MAP_SIZE, Studio.SHADOW_MAP_SIZE);
    light.shadow.bias = SHADOW_OFFSET.BIAS;
    light.shadow.normalBias = SHADOW_OFFSET.NORMAL;
    return light;
  }

  /**
   * @param {LightingRoom} room The stage's lights and room.
   * @returns {THREE.Scene} The room with its glowing panels, for the environment map.
   */
  #roomScene(room) {
    const environment = new THREE.Scene();
    const size = room.room.size();
    const faces = room.faceColors();
    const material = (color) => new THREE.MeshBasicMaterial({ color: new THREE.Color(...color), side: THREE.BackSide });
    const box = new THREE.Mesh(new THREE.BoxGeometry(...size), [
      material(faces.wall),
      material(faces.wall),
      material(faces.wall),
      material(faces.wall),
      material(faces.ceiling),
      material(faces.floor),
    ]);
    box.position.set(...room.room.center());
    environment.add(box);
    const facing = new THREE.Vector3(0, 0, 1);
    for (const panel of room.lighting.panels) {
      const quad = new THREE.Mesh(
        new THREE.PlaneGeometry(panel.width, panel.height),
        new THREE.MeshBasicMaterial({ color: new THREE.Color(...room.panelRadiance(panel)), side: THREE.DoubleSide }),
      );
      quad.position.set(...panel.center);
      quad.quaternion.setFromUnitVectors(facing, new THREE.Vector3(...panel.normal).normalize());
      environment.add(quad);
    }
    return environment;
  }

  /**
   * @param {THREE.Scene} scene The view's scene.
   */
  #clear(scene) {
    this.group.clear();
    this.#environment?.dispose();
    this.#environment = null;
    scene.environment = null;
    scene.environmentIntensity = 1;
  }

  /**
   * Remove the lights and free the environment map.
   * @param {THREE.Scene} scene The view's scene.
   */
  dispose(scene) {
    this.#clear(scene);
    this.group.removeFromParent();
  }
}
