/**
 * Starts the status page.
 */

import { ViewerApi } from '../core/viewer-api.js';
import { StatusPage } from './status.js';

/**
 * @param {string} url A JSON file that may be absent.
 * @returns {Promise<Object|null>} Its content, or null when absent.
 */
async function optionalJson(url) {
  const answer = await fetch(url);
  return answer.ok ? answer.json() : null;
}

new StatusPage(document, new ViewerApi((url, options) => fetch(url, options), document.baseURI)).show(optionalJson);
