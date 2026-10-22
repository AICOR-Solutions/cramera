/**
 * Knowing when every file a scene requested has arrived.
 */

import * as THREE from 'three';

// %% progress

export class LoadingProgress {
  /**
   * The manager every loader of one scene reports to.
   * @type {THREE.LoadingManager}
   */
  manager;

  /**
   * Settles once no request is pending.
   * @type {Promise<void>}
   */
  #idle;

  /**
   * The URLs that failed.
   * @type {Array<string>}
   */
  #failed = [];

  /**
   * Whether any request started.
   * @type {boolean}
   */
  #started = false;

  /**
   * Settles the promise `idle` returns.
   * @type {function(): void}
   */
  #settle;

  /**
   * @param {function(number, number): void=} onProgress Called with loaded and total request counts.
   */
  constructor(onProgress = () => {}) {
    this.#idle = new Promise((resolve) => { this.#settle = resolve; });
    this.manager = new THREE.LoadingManager(
      () => this.#settle(),
      (_url, loaded, total) => onProgress(loaded, total),
      (url) => this.#failed.push(url),
    );
    this.manager.onStart = () => { this.#started = true; };
  }

  /**
   * @returns {Promise<void>} Settles once every request has finished or failed.
   */
  idle() {
    return this.#idle;
  }

  /**
   * Settle at once when the scene requested nothing through the manager.
   */
  settleIfUnused() {
    if (!this.#started) this.#settle();
  }

  /**
   * @returns {Array<string>} The URLs whose requests failed.
   */
  failedUrls() {
    return [...this.#failed];
  }
}
