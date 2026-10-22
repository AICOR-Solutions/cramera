/**
 * Registers the import-map resolve hook; passed to Node with `--import`.
 */

import { register } from 'node:module';

register('./import-map-hooks.mjs', import.meta.url);
