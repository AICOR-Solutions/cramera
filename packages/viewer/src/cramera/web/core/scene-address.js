/**
 * How a page address names the bundle to show: `?scene=<name>`.
 */

/**
 * The query parameter naming the shown bundle.
 */
export const SCENE_PARAMETER = 'scene';

/**
 * The query parameter naming the live publisher the page follows.
 */
export const LIVE_PARAMETER = 'live';

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

/**
 * @param {string} href A page address.
 * @returns {string|null} The live publisher address it names, or null.
 */
export function liveAddressOf(href) {
  return new URL(href).searchParams.get(LIVE_PARAMETER);
}

/**
 * @param {string} href A page address.
 * @param {string} address A live publisher address.
 * @returns {URL} The address following that publisher instead of naming a bundle.
 */
export function withLive(href, address) {
  const url = new URL(href);
  url.searchParams.delete(SCENE_PARAMETER);
  url.searchParams.set(LIVE_PARAMETER, address);
  return url;
}
