/**
 * A camera that films a recording like a movie: a slow wide orbit around the robot that
 * eases into a close-up of the object whenever the robot picks one up or lets go of
 * it, slowing the playback down while it is close, and back out again afterwards.
 *
 * The shots are planned from the recording's segments alone, so the plan is known before
 * playback and does not depend on where the person left the camera.
 */

import * as THREE from 'three';

import { SegmentKey } from '../protocol.js';

/**
 * When a close-up happens around the moment it films, in recording seconds for a
 * recording of :data:`REFERENCE_DURATION` or longer; a shorter recording scales them
 * down, so its close-ups stay moments rather than the whole film.
 */
export const ShotTiming = Object.freeze({
  /** How long before the moment the camera starts moving in. */
  LEAD: 1.6,
  /** How long before the moment the camera is fully in. */
  ARRIVE: 0.5,
  /** How long after the moment the camera stays in. */
  HOLD: 1.2,
  /** How long the camera takes to move back out. */
  EASE_OUT: 1.4,
});

/**
 * The length of a recording, in seconds, from which close-ups keep their full timing.
 */
export const REFERENCE_DURATION = 12;

/**
 * The shortest share of the full timing a close-up of a short recording keeps.
 */
export const SHORTEST_TIMING = 0.12;

/**
 * How much the playback slows down while the camera is fully in: the speed is reduced
 * by this share, a slow motion of the moment filmed.
 */
export const SLOW_MOTION = 0.75;

/**
 * How the camera frames the wide shot and the close-up, in metres and radians.
 */
export const Framing = Object.freeze({
  WIDE_DISTANCE: 3.4,
  CLOSE_DISTANCE: 0.9,
  WIDE_ELEVATION: 0.42,
  CLOSE_ELEVATION: 0.28,
  /** How far above the robot's base the wide shot looks, roughly its chest. */
  ROBOT_LOOK_HEIGHT: 0.8,
  /** How fast the wide shot circles the robot. */
  ORBIT_SPEED: 0.1,
  /**
   * How far the close-up turns away from the line from the robot to the object, so it
   * looks at the object and the gripper from beside them, never from inside the robot.
   */
  CLOSE_SIDE: 0.7,
  /** How much of the way to the planned pose the camera moves per shown frame. */
  SMOOTHING: 0.18,
});

/**
 * @param {number} edge0 Where the ramp starts.
 * @param {number} edge1 Where it ends.
 * @param {number} value Where on it the value lies.
 * @returns {number} 0 before the ramp, 1 after it, and an eased value between.
 */
export function smoothstep(edge0, edge1, value) {
  if (edge1 <= edge0) return value < edge0 ? 0 : 1;
  const t = Math.min(Math.max((value - edge0) / (edge1 - edge0), 0), 1);
  return t * t * (3 - 2 * t);
}

// %% plan

/**
 * One close-up: the moment it films and the object it looks at.
 */
export class CloseUp {
  /**
   * @param {number} time The moment filmed, in recording seconds.
   * @param {string} object The key of the object the camera looks at.
   * @param {number=} scale The share of the full timing the close-up keeps.
   */
  constructor(time, object, scale = 1) {
    /**
     * The moment filmed, in recording seconds.
     * @type {number}
     */
    this.time = time;
    /**
     * The key of the object the camera looks at.
     * @type {string}
     */
    this.object = object;
    /**
     * The share of the full timing the close-up keeps.
     * @type {number}
     */
    this.scale = scale;
  }

  /**
   * @param {number} time A recording time in seconds.
   * @returns {number} How far the camera is in at that time, from 0 to 1.
   */
  closeness(time) {
    const scale = this.scale;
    const rising = smoothstep(this.time - scale * ShotTiming.LEAD, this.time - scale * ShotTiming.ARRIVE, time);
    const falling = 1 - smoothstep(this.time + scale * ShotTiming.HOLD, this.time + scale * (ShotTiming.HOLD + ShotTiming.EASE_OUT), time);
    return Math.min(rising, falling);
  }
}

/**
 * The close-ups of one recording.
 */
export class ShotPlan {
  /**
   * @param {Array<CloseUp>} closeUps The close-ups, in any order.
   */
  constructor(closeUps = []) {
    /**
     * The close-ups.
     * @type {Array<CloseUp>}
     */
    this.closeUps = closeUps;
  }

  /**
   * @param {Array<Object>} segments The recording's segments.
   * @param {number} framesPerSecond The recording's frame rate.
   * @param {number=} duration The recording's length in seconds.
   * @returns {ShotPlan} A close-up for every pick-up and every letting go a segment
   *   names together with its object, timed for the recording's length.
   */
  static of(segments, framesPerSecond, duration = REFERENCE_DURATION) {
    const scale = Math.min(Math.max(duration / REFERENCE_DURATION, SHORTEST_TIMING), 1);
    const closeUps = [];
    for (const segment of segments) {
      const object = segment[SegmentKey.PICKS];
      if (!object || !(framesPerSecond > 0)) continue;
      for (const frame of [segment[SegmentKey.ATTACH], segment[SegmentKey.DETACH]]) {
        if (frame !== undefined && frame !== null) closeUps.push(new CloseUp(frame / framesPerSecond, object, scale));
      }
    }
    return new ShotPlan(closeUps);
  }

