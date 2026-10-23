/**
 * Starts the viewer in the page.
 */

import { PageStatus } from '../core/page-status.js';
import { ViewerApi } from '../core/viewer-api.js';
import { Application, PageElements } from './application.js';
import { localStorageOf } from './site-header.js';

const elements = new PageElements(document);
const application = new Application(
  elements,
  new ViewerApi((url, options) => fetch(url, options), document.baseURI),
  window.location,
  window.history,
  (url, options) => fetch(url, options),
  window,
  localStorageOf(window),
);
application.start((url) => import(url)).catch((error) => {
  const message = `The viewer could not start: ${error.message}`;
  new PageStatus(document.documentElement, elements.statusLine).failed(message);
  elements.stageMessage.textContent = message;
  elements.stageMessage.hidden = false;
});
