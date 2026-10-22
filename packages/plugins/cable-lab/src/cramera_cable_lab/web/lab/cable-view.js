/**
 * The cable lab's 3D view: draws only what the simulation measured — the capsules, the
 * pads, the rail, the anchor, the contacts and, on request, the semantic points.
 */

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

import { CableConfigurationKey, CableLabKey } from '../../../protocol.js';

/**
 * The colours of the parts.
 */
export const PartColor = Object.freeze({
  CABLE: 0xee5867,
  PAD: 0x43d5c4,
  POINT: 0xffffff,
  CONTACT: 0xffc16c,
  ANCHOR: 0xe1b472,
  SUPPORT: 0x344350,
});

/**
 * The camera's lens and clipping planes.
 */
const CAMERA = Object.freeze({ FIELD_OF_VIEW: 40, NEAR: 0.001, FAR: 30 });

/**
 * How close and how far the orbit controls let the camera come, in metres.
 */
const ORBIT = Object.freeze({ MINIMUM: 0.03, MAXIMUM: 5 });

/**
 * Where the camera looks before a cable is shown, and from which direction.
 */
const HOME = Object.freeze({ TARGET: [0.15, 0, 0.35], DIRECTION: [0.5, -0.8, 0.55], DISTANCE: 0.7, SMALLEST: 0.35, MARGIN: 2 });

/**
 * The size of the grid on the floor, and its divisions.
 */
const GRID = Object.freeze({ SIZE: 2, DIVISIONS: 40, CENTRE: 0x355064, LINES: 0x213340 });

/**
 * The radius of a cable when the state names none, in metres.
 */
const DEFAULT_RADIUS = 0.005;

/**
 * How large markers are drawn, relative to the cable's radius.
 */
const MarkerScale = Object.freeze({ CONTACT: 0.6, POINT: 0.4, ANCHOR: 1.5 });

/**
 * The detail of the round shapes.
 */
const SEGMENTS = Object.freeze({ SPHERE_WIDTH: 14, SPHERE_HEIGHT: 10, CYLINDER: 14 });

/**
 * The lights: sky and ground colours, intensities and where the sun stands.
 */
const LIGHTS = Object.freeze({ SKY: 0xe0f4ff, GROUND: 0x627381, AMBIENT: 1.1, SUN: 1.5, SUN_POSITION: [0.3, -0.5, 1.6] });

/**
 * The axis three.js cylinders are built along.
 */
const CYLINDER_AXIS = new THREE.Vector3(0, 1, 0);

// %% errors

/**
 * A browser without WebGL.
 */
export class CableViewUnavailable extends Error {
  constructor() {
    super('This browser could not create a WebGL context for the cable view.');
  }
}

// %% view

export class CableView {
  /**
   * The element the canvas fills.
   * @type {HTMLElement}
   */
  #container;

  /**
   * The renderer.
   * @type {THREE.WebGLRenderer}
   */
  #renderer;

  /**
   * The scene.
   * @type {THREE.Scene}
   */
  #scene = new THREE.Scene();

  /**
   * The camera.
   * @type {THREE.PerspectiveCamera}
   */
  #camera;

  /**
   * The orbit controls.
   * @type {OrbitControls}
   */
  #controls;

  /**
   * The shared materials by part.
   * @type {Object<string, THREE.Material>}
   */
  #materials;

  /**
   * The shared unit shapes.
   * @type {{sphere: THREE.BufferGeometry, cylinder: THREE.BufferGeometry, box: THREE.BufferGeometry}}
   */
  #shapes;

  /**
   * The drawn parts, reused from state to state.
   * @type {{capsules: Array<THREE.Group>, pads: Array<THREE.Mesh>, contacts: Array<THREE.Mesh>, points: Array<THREE.Mesh>}}
   */
  #pools = { capsules: [], pads: [], contacts: [], points: [] };

  /**
   * The rail.
   * @type {THREE.Mesh}
   */
  #support;

  /**
   * The pinned first point.
   * @type {THREE.Mesh}
   */
  #anchor;

  /**
   * Watches the container's size.
   * @type {ResizeObserver}
   */
  #resizeObserver;

  /**
   * The pending animation frame.
   * @type {number}
   */
  #frame = 0;

  /**
   * The last state drawn.
   * @type {Object|null}
   */
  #state = null;

  /**
   * Whether the camera still waits to frame the first cable.
   * @type {boolean}
   */
  needsFraming = true;

  /**
   * Whether the semantic points are drawn.
   * @type {boolean}
   */
  showPoints = false;

