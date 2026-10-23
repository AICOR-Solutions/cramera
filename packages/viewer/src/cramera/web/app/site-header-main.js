/**
 * Puts the viewer's top bar into a plugin's page: the page marks an element with
 * `data-site-header` and names itself in its `data-page`.
 */

import { ViewerApi } from '../core/viewer-api.js';
import { SiteHeader, ThemeSetting, localStorageOf } from './site-header.js';

/**
 * The viewer's root, relative to this module.
 */
const VIEWER_ROOT = new URL('../', import.meta.url).href;

const theme = new ThemeSetting(document.documentElement, localStorageOf(window));
theme.apply();
const root = document.querySelector('[data-site-header]');
if (root) {
  const api = new ViewerApi((url, options) => fetch(url, options), VIEWER_ROOT);
  const header = new SiteHeader(root, (route) => api.url(route), theme, root.dataset.page);
  api.info().then((info) => header.show(info), () => header.show({}));
}
