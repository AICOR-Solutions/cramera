/**
 * How a page address names the bundle to show: `?scene=<name>`.
 */

/**
 * The query parameter naming the shown bundle.
 */
export const SCENE_PARAMETER = 'scene';

// %% addresses

/**
 * @param {string} href A page address.
 * @returns {string|null} The bundle it names, or null.
 */
export function sceneOf(href) {
  return new URL(href).searchParams.get(SCENE_PARAMETER);
}

/**
 * @param {string} href A page address.
 * @param {string} name A bundle name.
 * @returns {URL} The address naming that bundle.
 */
export function withScene(href, name) {
  const url = new URL(href);
  url.searchParams.set(SCENE_PARAMETER, name);
  return url;
}
