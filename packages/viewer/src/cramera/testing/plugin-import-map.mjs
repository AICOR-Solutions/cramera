/**
 * Registers the plugin resolve hook; passed to Node with `--import`.
 */

import { register } from 'node:module';

register('./plugin-import-map-hooks.mjs', import.meta.url);
