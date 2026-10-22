/**
 * Resolves module specifiers in Node the way the browser does when the viewer serves
 * the laboratory plugin: the plugin's web directory lies at `/plugins/laboratory/`, so a
 * relative import leaving it, such as `../../protocol.js`, reaches the viewer's web
 * directory; bare specifiers resolve through the import map of the viewer's page.
 * Tests reach the viewer's modules through the prefix `cramera-viewer/`.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';

/**
 * The environment variable naming the viewer's web directory.
 */
const VIEWER_WEB_VARIABLE = 'CRAMERA_VIEWER_WEB';

/**
 * The prefix tests import the viewer's modules by.
 */
const VIEWER_PREFIX = 'cramera-viewer/';

/**
 * The viewer's web directory.
 */
const VIEWER_WEB = pathToFileURL(`${process.env[VIEWER_WEB_VARIABLE]}/`).href;

/**
 * The plugin's web directory, served at `/plugins/laboratory/`.
 */
const PLUGIN_WEB = new URL('../../../src/cramera_laboratory/web/', import.meta.url).href;

/**
 * The directory standing for the viewer's root: two levels above the laboratory plugin's web directory.
 */
const SERVED_ROOT = new URL('../../', PLUGIN_WEB).href;

/**
 * The import map of the viewer's page, with addresses resolved against its web directory.
 */
const IMPORTS = (() => {
  const page = readFileSync(fileURLToPath(new URL('index.html', VIEWER_WEB)), 'utf8');
  const map = JSON.parse(page.match(/<script type="importmap">([\s\S]*?)<\/script>/)[1]);
  return [[VIEWER_PREFIX, VIEWER_WEB], ...Object.entries(map.imports).map(([specifier, address]) => [specifier, new URL(address, VIEWER_WEB).href])];
})();

/**
 * Node's resolve hook.
 * @param {string} specifier The imported specifier.
 * @param {Object} context Node's resolution context.
 * @param {Function} nextResolve Node's own resolution.
 * @returns {Promise<Object>} The resolution.
 */
export async function resolve(specifier, context, nextResolve) {
  for (const [prefix, address] of IMPORTS) {
    if (prefix.endsWith('/') ? specifier.startsWith(prefix) : specifier === prefix) {
      return nextResolve(prefix.endsWith('/') ? address + specifier.slice(prefix.length) : address, context);
    }
  }
  if (specifier.startsWith('.') && context.parentURL?.startsWith(PLUGIN_WEB)) {
    const address = new URL(specifier, context.parentURL).href;
    if (address.startsWith(SERVED_ROOT) && !address.startsWith(PLUGIN_WEB)) {
      return nextResolve(VIEWER_WEB + address.slice(SERVED_ROOT.length), context);
    }
  }
  return nextResolve(specifier, context);
}
