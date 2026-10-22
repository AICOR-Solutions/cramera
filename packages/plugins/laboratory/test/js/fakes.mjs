/**
 * Stand-ins for the viewer's parts the laboratory's browser modules use: its routes,
 * the network, a timer, the 3D view and a loaded scene.
 */

import { readFileSync } from 'node:fs';

import * as THREE from 'three';

import { RequestFailed } from 'cramera-viewer/core/viewer-api.js';
import { LaboratorySceneKey } from 'cramera-viewer/protocol.js';

/**
 * The directory of the Python tests' documents, which the browser tests share.
 */
const DATASET = new URL('../dataset/', import.meta.url);

/**
 * @param {string} name A document of the dataset.
 * @returns {Object} The decoded document.
 */
export function readDataset(name) {
  return JSON.parse(readFileSync(new URL(name, DATASET), 'utf8'));
}

// %% routes

export class FakeApi {
  constructor(scenes = []) {
    this.scenesIndex = { scenes: scenes.map((name) => ({ name, robot: '' })) };
    this.answers = new Map();
    this.requested = [];
  }

  url(route) {
    return `http://viewer${route}`;
  }

  scenes() {
    return Promise.resolve(this.scenesIndex);
  }

  async json(url) {
    this.requested.push(url);
    if (!this.answers.has(url)) throw new RequestFailed(url, 404, 'unknown');
    const answer = this.answers.get(url);
    if (answer instanceof Error) throw answer;
    return structuredClone(answer);
  }
}

export class FakeFetch {
  constructor() {
    this.requests = [];
    this.answers = new Map();
  }

  answer(url, status, body) {
    this.answers.set(url, { status, body });
  }

  async fetch(url, options) {
    this.requests.push({ url, options, body: JSON.parse(options.body) });
    const { status, body } = this.answers.get(url) ?? { status: 200, body: {} };
    return { ok: status < 400, status, statusText: String(status), json: async () => structuredClone(body) };
  }
}

// %% time

export class FakeTimer {
  constructor() {
    this.calls = [];
    this.cancelled = [];
  }

  after(milliseconds, callback) {
    this.calls.push({ milliseconds, callback });
    return this.calls.length;
  }

  cancel(handle) {
    this.cancelled.push(handle);
  }

  async runLatest() {
    await this.calls.at(-1).callback();
  }
}

// %% view and scene

export class FakeCanvas {
  constructor() {
    this.listeners = new Map();
  }

  addEventListener(type, listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(listener);
  }

  removeEventListener(type, listener) {
    this.listeners.get(type)?.delete(listener);
  }

  dispatch(type, event) {
    for (const listener of [...(this.listeners.get(type) ?? [])]) listener({ preventDefault() {}, ...event });
  }

  getBoundingClientRect() {
    return { left: 0, top: 0, width: 200, height: 200 };
  }
}

export class FakeView {
  constructor() {
    this.scene = new THREE.Scene();
    this.renderer = { localClippingEnabled: false, domElement: new FakeCanvas() };
    this.camera = new THREE.PerspectiveCamera(45, 1, 0.01, 100);
    this.controls = { enabled: true };
    this.renders = 0;
  }

  requestRender() {
    this.renders += 1;
  }
}

export class FakeLoadedScene {
  /**
   * @param {string} name The bundle's name.
   * @param {Object|null} controls The contact physics controls, or null for a plain scene.
   */
  constructor(name, controls) {
    this.name = name;
    this.description = controls ? { [LaboratorySceneKey.CONTACT_PHYSICS]: controls } : {};
    this.posed = [];
    this.jointValues = [];
    this.root = new THREE.Group();
    this.rackJoint = new THREE.Group();
    this.rackLink = new THREE.Group();
    this.root.add(this.rackJoint);
    this.rackJoint.add(this.rackLink);
    this.robot = {
      joints: { laboratory_drawer_joint: {}, laboratory_centrifuge_lid_joint: {} },
      links: { laboratory_rack: this.rackLink },
    };
    this.objects = { setPoses: (poses) => this.posed.push(poses) };
    this.models = {
      names: () => ['laboratory'],
      model: () => this.robot,
      setJointValues: (values) => this.jointValues.push(values),
    };
  }
}
