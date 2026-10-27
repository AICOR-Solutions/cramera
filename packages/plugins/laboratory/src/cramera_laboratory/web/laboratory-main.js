/** Starts the dedicated physical lab page. */

import { ViewerApi } from '../../core/viewer-api.js';
import { LaboratoryPage, viewerRootOf } from './laboratory-page.js';

const fetch = (url, options) => window.fetch(url, options);
const page = new LaboratoryPage(document.getElementById('medical-lab'), {
  api: new ViewerApi(fetch, viewerRootOf(window.location.href)),
  location: window.location,
  history: window.history,
  fetch,
  timers: window,
});
window.addEventListener('pagehide', () => page.dispose());
page.start().catch((error) => page.fail(error.reason ?? error.message));
