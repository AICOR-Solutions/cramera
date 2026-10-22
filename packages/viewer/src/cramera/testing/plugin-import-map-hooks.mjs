/**
 * Resolves module specifiers in Node the way the browser does when the viewer serves a
 * plugin: the plugin's web directory lies at `/plugins/<name>/`, so a relative import
 * leaving it, such as `../../protocol.js`, reaches the viewer's web directory; bare
 * specifiers resolve through the import map of the viewer's page. Tests reach the
 * viewer's modules through `cramera-viewer/` and this directory's helpers through
 * `cramera-testing/`.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';

/**
 * The environment variables naming the viewer's and the plugin's web directories.
 */
const Directory = Object.freeze({ VIEWER: 'CRAMERA_VIEWER_WEB', PLUGIN: 'CRAMERA_PLUGIN_WEB' });

/**
 * The prefixes tests import the viewer's modules and these helpers by.
 */
const Prefix = Object.freeze({ VIEWER: 'cramera-viewer/', TESTING: 'cramera-testing/' });

/**
 * @param {string} variable An environment variable naming a directory.
 * @returns {string} The directory's file URL, ending in `/`.
 */
function directoryUrl(variable) {
  return pathToFileURL(`${process.env[variable]}/`).href;
}

const VIEWER_WEB = directoryUrl(Directory.VIEWER);
const PLUGIN_WEB = directoryUrl(Directory.PLUGIN);

/**
 * The directory standing for the viewer's root: two levels above the plugin's web directory.
 */
const SERVED_ROOT = new URL('../../', PLUGIN_WEB).href;

/**
 * Prefixes and their addresses: the test prefixes, then the viewer page's import map.
 */
const IMPORTS = (() => {
  const page = readFileSync(fileURLToPath(new URL('index.html', VIEWER_WEB)), 'utf8');
  const map = JSON.parse(page.match(/<script type="importmap">([\s\S]*?)<\/script>/)[1]);
  return [
    [Prefix.VIEWER, VIEWER_WEB],
    [Prefix.TESTING, new URL('./', import.meta.url).href],
    ...Object.entries(map.imports).map(([specifier, address]) => [specifier, new URL(address, VIEWER_WEB).href]),
  ];
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
