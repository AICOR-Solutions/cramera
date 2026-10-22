/**
 * What the contact simulation measures, drawn over the shown laboratory: the liquid in
 * each vessel with its tilted surface, the liquid in flight and the puddles, the
 * contacts and the target an object is pulled towards.
 */

import * as THREE from 'three';

import {
  DropletKey,
  LiquidStateKey,
  MeasuredContactKey,
  PuddleKey,
  PullTargetKey,
  SnapshotKey,
  VesselInteriorKey,
  VesselLiquidKey,
} from '../../protocol.js';

/**
 * How many cubic metres a millilitre is.
 */
const CUBIC_METRES_PER_MILLILITRE = 1e-6;

/**
 * How many points outline a liquid surface.
 */
const SURFACE_SEGMENTS = 32;

/**
 * How many points describe the interior's profile for the liquid body.
 */
const PROFILE_SEGMENTS = 12;

/**
 * How much smaller than the glass's inside the liquid is drawn, so the glass shows.
 */
const LIQUID_INSET = 0.97;

/**
 * How thick a puddle is taken to be when its area is drawn, in metres.
 */
const PUDDLE_THICKNESS = 0.001;

/**
 * The radius of a contact marker, in metres.
 */
const CONTACT_RADIUS = 0.002;

/**
 * The radius of the target marker, in metres.
 */
const TARGET_RADIUS = 0.006;

/**
 * The opacity of a puddle.
 */
const PUDDLE_OPACITY = 0.82;

/**
 * The liquid's roughness: a calm, glossy surface. The liquid is opaque, so the
 * transmissive glass around it shows it.
 */
const LIQUID_ROUGHNESS = 0.2;

/**
 * The colours of the markers.
 */
const MarkerColor = Object.freeze({ CONTACT: 0xdc2626, TARGET: 0xf97316 });

/**
 * The volume below which a vessel counts as empty, in millilitres.
 */
const EMPTY = 1e-6;

/**
 * The quarter turn that stands a lathe, which turns about y, upright on z.
 */
const UPRIGHT = Math.PI / 2;

// %% surface

/**
 * The outline of a liquid surface in its vessel's frame: where the surface plane meets
 * the inside of the vessel, a cylinder above a half sphere.
 * @param {Object} interior The vessel interior, keyed by `VesselInteriorKey`.
 * @param {Array<number>} normal The surface's unit normal in the vessel's frame.
 * @param {number} offset The surface plane's offset along the normal.
 * @param {number=} segments How many points to return.
 * @returns {Array<Array<number>>} The outline's points, `[x, y, z]`.
 */
export function surfaceOutline(interior, normal, offset, segments = SURFACE_SEGMENTS) {
  const radius = interior[VesselInteriorKey.RADIUS];
  const bottom = interior[VesselInteriorKey.BOTTOM];
  const rim = interior[VesselInteriorKey.RIM];
  const center = bottom + radius;
  const [nx, ny, nz] = normal;
  const points = [];
  for (let index = 0; index < segments; index += 1) {
    const angle = (2 * Math.PI * index) / segments;
    const [cx, cy] = [Math.cos(angle), Math.sin(angle)];
    let height = (offset - radius * (nx * cx + ny * cy)) / nz;
    let reach = radius;
    if (height < center) {
      const depth = Math.max(0, Math.min(radius, center - height));
      reach = Math.sqrt(Math.max(0, radius * radius - depth * depth));
      height = (offset - reach * (nx * cx + ny * cy)) / nz;
    }
    height = Math.min(rim, Math.max(bottom, height));
    points.push([reach * cx, reach * cy, height]);
  }
  return points;
}

/**
 * @param {number} volume A volume in millilitres.
 * @returns {number} The radius of a sphere of that volume, in metres.
 */
export function sphereRadius(volume) {
  return Math.cbrt((3 * volume * CUBIC_METRES_PER_MILLILITRE) / (4 * Math.PI));
}

/**
 * @param {number} volume A volume in millilitres.
 * @returns {number} The radius of a puddle of that volume, in metres.
 */
export function puddleRadius(volume) {
  return Math.sqrt((volume * CUBIC_METRES_PER_MILLILITRE) / (Math.PI * PUDDLE_THICKNESS));
}

// %% one vessel's liquid

class VesselLiquidView {
  /**
   * The vessel's frame.
   * @type {THREE.Group}
   */
  group = new THREE.Group();

  /**
   * The plane cutting the liquid body at its surface, in the laboratory's frame.
   * @type {THREE.Plane}
   */
  #plane = new THREE.Plane();

  /**
   * The liquid's material.
   * @type {THREE.MeshStandardMaterial}
   */
  #material;

  /**
   * The liquid body: the interior, cut at the surface.
   * @type {THREE.Mesh}
   */
  #body;

  /**
   * The surface, a fan of triangles.
   * @type {THREE.Mesh}
   */
  #surface;

