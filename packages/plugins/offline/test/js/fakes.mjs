/**
 * Stand-ins for the browser's timers and network, for the offline plugin's tests.
 */

import { ErrorKey } from 'cramera-viewer/protocol.js';

/**
 * The HTTP status of a path the network has no answer for.
 */
const NOT_FOUND = 404;

/**
 * The lowest and the first status past the successful ones.
 */
const SUCCESS = Object.freeze({ FIRST: 200, PAST: 300 });

// %% timer

/**
 * A timer whose calls are run by the test.
 */
export class ManualTimer {
  constructor() {
    /**
     * The pending calls by handle.
     * @type {Map<number, {milliseconds: number, callback: function(): void}>}
     */
    this.pending = new Map();
    /**
     * The next handle.
     * @type {number}
     */
    this.nextHandle = 1;
  }

  after(milliseconds, callback) {
    const handle = this.nextHandle++;
    this.pending.set(handle, { milliseconds, callback });
    return handle;
  }

  cancel(handle) {
    this.pending.delete(handle);
  }

  /**
   * Run every pending call.
   */
  runAll() {
    const calls = [...this.pending.values()];
    this.pending.clear();
    calls.forEach(({ callback }) => callback());
  }
}

// %% network

/**
 * An answer of the network.
 */
export class FakeAnswer {
  /**
   * @param {number} status The HTTP status.
   * @param {*} body The decoded JSON body.
   */
  constructor(status, body) {
    this.status = status;
    this.ok = status >= SUCCESS.FIRST && status < SUCCESS.PAST;
    this.body = body;
  }

  async json() {
    return this.body;
  }
}

/**
 * A network answering each URL path with a fixed answer and recording the requests.
 */
export class FakeNetwork {
  /**
   * @param {Object<string, FakeAnswer>} answers The answer of each URL path.
   */
  constructor(answers) {
    this.answers = answers;
    this.requested = [];
  }

  /**
   * @returns {function(string): Promise<FakeAnswer>} A `fetch` over the answers.
   */
  fetch() {
    return async (url) => {
      this.requested.push(url);
      const path = new URL(url).pathname;
      return this.answers[path] ?? new FakeAnswer(NOT_FOUND, { [ErrorKey.ERROR]: `no answer for ${path}` });
    };
  }
}

/**
 * The viewer's routes below a fixed base, as `ViewerApi.url` gives them.
 */
export class FakeApi {
  url(route) {
    return new URL(route.replace(/^\//, ''), 'http://127.0.0.1/viewer/').href;
  }
}
