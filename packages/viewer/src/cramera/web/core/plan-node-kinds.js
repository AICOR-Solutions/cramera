/**
 * The kinds of plan node as the protocol names them, read from recordings of any age:
 * earlier recordings stored the planner's class names, which are translated once here.
 */

import { LegacyPlanNodeKind, PlanNodeKind } from '../protocol.js';

/**
 * The kind each class name of earlier recordings stands for.
 */
const LEGACY_KINDS = new Map(Object.entries(LegacyPlanNodeKind).map(([member, className]) => [className, PlanNodeKind[member]]));

/**
 * @param {string} kind A plan node's kind as a recording or the live plan names it.
 * @returns {string} The `PlanNodeKind` value it stands for; an unknown class name is
 *   `PlanNodeKind.OTHER`.
 */
export function planNodeKindOf(kind) {
  if (Object.values(PlanNodeKind).includes(kind)) return kind;
  return LEGACY_KINDS.get(kind) ?? PlanNodeKind.OTHER;
}
