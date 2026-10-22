/**
 * Resolves bare module specifiers in Node the way the browser does: from the import
 * map inside the viewer's index.html, so tests and page share one mapping.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

/**
 * The viewer's web directory.
 */
const WEB = new URL('../../../src/cramera/web/', import.meta.url);

/**
 * The import map of index.html, with addresses resolved against the web directory.
 */
const IMPORTS = (() => {
  const page = readFileSync(fileURLToPath(new URL('index.html', WEB)), 'utf8');
  const map = JSON.parse(page.match(/<script type="importmap">([\s\S]*?)<\/script>/)[1]);
  return Object.entries(map.imports).map(([specifier, address]) => [specifier, new URL(address, WEB).href]);
})();

/**
 * Node's resolve hook: maps bare specifiers through the import map.
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
  return nextResolve(specifier, context);
}

