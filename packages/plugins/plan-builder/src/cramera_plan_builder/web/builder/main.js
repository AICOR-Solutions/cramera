/**
 * Starts the builder page in the browser.
 */

import { PageState, PageStateAttribute } from '../../../protocol.js';
import { ViewerApi } from '../../../core/viewer-api.js';
import { PlanBuilderApi } from './builder-api.js';
import { BuilderEnvironment, BuilderPage } from './builder-page.js';
import { LiveClient } from './live-client.js';
import { PlanScene } from './plan-scene.js';

/**
 * The viewer's page, relative to the builder page.
 */
const VIEWER_PAGE = '../../';

/**
 * The element the page is built into.
 */
const ROOT_IDENTIFIER = 'plan-builder';

const viewer = new URL(VIEWER_PAGE, window.location.href).href;
const fetch = window.fetch.bind(window);
const api = new PlanBuilderApi(fetch, viewer);
const viewerApi = new ViewerApi(fetch, viewer);
const environment = new BuilderEnvironment({
  document,
  api,
  live: (base) => new LiveClient(fetch, base),
  storage: window.localStorage,
  query: new URLSearchParams(window.location.search),
  createScene: PlanScene.isAvailable(document) ? (container, listeners) => new PlanScene(container, viewerApi, (model) => api.objectUrl(model), listeners) : null,
  timer: { repeat: (callback, interval) => window.setInterval(callback, interval), cancel: (handle) => window.clearInterval(handle) },
});
const root = document.getElementById(ROOT_IDENTIFIER);
const page = new BuilderPage(root, environment);
window.addEventListener('pagehide', () => page.dispose());
page.start().catch((error) => {
  document.documentElement.dataset[PageStateAttribute.STATE] = PageState.FAILED;
  root.append(Object.assign(document.createElement('p'), { className: 'status-line', textContent: error.message }));
});
