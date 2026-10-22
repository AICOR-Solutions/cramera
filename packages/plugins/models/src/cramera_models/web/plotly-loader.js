/**
 * Loads the vendored Plotly bundle on first use. The bundle is a browser script that
 * defines the global `Plotly`, not an ES module, so it is added as a script element.
 */

// %% errors

/**
 * The Plotly bundle could not be loaded.
 */
export class PlotlyUnavailable extends Error {
  /**
   * @param {string} url The bundle's URL.
   */
  constructor(url) {
    super(`The plotting library could not be loaded from ${url}.`);
    /**
     * The bundle's URL.
     * @type {string}
     */
    this.url = url;
  }
}

// %% loader

export class PlotlyLoader {
  /**
   * The page.
   * @type {Document}
   */
  #document;

  /**
   * The bundle's URL.
   * @type {string}
   */
  #url;

  /**
   * The load in progress or done, once started.
   * @type {Promise<Object>|null}
   */
  #loading = null;

  /**
   * @param {Document} document The page.
   * @param {string} url The bundle's URL.
   */
  constructor(document, url) {
    this.#document = document;
    this.#url = url;
  }

  /**
   * @returns {Promise<Object>} The `Plotly` object; the bundle is loaded once, and
   *   tried again after a failed load.
   * @throws {PlotlyUnavailable} When the bundle cannot be loaded.
   */
  load() {
    this.#loading ??= new Promise((resolve, reject) => {
      const script = this.#document.createElement('script');
      script.src = this.#url;
      script.addEventListener('load', () => resolve(this.#document.defaultView.Plotly));
      script.addEventListener('error', () => {
        this.#loading = null;
        script.remove();
        reject(new PlotlyUnavailable(this.#url));
      });
      this.#document.head.append(script);
    });
    return this.#loading;
  }
}
