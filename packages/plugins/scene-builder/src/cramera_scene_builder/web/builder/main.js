/**
 * Starts the builder page in the browser.
 */

import { BuilderApi } from './builder-api.js';
import { BuilderEnvironment, BuilderPage } from './builder-page.js';
import { DraftView } from './draft-view.js';
import { ResourceLoading } from './resource-loading.js';

/**
 * The viewer's page, relative to the builder page.
 */
const VIEWER_PAGE = '../../';

/**
 * How long an exported file's address stays valid after the download starts, in milliseconds.
 */
const DOWNLOAD_ADDRESS_LIFETIME = 0;

/**
 * The ways into a page that return to it rather than open it anew: a reload, and the
 * browser's back and forward buttons.
 */
const RETURNING_NAVIGATIONS = Object.freeze(['reload', 'back_forward']);

const viewer = new URL(VIEWER_PAGE, window.location.href).href;
const api = new BuilderApi(window.fetch.bind(window), viewer);
const environment = new BuilderEnvironment({
  document,
  api,
  storage: window.sessionStorage,
  query: new URLSearchParams(window.location.search),
  returning: RETURNING_NAVIGATIONS.includes(performance.getEntriesByType('navigation')[0]?.type),
  viewerUrl: viewer,
  createView: DraftView.isAvailable(document)
    ? (container, listeners) => new DraftView(container, new ResourceLoading(api, (missing) => listeners.onError(missing)), listeners)
    : null,
  download: (blob, name) => {
    const address = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = address;
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(address), DOWNLOAD_ADDRESS_LIFETIME);
  },
});
const page = new BuilderPage(document.getElementById('scene-builder'), environment);
window.addEventListener('pagehide', () => page.dispose());
page.start().catch((error) => {
  document.documentElement.dataset.builderState = 'failed';
  document.getElementById('scene-builder').append(Object.assign(document.createElement('p'), { className: 'status-line', textContent: error.message }));
});
