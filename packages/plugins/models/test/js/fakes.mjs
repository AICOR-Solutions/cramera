/**
 * Stand-ins for the workbench routes, the network and Plotly, for the models plugin's
 * tests.
 */

import { RequestFailed } from 'cramera-viewer/core/viewer-api.js';

/**
 * The first HTTP status of a refused request.
 */
const FIRST_ERROR_STATUS = 400;

// %% workbench

/**
 * A workbench client answering with fixed documents and recording the questions.
 */
export class FakeClient {
  /**
   * @param {Object} state The workbench state it answers.
   */
  constructor(state) {
    this.currentState = state;
    this.asked = [];
    this.failure = null;
    this.answers = {};
  }

  async state() {
    if (this.failure) throw this.failure;
    return this.currentState;
  }

  async load(name, text) {
    this.asked.push(['load', name, text]);
    if (this.failure) throw this.failure;
    return this.currentState;
  }

  async probability(query, evidence) {
    this.asked.push(['probability', query, evidence]);
    return this.answers.probability;
  }

  async posterior(variables, evidence) {
    this.asked.push(['posterior', variables, evidence]);
    return this.answers.posterior;
  }

  async mode(evidence) {
    this.asked.push(['mode', evidence]);
    if (this.failure) throw this.failure;
    return this.answers.mode;
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

// %% plotting

/**
 * A Plotly that records the plots it draws.
 */
export class FakePlotly {
  constructor() {
    this.plots = [];
  }

  async newPlot(element, data, layout, options) {
    this.plots.push({ element, data, layout, options });
  }
}

/**
 * A loader handing out a fixed Plotly.
 */
export class FakePlotlyLoader {
  /**
   * @param {FakePlotly} plotly The Plotly to hand out.
   */
  constructor(plotly) {
    this.plotly = plotly;
  }

  async load() {
    return this.plotly;
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

/**
 * The viewer's routes below a fixed base, as `ViewerApi.url` gives them.
 */
export class FakeApi {
  url(route) {
    return new URL(route.replace(/^\//, ''), 'http://127.0.0.1/viewer/').href;
  }
}
