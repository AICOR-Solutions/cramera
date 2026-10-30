/**
 * A camera that films a recording like a movie: a slow wide orbit around the robot that
 * eases into a close-up of the object whenever the robot picks one up or lets go of
 * it, slowing the playback down while it is close, and back out again afterwards.
 *
 * The shots are planned from the recording's segments alone, so the plan is known before
 * playback and does not depend on where the person left the camera.
 *
 * Nothing of the scene, such as a wall, a cabinet or a door, ever stands between the
 * camera and what it films: a shot whose angle is blocked films from another one, the
 * wide orbit turns back where a wall would come between, and a camera that has nowhere
 * clear to go moves in front of what stands in its way.
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
 * How the camera keeps what it films in sight.
 */
export const Sight = Object.freeze({
  /**
   * How far in front of a surface that would stand between it and what it films the
   * camera stays, in metres.
   */
  MARGIN: 0.2,
  /**
   * The share of its planned distance an angle must leave the camera, once it stands in
   * front of what is in the way, to be filmed from; a shot that would have to come
   * closer looks for another angle.
   */
  COMFORT: 0.7,
  /**
   * How far toward the corners of the picture the rays that look for a crowded picture
   * point, as a share of the half field of view.
   */
  CORNER: 0.5,
  /**
   * How far toward what is filmed something must stand to crowd the picture, as a share
   * of the way; what stands beyond, such as the floor around the robot, is scenery.
   */
  NEAR: 0.75,
  /** The most of the picture's four corners something near may hide in a clear picture. */
  HIDDEN_CORNERS: 2,
  /** The opacity below which a surface is glass the camera films through. */
  SEE_THROUGH: 0.5,
  /**
   * The most triangles a mesh may have for a ray to test them; a mesh of more, such as
   * an oven or a wardrobe, stands in the way as its box, which keeps a ray cheap.
   */
  SOLID_TRIANGLES: 2000,
});

/**
 * How much farther round a blocked wide shot turns, either way, and how much higher it
 * looks from, in radians.
 */
const WIDE_DETOUR = Object.freeze({
  TURNS: [0, 0.4, 0.8, 1.2, 1.6, 2.0, 2.4, 2.8, Math.PI],
  RAISES: [0, 0.35, 0.7],
});

/**
 * The sides a close-up tries to film its object from, in the order tried, as turns from
 * the line from the robot to the object, in radians: never from the robot's side of it.
 */
const CLOSE_SIDES = Object.freeze([Framing.CLOSE_SIDE, -Framing.CLOSE_SIDE, 0.25, -0.25, 1.2, -1.2, 1.5, -1.5]);

/**
 * How much higher than its own elevation a close-up looks from when no side is clear,
 * in the order tried, in radians.
 */
const CLOSE_RAISES = Object.freeze([0, 0.4, 0.8]);

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

// %% sight

/**
 * @param {number} from A direction in radians.
 * @param {number} to Another direction in radians.
 * @returns {number} The shorter turn from the one to the other, in radians.
 */
function turnBetween(from, to) {
  return Math.atan2(Math.sin(to - from), Math.cos(to - from));
}

/**
 * @param {Array<number>} turns The sizes of the turns, in radians.
 * @param {Array<number>} raises The raises of the elevation, in radians.
 * @returns {Array<{turn: number, raise: number}>} Every turn with every raise but the
 *   plan itself, cheapest first, where a raise costs as much as a turn twice its size;
 *   a positive turn goes back against the orbit, and is tried before going on.
 */
function detoursOf(turns, raises) {
  const detours = [];
  for (const raise of raises) {
    for (const size of turns) {
      for (const turn of size === 0 || size === Math.PI ? [size] : [size, -size]) {
        if (turn !== 0 || raise !== 0) detours.push({ turn, raise });
      }
    }
  }
  const cost = (detour) => Math.abs(detour.turn) + 2 * detour.raise;
  return detours.sort((first, second) => cost(first) - cost(second));
}