  /**
   * @param {HTMLElement} container The element the canvas fills.
   * @throws {CableViewUnavailable} When the browser has no WebGL.
   */
  constructor(container) {
    this.#container = container;
    const canvas = container.ownerDocument.createElement('canvas');
    if (!canvas.getContext('webgl2')) throw new CableViewUnavailable();
    this.#renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    this.#renderer.setPixelRatio(container.ownerDocument.defaultView.devicePixelRatio);
    this.#renderer.shadowMap.enabled = true;
    container.prepend(canvas);
    this.#camera = new THREE.PerspectiveCamera(CAMERA.FIELD_OF_VIEW, 1, CAMERA.NEAR, CAMERA.FAR);
    this.#camera.up.set(0, 0, 1);
    this.#controls = new OrbitControls(this.#camera, canvas);
    this.#controls.enableDamping = true;
    this.#controls.minDistance = ORBIT.MINIMUM;
    this.#controls.maxDistance = ORBIT.MAXIMUM;
    this.#scene.add(new THREE.HemisphereLight(LIGHTS.SKY, LIGHTS.GROUND, LIGHTS.AMBIENT));
    const sun = new THREE.DirectionalLight(0xffffff, LIGHTS.SUN);
    sun.position.set(...LIGHTS.SUN_POSITION);
    sun.castShadow = true;
    this.#scene.add(sun);
    const grid = new THREE.GridHelper(GRID.SIZE, GRID.DIVISIONS, GRID.CENTRE, GRID.LINES);
    grid.rotation.x = Math.PI / 2;
    this.#scene.add(grid);
    this.#materials = {
      cable: new THREE.MeshStandardMaterial({ color: PartColor.CABLE }),
      pad: new THREE.MeshStandardMaterial({ color: PartColor.PAD }),
      point: new THREE.MeshBasicMaterial({ color: PartColor.POINT, depthTest: false, transparent: true }),
      contact: new THREE.MeshBasicMaterial({ color: PartColor.CONTACT }),
      anchor: new THREE.MeshStandardMaterial({ color: PartColor.ANCHOR }),
      support: new THREE.MeshStandardMaterial({ color: PartColor.SUPPORT }),
    };
    this.#shapes = {
      sphere: new THREE.SphereGeometry(1, SEGMENTS.SPHERE_WIDTH, SEGMENTS.SPHERE_HEIGHT),
      cylinder: new THREE.CylinderGeometry(1, 1, 1, SEGMENTS.CYLINDER),
      box: new THREE.BoxGeometry(1, 1, 1),
    };
    this.#support = this.#mesh(this.#shapes.box, this.#materials.support);
    this.#anchor = this.#mesh(this.#shapes.sphere, this.#materials.anchor);
    this.#support.visible = false;
    this.#anchor.visible = false;
    this.#resizeObserver = new ResizeObserver(() => this.#resize());
    this.#resizeObserver.observe(container);
    this.#resize();
    this.home();
    const loop = () => {
      this.#controls.update();
      this.#renderer.render(this.#scene, this.#camera);
      this.#frame = requestAnimationFrame(loop);
    };
    this.#frame = requestAnimationFrame(loop);
  }

  /**
   * @param {THREE.BufferGeometry} shape A unit shape.
   * @param {THREE.Material} material Its material.
   * @returns {THREE.Mesh} A mesh of the scene.
   */
  #mesh(shape, material) {
    const mesh = new THREE.Mesh(shape, material);
    mesh.castShadow = true;
    this.#scene.add(mesh);
    return mesh;
  }

  /**
   * @returns {THREE.Group} A capsule: a cylinder and two spheres.
   */
  #capsule() {
    const group = new THREE.Group();
    group.add(
      new THREE.Mesh(this.#shapes.cylinder, this.#materials.cable),
      new THREE.Mesh(this.#shapes.sphere, this.#materials.cable),
      new THREE.Mesh(this.#shapes.sphere, this.#materials.cable),
    );
    this.#scene.add(group);
    return group;
  }

  #resize() {
    const width = this.#container.clientWidth || 1;
    const height = this.#container.clientHeight || 1;
    this.#renderer.setSize(width, height, false);
    this.#camera.aspect = width / height;
    this.#camera.updateProjectionMatrix();
  }

  /**
   * Show enough drawn parts for the values and update each one.
   * @param {Array<THREE.Object3D>} pool The drawn parts.
   * @param {Array<Object>} values What to draw.
   * @param {function(): THREE.Object3D} create Makes another part.
   * @param {function(THREE.Object3D, Object): void} update Puts a part where its value says.
   */
  #sync(pool, values, create, update) {
    while (pool.length < values.length) pool.push(create());
    pool.forEach((part, index) => {
      part.visible = index < values.length;
      if (part.visible) update(part, values[index]);
    });
  }

  /**
   * Draw a measured state.
   * @param {Object} state The cable lab's state.
   */
  show(state) {
    this.#state = state;
    const configuration = state[CableLabKey.CONFIGURATION] ?? {};
    const radius = configuration[CableConfigurationKey.RADIUS] ?? DEFAULT_RADIUS;
    const color = configuration[CableConfigurationKey.COLOR];
    if (color) this.#materials.cable.color.setRGB(color[0], color[1], color[2]);
    this.#sync(this.#pools.capsules, state[CableLabKey.SEGMENTS] ?? [], () => this.#capsule(), (group, segment) => {
      const start = new THREE.Vector3(...segment[CableLabKey.START]);
      const end = new THREE.Vector3(...segment[CableLabKey.END]);
      const [cylinder, first, second] = group.children;
      const direction = end.clone().sub(start);
      cylinder.position.copy(start).add(end).multiplyScalar(0.5);
      cylinder.scale.set(radius, direction.length(), radius);
      cylinder.quaternion.setFromUnitVectors(CYLINDER_AXIS, direction.normalize());
      first.position.copy(start);
      second.position.copy(end);
      first.scale.setScalar(radius);
      second.scale.setScalar(radius);
    });
    const pads = state[CableLabKey.GRIPPER]?.[CableLabKey.PADS] ?? [];
    this.#sync(this.#pools.pads, pads, () => this.#mesh(this.#shapes.box, this.#materials.pad), (mesh, pad) => this.#placeBox(mesh, pad));
    this.#sync(this.#pools.contacts, state[CableLabKey.CONTACTS] ?? [], () => this.#mesh(this.#shapes.sphere, this.#materials.contact), (mesh, contact) => {
      mesh.position.set(...contact[CableLabKey.POSITION]);
      mesh.scale.setScalar(radius * MarkerScale.CONTACT);
    });
    this.#sync(this.#pools.points, state[CableLabKey.POINTS] ?? [], () => this.#mesh(this.#shapes.sphere, this.#materials.point), (mesh, point) => {
      mesh.position.set(...point[CableLabKey.POSITION]);
      mesh.scale.setScalar(radius * MarkerScale.POINT);
    });
    for (const point of this.#pools.points) point.visible &&= this.showPoints;
    const support = state[CableLabKey.SUPPORT];
    this.#support.visible = Boolean(support);
    if (support) this.#placeBox(this.#support, support);
    const anchor = state[CableLabKey.ANCHOR];
    this.#anchor.visible = Boolean(anchor?.[CableLabKey.ENABLED]);
    if (this.#anchor.visible) {
      this.#anchor.position.set(...anchor[CableLabKey.POSITION]);
      this.#anchor.scale.setScalar(radius * MarkerScale.ANCHOR);
    }
    if (this.needsFraming && (state[CableLabKey.SEGMENTS] ?? []).length) {
      this.home();
      this.needsFraming = false;
    }
  }

  /**
   * @param {THREE.Mesh} mesh A unit box.
   * @param {Object} box An oriented box of the state.
   */
  #placeBox(mesh, box) {
    const pose = box[CableLabKey.POSE];
    mesh.position.set(pose[0], pose[1], pose[2]);
    mesh.quaternion.set(pose[3], pose[4], pose[5], pose[6]);
    mesh.scale.set(...box[CableLabKey.SIZE]);
  }

  /**
   * Look at the whole cable, or at where it will be.
   */
  home() {
    const ends = (this.#state?.[CableLabKey.SEGMENTS] ?? []).flatMap((segment) => [segment[CableLabKey.START], segment[CableLabKey.END]]);
    const target = new THREE.Vector3(...HOME.TARGET);
    let distance = HOME.DISTANCE;
    if (ends.length) {
      const bounds = new THREE.Box3().setFromPoints(ends.map((end) => new THREE.Vector3(...end)));
      bounds.getCenter(target);
      distance = Math.max(HOME.SMALLEST, bounds.getSize(new THREE.Vector3()).length() * HOME.MARGIN);
    }
    this.#controls.target.copy(target);
    this.#camera.position.copy(target).add(new THREE.Vector3(...HOME.DIRECTION).multiplyScalar(distance));
    this.#controls.update();
  }

  /**
   * Show or hide the semantic points.
   * @param {boolean} shown Whether they are drawn.
   */
  setPointsShown(shown) {
    this.showPoints = shown;
    if (this.#state) this.show(this.#state);
  }

  /**
   * Stop drawing and free the renderer, shapes and materials.
   */
  dispose() {
    cancelAnimationFrame(this.#frame);
    this.#resizeObserver.disconnect();
    this.#controls.dispose();
    Object.values(this.#shapes).forEach((shape) => shape.dispose());
    Object.values(this.#materials).forEach((material) => material.dispose());
    this.#renderer.dispose();
    this.#renderer.domElement.remove();
  }
}
