/**
 * Starts the cable lab page in the browser.
 */

import { PageStatus } from '../../../core/page-status.js';
import { CableLabClient } from './cable-client.js';
import { CableView } from './cable-view.js';
import { ElementId, LabPage } from './lab-page.js';

/**
 * The viewer's address, relative to the cable lab page.
 */
const VIEWER_PAGE = '../../';

const viewer = new URL(VIEWER_PAGE, window.location.href).href;
const client = new CableLabClient(window.fetch.bind(window), viewer);
const container = document.getElementById(ElementId.VIEWPORT);
const canvas = document.createElement('canvas');
const view = canvas.getContext('webgl2') ? new CableView(container) : null;
const status = new PageStatus(document.documentElement, document.getElementById(ElementId.STATUS));
const page = new LabPage(document, client, view, window, status);
window.addEventListener('pagehide', () => {
  page.close();
  view?.dispose();
});
page.poll();