  /**
   * @param {number} time A recording time in seconds.
   * @returns {{closeness: number, object: string|null}} How far the camera is in, and
   *   the object it looks at while it is in at all.
   */
  shotAt(time) {
    let best = { closeness: 0, object: null };
    for (const closeUp of this.closeUps) {
      const closeness = closeUp.closeness(time);
      if (closeness > best.closeness) best = { closeness, object: closeUp.object };
    }
    return best;
  }

  /**
   * @param {number} time A recording time in seconds.
   * @returns {number} The share of the chosen speed the playback runs at then: slower
   *   the closer the camera is.
   */
  pace(time) {
    return 1 - SLOW_MOTION * this.shotAt(time).closeness;
  }
}

// %% camera

export class CinematicCamera {
  /**
   * The 3D view whose camera is driven.
   * @type {import('./scene-view.js').SceneView}
   */
  #view;

  /**
   * The recording's close-ups.
   * @type {ShotPlan}
   */
  #plan = new ShotPlan();

  /**
   * The direction the wide shot starts from, around the robot, in radians.
   * @type {number|null}
   */
  #startAzimuth = null;

  /**
   * Whether the camera was posed before, so the next pose eases from it.
   * @type {boolean}
   */
  #posed = false;

  /**
   * Whether the camera is driven.
   * @type {boolean}
   */
  enabled = false;

  /**
   * @param {import('./scene-view.js').SceneView} view The 3D view whose camera is driven.
   */
  constructor(view) {
    this.#view = view;
  }

  /**
   * @param {ShotPlan} plan The close-ups of the recording shown now.
   */
  plan(plan) {
    this.#plan = plan;
    this.cut();
  }

  /**
   * @param {number} time A recording time in seconds.
   * @returns {number} The share of the chosen speed the playback runs at then, 1 while
   *   the camera is off.
   */
  pace(time) {
    return this.enabled ? this.#plan.pace(time) : 1;
  }

  /**
   * Let the next pose jump to its shot instead of easing into it, as after a seek, and
   * start the wide shot from where the camera looks from now.
   */
  cut() {
    this.#posed = false;
    this.#startAzimuth = null;
  }

  /**
   * Pose the camera for a moment of the recording.
   * @param {number} time The recording time shown, in seconds.
   * @param {THREE.Vector3|null} robot Where the robot's base stands.
   * @param {function(string): (THREE.Vector3|null)} objectAt Where an object is now.
   * @returns {boolean} Whether the camera was posed.
   */
  update(time, robot, objectAt) {
    if (!this.enabled || !robot) return false;
    const camera = this.#view.camera;
    const target = this.#view.controls.target;
    if (this.#startAzimuth === null) this.#startAzimuth = Math.atan2(camera.position.y - robot.y, camera.position.x - robot.x);
    const shot = this.#plan.shotAt(time);
    const object = shot.object ? objectAt(shot.object) : null;
    const closeness = object ? shot.closeness : 0;
    const wide = robot.clone().add(new THREE.Vector3(0, 0, Framing.ROBOT_LOOK_HEIGHT));
    const look = object ? wide.clone().lerp(object, closeness) : wide;
    const distance = THREE.MathUtils.lerp(Framing.WIDE_DISTANCE, Framing.CLOSE_DISTANCE, closeness);
    const elevation = THREE.MathUtils.lerp(Framing.WIDE_ELEVATION, Framing.CLOSE_ELEVATION, closeness);
    const orbit = this.#startAzimuth + Framing.ORBIT_SPEED * time;
    const beside = object ? Math.atan2(object.y - robot.y, object.x - robot.x) + Framing.CLOSE_SIDE : orbit;
    const turn = Math.atan2(Math.sin(beside - orbit), Math.cos(beside - orbit));
    const azimuth = orbit + turn * closeness;
    const position = new THREE.Vector3(
      Math.cos(elevation) * Math.cos(azimuth),
      Math.cos(elevation) * Math.sin(azimuth),
      Math.sin(elevation),
    )
      .multiplyScalar(distance)
      .add(look);
    if (this.#posed) {
      position.lerpVectors(camera.position, position, Framing.SMOOTHING);
      look.lerpVectors(target, look, Framing.SMOOTHING);
    }
    camera.position.copy(position);
    target.copy(look);
    camera.lookAt(look);
    this.#posed = true;
    this.#view.requestRender();
    return true;
  }
}