/**
 * The other angles a blocked wide shot tries, cheapest first.
 */
const WIDE_DETOURS = Object.freeze(detoursOf(WIDE_DETOUR.TURNS, WIDE_DETOUR.RAISES));

/**
 * Where the camera stands around what it films.
 */
export class ShotAngle {
  /**
   * @param {number} azimuth The direction it looks from around what it films, in radians.
   * @param {number} elevation How far above it it looks from, in radians.
   * @param {number} distance How far from it it stands, in metres.
   */
  constructor(azimuth, elevation, distance) {
    /**
     * The direction the camera looks from around what it films, in radians.
     * @type {number}
     */
    this.azimuth = azimuth;
    /**
     * How far above what it films the camera looks from, in radians.
     * @type {number}
     */
    this.elevation = elevation;
    /**
     * How far from what it films the camera stands, in metres.
     * @type {number}
     */
    this.distance = distance;
  }

  /**
   * @param {THREE.Vector3} position Where a camera stands.
   * @param {THREE.Vector3} look What it looks at, somewhere else.
   * @returns {ShotAngle} The angle it looks from.
   */
  static of(position, look) {
    const offset = new THREE.Vector3().subVectors(position, look);
    const distance = offset.length();
    return new ShotAngle(Math.atan2(offset.y, offset.x), Math.asin(THREE.MathUtils.clamp(offset.z / distance, -1, 1)), distance);
  }

  /**
   * @returns {THREE.Vector3} The unit direction from what is filmed toward the camera.
   */
  direction() {
    return new THREE.Vector3(
      Math.cos(this.elevation) * Math.cos(this.azimuth),
      Math.cos(this.elevation) * Math.sin(this.azimuth),
      Math.sin(this.elevation),
    );
  }

  /**
   * @param {number} distance Another distance.
   * @returns {ShotAngle} This angle from that distance.
   */
  at(distance) {
    return new ShotAngle(this.azimuth, this.elevation, distance);
  }

  /**
   * @param {ShotAngle} other Another angle.
   * @param {number} share How far toward it, from 0 to 1.
   * @returns {ShotAngle} The angle that share of the way to the other one, turning the
   *   shorter way round what is filmed, so the camera never passes through it.
   */
  toward(other, share) {
    return new ShotAngle(
      this.azimuth + turnBetween(this.azimuth, other.azimuth) * share,
      THREE.MathUtils.lerp(this.elevation, other.elevation, share),
      THREE.MathUtils.lerp(this.distance, other.distance, share),
    );
  }
}

/**
 * The most triangles a box of a `TriangleTree` holds without being split further.
 */
const LEAF_TRIANGLES = 8;

/**
 * The triangles of a geometry sorted into nested boxes in the geometry's own frame, so a
 * ray tests only the triangles near it.
 */
class TriangleTree {
  /**
   * The corners of every triangle, nine numbers each.
   * @type {Float32Array}
   */
  #corners;

  /**
   * The triangles in the order the boxes hold them.
   * @type {Uint32Array}
   */
  #order;

  /**
   * The outermost box: each box holds its children, or the triangles from `first` on.
   * @type {{box: THREE.Box3, first: number, count: number, children: Array<Object>|null}}
   */
  #root;

