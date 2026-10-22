/**
 * The scene builder's routes as the builder page calls them.
 */

import {
  DraftRecordKey,
  ErrorKey,
  SceneBuilderName,
  SceneBuilderRoute,
  TemplateParameter,
  ViewerRoute,
} from '../../../protocol.js';
import { RequestFailed, ViewerApi } from '../../../core/viewer-api.js';

/**
 * The HTTP request parts the builder writes.
 */
const HttpPart = Object.freeze({
  POST: 'POST',
  CONTENT_TYPE: 'Content-Type',
  JSON: 'application/json',
});

/**
 * Separates the segments of a resource identifier.
 */
const PATH_SEPARATOR = '/';

// %% client

export class BuilderApi {
  /**
   * The viewer's routes, below which the builder's lie.
   * @type {ViewerApi}
   */
  #viewer;

  /**
   * Fetches a URL; `window.fetch` in the browser.
   * @type {function(string, Object=): Promise<Response>}
   */
  #fetch;

  /**
   * @param {function(string, Object=): Promise<Response>} fetch Fetches a URL.
   * @param {string} base The viewer's URL, ending in `/`.
   */
  constructor(fetch, base) {
    this.#fetch = fetch;
    this.#viewer = new ViewerApi(fetch, base);
  }

  /**
   * @param {string} route A `SceneBuilderRoute` value, with what follows a prefix.
   * @returns {string} The route's URL.
   */
  url(route) {
    return this.#viewer.url(`${ViewerRoute.PLUGIN_API}${SceneBuilderName.PLUGIN}/${route}`);
  }

  /**
   * @returns {Promise<Object>} The resources, scenes and drafts, with the limits.
   */
  catalog() {
    return this.#viewer.json(this.url(SceneBuilderRoute.CATALOG));
  }

  /**
   * @param {string} scene A bundle name.
   * @returns {Promise<Object>} A new draft of the scene.
   */
  template(scene) {
    const query = new URLSearchParams({ [TemplateParameter.SCENE]: scene });
    return this.#viewer.json(`${this.url(SceneBuilderRoute.TEMPLATE)}?${query}`);
  }

  /**
   * @returns {Promise<Object>} The saved drafts.
   */
  drafts() {
    return this.#viewer.json(this.url(SceneBuilderRoute.DRAFTS));
  }

  /**
   * @param {string} identifier A draft's identity.
   * @returns {Promise<Object>} The saved draft with its identity.
   */
  draft(identifier) {
    return this.#viewer.json(this.url(`${SceneBuilderRoute.DRAFT}${encodeURIComponent(identifier)}`));
  }

  /**
   * @param {Object} draft A draft.
   * @param {string|null} identifier The identity of the draft it replaces, or null for a new draft.
   * @returns {Promise<Object>} The saved draft with its identity.
   */
  save(draft, identifier) {
    const record = { [DraftRecordKey.DOCUMENT]: draft };
    if (identifier !== null) record[DraftRecordKey.IDENTIFIER] = identifier;
    return this.#post(this.url(SceneBuilderRoute.DRAFTS), JSON.stringify(record), HttpPart.JSON);
  }

  /**
   * @param {Blob} file A point cloud file.
   * @param {string} format Its `PointCloudFormat` value.
   * @returns {Promise<Object>} The kept point cloud as the catalog lists it.
   */
  upload(file, format) {
    return this.#post(this.url(`${SceneBuilderRoute.POINT_CLOUDS}${format}`), file, null);
  }

  /**
   * @param {string} identifier A resource identifier.
   * @returns {string} The URL the resource's file is served at.
   */
  assetUrl(identifier) {
    return this.url(`${SceneBuilderRoute.ASSETS}${this.#path(identifier)}`);
  }

  /**
   * @param {string} identifier A point cloud's resource identifier.
   * @returns {Promise<ArrayBuffer>} The point cloud's display sample.
   */
  async sample(identifier) {
    const url = this.url(`${SceneBuilderRoute.POINT_CLOUD_SAMPLES}${this.#path(identifier)}`);
    const answer = await this.#fetch(url);
    if (!answer.ok) throw await this.#failure(url, answer);
    return answer.arrayBuffer();
  }

  /**
   * @param {string} identifier A resource identifier.
   * @returns {string} The identifier with each segment escaped for a URL.
   */
  #path(identifier) {
    return identifier.split(PATH_SEPARATOR).map(encodeURIComponent).join(PATH_SEPARATOR);
  }

  /**
   * @param {string} url A route's URL.
   * @param {BodyInit} body The request's body.
   * @param {string|null} mediaType The body's media type, or null to let the browser name it.
   * @returns {Promise<Object>} The decoded answer.
   * @throws {RequestFailed} When the answer has an error status.
   */
  async #post(url, body, mediaType) {
    const headers = mediaType === null ? {} : { [HttpPart.CONTENT_TYPE]: mediaType };
    const answer = await this.#fetch(url, { method: HttpPart.POST, body, headers });
    if (!answer.ok) throw await this.#failure(url, answer);
    return answer.json();
  }

  /**
   * @param {string} url The requested URL.
   * @param {Response} answer An answer with an error status.
   * @returns {Promise<RequestFailed>} The failure, with the reason the server gave.
   */
  async #failure(url, answer) {
    const explained = (answer.headers.get(HttpPart.CONTENT_TYPE) ?? '').startsWith(HttpPart.JSON);
    const reason = explained ? (await answer.json())[ErrorKey.ERROR] : answer.statusText;
    return new RequestFailed(url, answer.status, reason);
  }
}
