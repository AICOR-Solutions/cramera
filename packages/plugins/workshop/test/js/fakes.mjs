/**
 * Stand-ins for the workshop routes, the shown scene, the clock, the timers and the
 * network, for the workshop plugin's tests.
 */

import { readFileSync } from 'node:fs';

import { RequestFailed } from 'cramera-viewer/core/viewer-api.js';
import {
  ThreadKey,
  ThreadState,
  WorkshopAction,
  WorkshopCommandKey,
  WorkshopSceneKey,
  WorkshopStateKey,
} from 'cramera-viewer/protocol.js';

/**
 * The first HTTP status of a refused request.
 */
const FIRST_ERROR_STATUS = 400;

/**
 * The AICOR workshop's scene description.
 */
export const SCENE = JSON.parse(readFileSync(new URL('./workshop_scene.json', import.meta.url), 'utf-8'));

/**
 * Its workshop description.
 */
export const WORKSHOP = SCENE[WorkshopSceneKey.WORKSHOP];

/**
 * A measured state of the contact world.
 */
export const STATE = JSON.parse(readFileSync(new URL('./state.json', import.meta.url), 'utf-8'));

/**
 * @returns {Object} A fresh copy of the measured state.
 */
export function freshState() {
  return structuredClone(STATE);
}

// %% routes

/**
 * A contact world that puts a held body wherever its target is, captures a released
 * screw and engages a driver at their goals, and records every command.
 */
export class FakeClient {
  constructor() {
    this.current = freshState();
    this.current[WorkshopStateKey.RUNNING] = false;
    this.commands = [];
    this.failure = null;
    this.stateReads = 0;
    this.frozen = false;
  }

  async state() {
    this.stateReads += 1;
    if (this.failure) throw this.failure;
    return structuredClone(this.current);
  }

  async command(command) {
    this.commands.push(command);
    if (this.failure) throw this.failure;
    const state = this.current;
    const thread = state[WorkshopStateKey.THREAD];
    switch (command[WorkshopCommandKey.ACTION]) {
      case WorkshopAction.START:
        state[WorkshopStateKey.RUNNING] = true;
        break;
      case WorkshopAction.PAUSE:
        state[WorkshopStateKey.RUNNING] = false;
        state[WorkshopStateKey.HELD] = null;
        break;
      case WorkshopAction.GRAB:
        state[WorkshopStateKey.HELD] = command[WorkshopCommandKey.OBJECT];
        break;
      case WorkshopAction.MOVE:
        if (this.frozen) break;
        state[WorkshopStateKey.OBJECTS][command[WorkshopCommandKey.OBJECT]] = command[WorkshopCommandKey.POSE];
        if (JSON.stringify(command[WorkshopCommandKey.POSE]) === JSON.stringify(thread[ThreadKey.DRIVER_TARGET_POSE])) thread[ThreadKey.ENGAGED] = true;
        break;
      case WorkshopAction.RELEASE:
        if (state[WorkshopStateKey.HELD] === thread[ThreadKey.SCREW]) thread[ThreadKey.STATE] = ThreadState.SEATED;
        state[WorkshopStateKey.HELD] = null;
        break;
      default:
        break;
    }
    return structuredClone(state);
  }
}

/**
 * @param {number} status An HTTP status.
 * @param {string} reason The reason the viewer gave.
 * @returns {RequestFailed} A refused request.
 */
export function refused(status, reason) {
  return new RequestFailed('http://127.0.0.1/', status, reason);
}

// %% scene

/**
 * A shown scene that records what it is asked to show.
 */
export class FakeScene {
  constructor() {
    this.shown = [];
    this.views = [];
    this.pauses = 0;
  }

  show(state) {
    this.shown.push(state);
  }

  look(view) {
    this.views.push(view);
  }

  pausePlayback() {
    this.pauses += 1;
  }
}

/**
 * A clock whose waits pass at once and move it on.
 */
export class FakeClock {
  constructor() {
    this.time = 0;
  }

  now() {
    return this.time;
  }

  async wait(milliseconds) {
    this.time += milliseconds;
  }
}

/**
 * Timers that record the intervals instead of running them.
 */
export class FakeTimers {
  constructor() {
    this.intervals = new Map();
    this.next = 1;
  }

  setInterval(callback, milliseconds) {
    const identifier = this.next++;
    this.intervals.set(identifier, { callback, milliseconds });
    return identifier;
  }

  clearInterval(identifier) {
    this.intervals.delete(identifier);
  }
}

// %% network

/**
 * An answer of the network with JSON headers.
 */
export class FakeAnswer {
  /**
   * @param {number} status The HTTP status.
   * @param {*} body The decoded JSON body.
   * @param {string} mediaType The answer's media type.
   */
  constructor(status, body, mediaType = 'application/json') {
    this.status = status;
    this.ok = status < FIRST_ERROR_STATUS;
    this.statusText = `status ${status}`;
    this.body = body;
    this.headers = new Map([['Content-Type', mediaType]]);
  }

  async json() {
    return this.body;
  }
}