  /**
   * @param {THREE.BufferGeometry} geometry A geometry of triangles.
   */
  constructor(geometry) {
    const position = geometry.attributes.position;
    const index = geometry.index;
    const count = Math.floor((index ? index.count : position.count) / 3);
    this.#corners = new Float32Array(count * 9);
    const centres = new Float32Array(count * 3);
    for (let triangle = 0; triangle < count; triangle += 1) {
      for (let corner = 0; corner < 3; corner += 1) {
        const vertex = index ? index.getX(triangle * 3 + corner) : triangle * 3 + corner;
        const offset = triangle * 9 + corner * 3;
        this.#corners[offset] = position.getX(vertex);
        this.#corners[offset + 1] = position.getY(vertex);
        this.#corners[offset + 2] = position.getZ(vertex);
        for (let axis = 0; axis < 3; axis += 1) centres[triangle * 3 + axis] += this.#corners[offset + axis] / 3;
      }
    }
    this.#order = new Uint32Array(count);
    for (let triangle = 0; triangle < count; triangle += 1) this.#order[triangle] = triangle;
    this.#root = this.#box(0, count);
    const unsplit = [this.#root];
    while (unsplit.length > 0) {
      const node = unsplit.pop();
      const halves = this.#split(node, centres);
      if (halves === null) continue;
      node.children = halves.map(([first, size]) => this.#box(first, size));
      unsplit.push(...node.children);
    }
  }

  /**
   * @param {number} first The first triangle of the box, in the tree's order.
   * @param {number} count How many triangles it holds.
   * @returns {{box: THREE.Box3, first: number, count: number, children: null}} A box
   *   around those triangles, not split yet.
   */
  #box(first, count) {
    const box = new THREE.Box3();
    const corner = new THREE.Vector3();
    for (let place = first; place < first + count; place += 1) {
      for (let offset = 0; offset < 9; offset += 3) box.expandByPoint(corner.fromArray(this.#corners, this.#order[place] * 9 + offset));
    }
    return { box, first, count, children: null };
  }

  /**
   * Sort a box's triangles into the halves of its longest side, by their centres.
   * @param {{first: number, count: number}} node A box of the tree.
   * @param {Float32Array} centres The centre of every triangle.
   * @returns {Array<Array<number>>|null} The first triangle and the count of each half,
   *   or null for a box small enough to keep its triangles.
   */
  #split(node, centres) {
    if (node.count <= LEAF_TRIANGLES) return null;
    const low = [Infinity, Infinity, Infinity];
    const high = [-Infinity, -Infinity, -Infinity];
    for (let place = node.first; place < node.first + node.count; place += 1) {
      for (let axis = 0; axis < 3; axis += 1) {
        const centre = centres[this.#order[place] * 3 + axis];
        low[axis] = Math.min(low[axis], centre);
        high[axis] = Math.max(high[axis], centre);
      }
    }
    const axis = [0, 1, 2].reduce((longest, candidate) => (high[candidate] - low[candidate] > high[longest] - low[longest] ? candidate : longest));
    const middle = (low[axis] + high[axis]) / 2;
    let left = node.first;
    let right = node.first + node.count - 1;
    while (left <= right) {
      if (centres[this.#order[left] * 3 + axis] < middle) left += 1;
      else {
        [this.#order[left], this.#order[right]] = [this.#order[right], this.#order[left]];
        right -= 1;
      }
    }
    let size = left - node.first;
    if (size === 0 || size === node.count) size = Math.floor(node.count / 2);
    return [[node.first, size], [node.first + size, node.count - size]];
  }

  /**
   * @param {THREE.Ray} ray A ray in the geometry's own frame.
   * @param {THREE.Vector3} point Receives where the ray meets the nearest triangle.
   * @returns {boolean} Whether the ray meets a triangle, from either side.
   */
  nearest(ray, point) {
    let best = Infinity;
    const [first, second, third, hit, entry] = [0, 1, 2, 3, 4].map(() => new THREE.Vector3());
    const open = [this.#root];
    while (open.length > 0) {
      const node = open.pop();
      if (!node.box.containsPoint(ray.origin) && !(ray.intersectBox(node.box, entry) && entry.distanceTo(ray.origin) < best)) continue;
      if (node.children) {
        open.push(...node.children);
        continue;
      }
      for (let place = node.first; place < node.first + node.count; place += 1) {
        const offset = this.#order[place] * 9;
        first.fromArray(this.#corners, offset);
        second.fromArray(this.#corners, offset + 3);
        third.fromArray(this.#corners, offset + 6);
        if (ray.intersectTriangle(first, second, third, false, hit) === null) continue;
        const distance = hit.distanceTo(ray.origin);
        if (distance < best) {
          best = distance;
          point.copy(hit);
        }
      }
    }
    return best < Infinity;
  }
}

/**
 * Whether the scene's geometry stands between the camera and what it films. A surface
 * counts from either side, so the camera never stands inside a box either; hidden
 * surfaces and glass do not count.
 */
export class LineOfSight {
  /**
   * The geometry that may stand in the way, as given.
   * @type {Array<THREE.Object3D>}
   */
  #obstacles;

  /**
   * A two-sided stand-in for every mesh of the obstacles, sharing its geometry and its
   * world matrix, with the mesh it stands in for.
   * @type {Map<THREE.Mesh, THREE.Mesh>}
   */
  #standIns = new Map();

  /**
   * The box around every stand-in in the world, as of the last refresh, so a ray only
   * looks at the meshes it passes through.
   * @type {Map<THREE.Mesh, THREE.Box3>}
   */
  #bounds = new Map();

  /**
   * The stand-ins of more than `Sight.SOLID_TRIANGLES` triangles, which stand in the way
   * as their own box.
   * @type {Set<THREE.Mesh>}
   */
  #solids = new Set();

  /**
   * The triangle tree of every solid's geometry a ray started inside the box of.
   * @type {WeakMap<THREE.BufferGeometry, TriangleTree>}
   */
  #trees = new WeakMap();

  /**
   * Casts the rays.
   * @type {THREE.Raycaster}
   */
  #raycaster = new THREE.Raycaster();

  /**
   * @param {Array<THREE.Object3D>} obstacles The geometry that may stand in the way,
   *   such as the environment's models; everything below them counts.
   */
  constructor(obstacles = []) {
    this.#obstacles = obstacles;
    const twoSided = new THREE.MeshBasicMaterial({ side: THREE.DoubleSide });
    for (const obstacle of obstacles) {
      obstacle.traverse((child) => {
        if (!child.isMesh) return;
        if (child.geometry.boundingBox === null) child.geometry.computeBoundingBox();
        const standIn = new THREE.Mesh(child.geometry, twoSided);
        standIn.matrixWorld = child.matrixWorld;
        this.#standIns.set(standIn, child);
        this.#bounds.set(standIn, new THREE.Box3());
        const corners = child.geometry.index?.count ?? child.geometry.attributes.position?.count ?? 0;
        if (corners / 3 > Sight.SOLID_TRIANGLES) this.#solids.add(standIn);
        else if (child.geometry.boundingSphere === null) child.geometry.computeBoundingSphere();
      });
    }
    this.refresh();
  }

  /**
   * Bring the obstacles' world matrices and boxes up to their parts' current poses, such
   * as a door opened since the last frame was drawn.
   */
  refresh() {
    for (const obstacle of this.#obstacles) obstacle.updateWorldMatrix(true, true);
    for (const [standIn, box] of this.#bounds) box.copy(standIn.geometry.boundingBox).applyMatrix4(standIn.matrixWorld);
  }

  /**
   * @param {THREE.Vector3} subject What the camera films.
   * @param {THREE.Vector3} direction The unit direction from it toward the camera.
   * @param {number} distance How far from it the camera would stand.
   * @returns {number} How far from the subject, up to that distance, the camera can
   *   stand with nothing between them: `Sight.MARGIN` in front of the nearest surface
   *   in the way, or halfway to a surface closer than twice that.
   */
  reach(subject, direction, distance) {
    const surface = this.#nearest(subject, direction, distance);
    if (surface === null) return distance;
    return surface > 2 * Sight.MARGIN ? surface - Sight.MARGIN : surface / 2;
  }

  /**
   * @param {THREE.Vector3} position Where the camera stands.
   * @param {THREE.Vector3} subject What it looks at.
   * @param {THREE.PerspectiveCamera} lens The camera, for its field of view and up.
   * @returns {number} How many of the picture's four corners, `Sight.CORNER` of the way
   *   out from its middle, something hides in the near part of the way to the subject.
   */
  hiddenCorners(position, subject, lens) {
    const forward = new THREE.Vector3().subVectors(subject, position);
    const depth = forward.length();
    forward.divideScalar(depth);
    const right = new THREE.Vector3().crossVectors(forward, lens.up);
    if (right.lengthSq() < 1e-12) right.set(1, 0, 0);
    else right.normalize();
    const up = new THREE.Vector3().crossVectors(right, forward);
    const height = Sight.CORNER * Math.tan(THREE.MathUtils.degToRad(lens.fov) / 2);
    const width = height * lens.aspect;
    let hidden = 0;
    for (const [across, along] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
      const ray = forward.clone().addScaledVector(right, across * width).addScaledVector(up, along * height);
      const length = Sight.NEAR * depth * ray.length();
      if (this.#nearest(position, ray.normalize(), length) !== null) hidden += 1;
    }
    return hidden;
  }

  /**
   * @param {THREE.Vector3} subject What the camera films.
   * @param {ShotAngle} angle Where the camera would stand around it.
   * @param {THREE.PerspectiveCamera} lens The camera.
   * @returns {{angle: ShotAngle, clear: boolean}} The angle in front of what stands in
   *   its way, and whether it films the subject well: from at least `Sight.COMFORT` of
   *   its distance, with at most `Sight.HIDDEN_CORNERS` of the picture hidden.
   */
  view(subject, angle, lens) {
    const direction = angle.direction();
    const reached = angle.at(this.reach(subject, direction, angle.distance));
    if (reached.distance < Sight.COMFORT * angle.distance) return { angle: reached, clear: false };
    const position = subject.clone().addScaledVector(direction, reached.distance);
    return { angle: reached, clear: this.hiddenCorners(position, subject, lens) <= Sight.HIDDEN_CORNERS };
  }

  /**
   * @param {THREE.Vector3} origin Where the ray starts.
   * @param {THREE.Vector3} direction Its unit direction.
   * @param {number} length How far it reaches.
   * @returns {number|null} How far along it the nearest drawn, opaque surface lies, or
   *   null when none lies within its length; a mesh of many triangles counts as its
   *   box, unless the ray starts inside that box, when its triangle tree tells.
   */
  #nearest(origin, direction, length) {
    if (!(length > 0)) return null;
    const ray = new THREE.Ray(origin, direction);
    const entry = new THREE.Vector3();
    const inverse = new THREE.Matrix4();
    const local = new THREE.Ray();
    let nearest = null;
    const consider = (point, standIn) => {
      const distance = point.applyMatrix4(standIn.matrixWorld).distanceTo(origin);
      if (distance <= length && (nearest === null || distance < nearest)) nearest = distance;
    };
    const exact = [];
    for (const [standIn, box] of this.#bounds) {
      if (!box.containsPoint(origin) && !(ray.intersectBox(box, entry) && entry.distanceTo(origin) <= length)) continue;
      if (!drawn(this.#standIns.get(standIn))) continue;
      if (!this.#solids.has(standIn)) {
        exact.push(standIn);
        continue;
      }
      local.copy(ray).applyMatrix4(inverse.copy(standIn.matrixWorld).invert());
      const geometry = standIn.geometry;
      if (!geometry.boundingBox.containsPoint(local.origin)) {
        if (local.intersectBox(geometry.boundingBox, entry)) consider(entry, standIn);
        continue;
      }
      if (!this.#trees.has(geometry)) this.#trees.set(geometry, new TriangleTree(geometry));
      if (this.#trees.get(geometry).nearest(local, entry)) consider(entry, standIn);
    }
    this.#raycaster.set(origin, direction);
    this.#raycaster.far = nearest ?? length;
    const [hit] = this.#raycaster.intersectObjects(exact, false);
    return hit ? hit.distance : nearest;
  }
}

/**
 * @param {THREE.Mesh} mesh A mesh of the scene.
 * @returns {boolean} Whether it is drawn, and drawn opaque enough to hide what is behind.
 */
function drawn(mesh) {
  for (let node = mesh; node; node = node.parent) if (!node.visible) return false;
  return [mesh.material].flat().some((material) => material?.visible && !(material.transparent && material.opacity < Sight.SEE_THROUGH));
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
   * Whether the scene's geometry stands between the camera and what it films.
   * @type {LineOfSight}
   */
  #sight = new LineOfSight();

  /**
   * The direction the wide shot looks from, around the robot, in radians, or null until
   * the next pose starts it from where the camera looks from then.
   * @type {number|null}
   */
  #orbit = null;

  /**
   * Which way the wide shot circles the robot: 1 anticlockwise seen from above, -1
   * clockwise.
   * @type {number}
   */
  #heading = 1;

  /**
   * How much higher than its own elevation the wide shot looks from, to see over what
   * stands in its way, in radians.
   * @type {number}
   */
  #raise = 0;

  /**
   * The recording time of the last pose, in seconds.
   * @type {number}
   */
  #time = 0;

  /**
   * The object the close-up shown films and the side and raise it films it from, or
   * null between close-ups.
   * @type {{object: string, side: number, raise: number}|null}
   */
  #closeUp = null;

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
   * @param {Array<THREE.Object3D>} obstacles The scene's geometry that must never stand
   *   between the camera and what it films, such as the environment's walls, cabinets
   *   and doors; the robots and the objects they handle are what is filmed.
   */
  setObstacles(obstacles) {
    this.#sight = new LineOfSight(obstacles);
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
    this.#orbit = null;
    this.#closeUp = null;
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
    this.#sight.refresh();
    const shot = this.#plan.shotAt(time);
    const object = shot.object ? objectAt(shot.object) : null;
    const wide = robot.clone().add(new THREE.Vector3(0, 0, Framing.ROBOT_LOOK_HEIGHT));
    const orbit = this.#wideAngle(time, robot, wide);
    if (object) {
      const close = this.#closeAngle(shot.object, robot, object);
      this.#pose(wide.clone().lerp(object, shot.closeness), orbit.toward(close, shot.closeness));
    } else {
      this.#closeUp = null;
      this.#pose(wide, orbit);
    }
    return true;
  }

  /**
   * Circle the robot, turning back where a wall would come between the camera and the
   * robot, and look from higher up or from elsewhere when the way ahead is blocked too.
   * @param {number} time The recording time shown, in seconds.
   * @param {THREE.Vector3} robot Where the robot's base stands.
   * @param {THREE.Vector3} look What the wide shot looks at.
   * @returns {ShotAngle} The angle of the wide shot now.
   */
  #wideAngle(time, robot, look) {
    if (this.#orbit === null) {
      const camera = this.#view.camera.position;
      this.#orbit = Math.atan2(camera.y - robot.y, camera.x - robot.x);
      this.#heading = 1;
      this.#raise = 0;
      this.#time = time;
    }
    const heading = this.#heading;
    const ahead = this.#orbit + heading * Framing.ORBIT_SPEED * Math.max(time - this.#time, 0);
    this.#time = time;
    const attempt = (azimuth, raise, turnedTo, open = false) => ({
      angle: new ShotAngle(azimuth, Framing.WIDE_ELEVATION + raise, Framing.WIDE_DISTANCE),
      raise,
      heading: turnedTo,
      open,
    });
    const attempts = [];
    if (this.#raise > 0) attempts.push(attempt(ahead, 0, heading, true));
    attempts.push(attempt(ahead, this.#raise, heading));
    if (ahead !== this.#orbit) attempts.push(attempt(this.#orbit, this.#raise, -heading));
    for (const { turn, raise } of WIDE_DETOURS) {
      attempts.push(attempt(ahead - heading * turn, raise, turn === 0 ? heading : -heading * Math.sign(turn)));
    }
    const { attempt: chosen, angle } = this.#clearest(look, attempts);
    this.#orbit = chosen.angle.azimuth;
    this.#raise = chosen.raise;
    this.#heading = chosen.heading;
    return angle;
  }

  /**
   * Film an object from beside it, from its other side or from above when something
   * stands in the way, keeping the side found while it stays clear.
   * @param {string} key The object's key.
   * @param {THREE.Vector3} robot Where the robot's base stands.
   * @param {THREE.Vector3} object Where the object is.
   * @returns {ShotAngle} The angle of the close-up now.
   */
  #closeAngle(key, robot, object) {
    const toward = Math.atan2(object.y - robot.y, object.x - robot.x);
    const attempt = (side, raise) => ({
      angle: new ShotAngle(toward + side, Framing.CLOSE_ELEVATION + raise, Framing.CLOSE_DISTANCE),
      side,
      raise,
    });
    const attempts = [];
    if (this.#closeUp?.object === key) attempts.push(attempt(this.#closeUp.side, this.#closeUp.raise));
    for (const raise of CLOSE_RAISES) for (const side of CLOSE_SIDES) attempts.push(attempt(side, raise));
    const { attempt: chosen, angle } = this.#clearest(object, attempts);
    this.#closeUp = { object: key, side: chosen.side, raise: chosen.raise };
    return angle;
  }

  /**
   * @param {THREE.Vector3} look What the shot films.
   * @param {Array<{angle: ShotAngle, open: boolean=}>} attempts The angles to try, in
   *   order; an open one counts only when nothing at all stands in its way.
   * @returns {{attempt: Object, angle: ShotAngle}} The first attempt that films the
   *   subject well, or the one that leaves the camera farthest from it when none does,
   *   with its angle in front of what stands in its way.
   */
  #clearest(look, attempts) {
    let best = null;
    for (const attempt of attempts) {
      const view = this.#sight.view(look, attempt.angle, this.#view.camera);
      const found = { attempt, angle: view.angle };
      if (view.clear && (!attempt.open || view.angle.distance === attempt.angle.distance)) return found;
      if (!best || view.angle.distance > best.angle.distance) best = found;
    }
    return best;
  }

  /**
   * Move the camera toward a shot, easing from its last pose round what it films, and
   * never behind anything that stands in the way; when easing would hide what the shot
   * films, as when the robot moves faster than the camera follows, cut to the shot.
   * @param {THREE.Vector3} look What the shot looks at.
   * @param {ShotAngle} angle Where the camera stands around it.
   */
  #pose(look, angle) {
    const camera = this.#view.camera;
    const target = this.#view.controls.target;
    let position = this.#placed(look, angle);
    if (this.#posed && camera.position.distanceTo(target) > 0) {
      const easedLook = target.clone().lerp(look, Framing.SMOOTHING);
      const eased = this.#placed(easedLook, ShotAngle.of(camera.position, target).toward(angle, Framing.SMOOTHING));
      const toward = new THREE.Vector3().subVectors(eased, look);
      const distance = toward.length();
      if (distance > 0 && this.#sight.reach(look, toward.divideScalar(distance), distance) === distance) {
        position = eased;
        look = easedLook;
      }
    }
    camera.position.copy(position);
    target.copy(look);
    camera.lookAt(look);
    this.#posed = true;
    this.#view.requestRender();
  }

  /**
   * @param {THREE.Vector3} look What a shot looks at.
   * @param {ShotAngle} angle Where the camera would stand around it.
   * @returns {THREE.Vector3} Where the camera stands: at the angle, in front of what
   *   stands in the way.
   */
  #placed(look, angle) {
    const direction = angle.direction();
    return look.clone().addScaledVector(direction, this.#sight.reach(look, direction, angle.distance));
  }
}
