/**
 * Showing in the 3D view what an answer is about: lighting up its links and free
 * objects, drawing its regions as boxes and moving the camera onto it.
 */

import { SceneHighlightKey, ViewerEvent } from '../protocol.js';

/**
 * @param {import('../core/event-bus.js').EventBus} bus The bus the 3D view listens on.
 * @param {Object|null} highlight What the scene shows of an answer; null clears what
 *   was shown.
 */
export function showAnswerInScene(bus, highlight) {
  bus.publish(ViewerEvent.ENTITY_HIGHLIGHTED, highlight?.[SceneHighlightKey.KEYS] ?? []);
  bus.publish(ViewerEvent.REGIONS_OUTLINED, highlight?.[SceneHighlightKey.REGIONS] ?? []);
  const framed = highlight?.[SceneHighlightKey.FRAMED] ?? [];
  if (framed.length) bus.publish(ViewerEvent.FOCUS_REQUESTED, framed);
}