  /**
   * The vessel interior.
   * @type {Object}
   */
  #interior;

  /**
   * @param {Object} interior The vessel interior, keyed by `VesselInteriorKey`.
   */
  constructor(interior) {
    this.#interior = interior;
    const radius = interior[VesselInteriorKey.RADIUS] * LIQUID_INSET;
    const bottom = interior[VesselInteriorKey.BOTTOM];
    const center = bottom + interior[VesselInteriorKey.RADIUS];
    const profile = [];
    for (let index = 0; index <= PROFILE_SEGMENTS; index += 1) {
      const angle = -UPRIGHT + (UPRIGHT * index) / PROFILE_SEGMENTS;
      profile.push(new THREE.Vector2(radius * Math.cos(angle), center + radius * Math.sin(angle)));
    }
    profile.push(new THREE.Vector2(radius, interior[VesselInteriorKey.RIM]));
    const geometry = new THREE.LatheGeometry(profile, SURFACE_SEGMENTS);
    geometry.rotateX(UPRIGHT);
    this.#material = new THREE.MeshStandardMaterial({
      side: THREE.DoubleSide,
      clippingPlanes: [this.#plane],
      roughness: LIQUID_ROUGHNESS,
    });
    this.#body = new THREE.Mesh(geometry, this.#material);
    const surface = new THREE.BufferGeometry();
    surface.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array((SURFACE_SEGMENTS + 1) * 3), 3));
    const triangles = [];
    for (let index = 0; index < SURFACE_SEGMENTS; index += 1) triangles.push(SURFACE_SEGMENTS, index, (index + 1) % SURFACE_SEGMENTS);
    surface.setIndex(triangles);
    this.#surface = new THREE.Mesh(surface, this.#material);
    this.group.add(this.#body, this.#surface);
  }

  /**
   * @param {Array<number>} pose The vessel's pose.
   * @param {Object} liquid The vessel's liquid, keyed by `VesselLiquidKey`.
   */
  show(pose, liquid) {
    this.group.visible = liquid[VesselLiquidKey.VOLUME] > EMPTY;
    if (!this.group.visible) return;
    this.group.position.set(pose[0], pose[1], pose[2]);
    this.group.quaternion.set(pose[3], pose[4], pose[5], pose[6]);
    this.group.updateMatrixWorld(true);
    this.#material.color.setRGB(...liquid[VesselLiquidKey.COLOR], THREE.LinearSRGBColorSpace);
    const normal = liquid[VesselLiquidKey.NORMAL];
    const offset = liquid[VesselLiquidKey.OFFSET];
    const worldNormal = new THREE.Vector3(...normal).applyQuaternion(this.group.quaternion);
    this.#plane.set(worldNormal.clone().negate(), offset + worldNormal.dot(this.group.position));
    const outline = surfaceOutline(this.#interior, normal, offset);
    const positions = this.#surface.geometry.getAttribute('position');
    const middle = [0, 1, 2].map((axis) => outline.reduce((sum, point) => sum + point[axis], 0) / outline.length);
    outline.forEach((point, index) => positions.setXYZ(index, ...point));
    positions.setXYZ(outline.length, ...middle);
    positions.needsUpdate = true;
    this.#surface.geometry.computeBoundingSphere();
  }

  /**
   * Free the geometries and the material.
   */
  dispose() {
    this.#body.geometry.dispose();
    this.#surface.geometry.dispose();
    this.#material.dispose();
  }
}

// %% marker pools

class SpherePool {
  /**
   * The spheres, shown or hidden.
   * @type {Array<THREE.Mesh>}
   */
  #spheres = [];

  /**
   * The group holding the spheres.
   * @type {THREE.Group}
   */
  group = new THREE.Group();

  /**
   * The spheres' shared geometry.
   * @type {THREE.SphereGeometry}
   */
  #geometry = new THREE.SphereGeometry(1, 12, 8);

