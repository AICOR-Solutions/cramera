/**
 * Starts the viewer in the page.
 */

import { PageStatus } from '../core/page-status.js';
import { ViewerApi } from '../core/viewer-api.js';
import { Application, PageElements } from './application.js';

const elements = new PageElements(document);
const application = new Application(
  elements,
  new ViewerApi((url, options) => fetch(url, options), document.baseURI),
  window.location,
  window.history,
);
application.start((url) => import(url)).catch((error) => {
  new PageStatus(document.documentElement, elements.statusLine).failed(`The viewer could not start: ${error.message}`);
});
