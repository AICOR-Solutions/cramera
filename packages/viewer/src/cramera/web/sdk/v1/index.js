/**
 * The plugin SDK, version 1: the one module a plugin's browser page imports from cramera,
 * as `../../sdk/v1/index.js` from a page below `/plugins/<name>/`. It re-exports the
 * protocol's keys, the viewer's API client and the plan builder's 3D view and API
 * client, so a plugin never imports the viewer's or the plan builder's own files. Names
 * leave it only with a new major version, served under `/sdk/v2/`; a new minor version
 * only adds names.
 *
 * The plan builder's parts need the plan-builder plugin installed, as the Python facade
 * `cramera_plan_builder.plugin_api` does.
 */

export * from '../../protocol.js';
export { RequestFailed, ViewerApi } from '../../core/viewer-api.js';
export { Bounds } from '../../scene/bounds.js';
export { PlanBuilderApi, RequestRefused } from '../../plugins/plan-builder/builder/builder-api.js';
export { MarkerKind, PlanScene, PlanSceneListeners, SceneOverlay } from '../../plugins/plan-builder/builder/plan-scene.js';

/**
 * The SDK's version, `major.minor`; the plugin API version of the Python facade.
 */
export const SDK_VERSION = '1.0';