  /**
   * Show one sphere per entry and hide the rest.
   * @param {Array<{position: Array<number>, radius: number, color: Array<number>|number}>} entries The spheres.
   */
  show(entries) {
    entries.forEach((entry, index) => {
      const sphere = this.#sphere(index);
      sphere.visible = true;
      sphere.position.set(...entry.position);
      sphere.scale.setScalar(entry.radius);
      if (Array.isArray(entry.color)) sphere.material.color.setRGB(...entry.color, THREE.LinearSRGBColorSpace);
      else sphere.material.color.set(entry.color);
    });
    for (let index = entries.length; index < this.#spheres.length; index += 1) this.#spheres[index].visible = false;
  }

  /**
   * @param {number} index A sphere's position in the pool.
   * @returns {THREE.Mesh} The sphere, created when the pool is too small.
   */
  #sphere(index) {
    while (this.#spheres.length <= index) {
      const sphere = new THREE.Mesh(this.#geometry, new THREE.MeshStandardMaterial());
      this.#spheres.push(sphere);
      this.group.add(sphere);
    }
    return this.#spheres[index];
  }

  /**
   * Free the geometry and the materials.
   */
  dispose() {
    this.#geometry.dispose();
    for (const sphere of this.#spheres) sphere.material.dispose();
  }
}

class PuddlePool {
  /**
   * The group holding the puddles.
   * @type {THREE.Group}
   */
  group = new THREE.Group();

  /**
   * The puddles, shown or hidden.
   * @type {Array<THREE.Mesh>}
   */
  #puddles = [];

  /**
   * The puddles' shared geometry, a unit disc facing up.
   * @type {THREE.CircleGeometry}
   */
  #geometry = new THREE.CircleGeometry(1, SURFACE_SEGMENTS);

  /**
   * @param {Array<Object>} puddles The puddles, keyed by `PuddleKey`.
   */
  show(puddles) {
    puddles.forEach((puddle, index) => {
      while (this.#puddles.length <= index) {
        const mesh = new THREE.Mesh(this.#geometry, new THREE.MeshStandardMaterial({ transparent: true, opacity: PUDDLE_OPACITY }));
        this.#puddles.push(mesh);
        this.group.add(mesh);
      }
      const mesh = this.#puddles[index];
      mesh.visible = true;
      mesh.position.set(...puddle[PuddleKey.POSITION]);
      mesh.scale.setScalar(puddleRadius(puddle[PuddleKey.VOLUME]));
      mesh.material.color.setRGB(...puddle[PuddleKey.COLOR], THREE.LinearSRGBColorSpace);
    });
    for (let index = puddles.length; index < this.#puddles.length; index += 1) this.#puddles[index].visible = false;
  }

  /**
   * Free the geometry and the materials.
   */
  dispose() {
    this.#geometry.dispose();
    for (const puddle of this.#puddles) puddle.material.dispose();
  }
}

// %% view

export class SimulationView {
  /**
   * The group holding everything this view draws.
   * @type {THREE.Group}
   */
  group = new THREE.Group();

  /**
   * The liquid of each vessel, by key.
   * @type {Map<string, VesselLiquidView>}
   */
  #vessels = new Map();

  /**
   * The liquid in flight.
   * @type {SpherePool}
   */
  #droplets = new SpherePool();

  /**
   * The contacts.
   * @type {SpherePool}
   */
  #contacts = new SpherePool();

  /**
   * The pull target.
   * @type {SpherePool}
   */
  #target = new SpherePool();

  /**
   * The puddles.
   * @type {PuddlePool}
   */
  #puddles = new PuddlePool();

  /**
   * Whether contacts are drawn.
   * @type {boolean}
   */
  showContacts = true;

  /**
   * @param {Object} interior The vessel interior, keyed by `VesselInteriorKey`.
   * @param {Array<string>} vessels The keys of the vessels holding liquid.
   */
  constructor(interior, vessels) {
    for (const key of vessels) {
      const view = new VesselLiquidView(interior);
      this.#vessels.set(key, view);
      this.group.add(view.group);
    }
    this.group.add(this.#droplets.group, this.#puddles.group, this.#contacts.group, this.#target.group);
  }

  /**
   * Draw one measured state.
   * @param {Object} snapshot The simulation's snapshot, keyed by `SnapshotKey`.
   */
  show(snapshot) {
    const objects = snapshot[SnapshotKey.OBJECTS];
    const liquid = snapshot[SnapshotKey.LIQUID];
    for (const [key, view] of this.#vessels) {
      const content = liquid[LiquidStateKey.VESSELS][key];
      if (content && objects[key]) view.show(objects[key], content);
    }
    this.#droplets.show(
      liquid[LiquidStateKey.DROPLETS].map((droplet) => ({
        position: droplet[DropletKey.POSITION],
        radius: sphereRadius(droplet[DropletKey.VOLUME]),
        color: droplet[DropletKey.COLOR],
      })),
    );
    this.#puddles.show(liquid[LiquidStateKey.PUDDLES]);
    const contacts = this.showContacts ? snapshot[SnapshotKey.CONTACTS] : [];
    this.#contacts.show(
      contacts.map((contact) => ({ position: contact[MeasuredContactKey.POSITION], radius: CONTACT_RADIUS, color: MarkerColor.CONTACT })),
    );
    const target = snapshot[SnapshotKey.TARGET];
    this.#target.show(target ? [{ position: target[PullTargetKey.POSITION], radius: TARGET_RADIUS, color: MarkerColor.TARGET }] : []);
  }

  /**
   * Remove the drawing and free its resources.
   */
  dispose() {
    this.group.removeFromParent();
    for (const view of this.#vessels.values()) view.dispose();
    for (const pool of [this.#droplets, this.#contacts, this.#target, this.#puddles]) pool.dispose();
  }
}
