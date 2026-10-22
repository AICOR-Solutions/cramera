/**
 * Registers the resolve hook that lets the plugin's modules run in Node as the viewer
 * serves them; passed to Node with `--import`.
 */

import { register } from 'node:module';

register('./import-map-hooks.mjs', import.meta.url);
