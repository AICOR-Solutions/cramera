/**
 * What perception reported for each detection of a run, as a person reads it: what was
 * asked, every object that came back with its colors, size and position, which one the
 * step used and why not the others, its warnings with the later detection used instead,
 * an empty answer as such, and one sentence per step telling why its detections failed.
 */

import { DomEvent } from './elements.js';
import {
  PerceptionReportKey,
  ReportedObjectKey,
  ReportedObjectVerdict,
  SurfaceDepthKey,
} from '../../../protocol.js';

/**
 * How a person reads each verdict on a reported object.
 */
export const VERDICT_TEXTS = Object.freeze({
  [ReportedObjectVerdict.ACCEPTED]: 'used',
  [ReportedObjectVerdict.TOO_FAR]: 'too far off',
  [ReportedObjectVerdict.NOT_CHOSEN]: 'ignored, another used',
  [ReportedObjectVerdict.WRONG_COLOR]: 'wrong colour',
  [ReportedObjectVerdict.WRONG_TYPE]: 'wrong type',
  [ReportedObjectVerdict.OUTSIDE_BOX]: 'outside the search',
});

/**
 * The classes the perception reports' elements carry.
 */
export const PerceptionViewClass = Object.freeze({
  REPORTS: 'perception-reports',
  REPORT: 'perception-report',
  ASKED: 'perception-asked',
  OBJECTS: 'perception-objects',
  OBJECT: 'perception-object',
  SWATCH: 'color-swatch',
  EMPTY: 'perception-empty',
  WARNING: 'perception-warning',
  INSTEAD: 'perception-instead',
  SENTENCE: 'run-step-perception',
});

/**
 * @param {number} metres A length.
 * @returns {string} It in centimetres, to a tenth.
 */
const cm = (metres) => `${Math.round(metres * 1000) / 10}`;

/**
 * @param {Array<number>} position A position in metres.
 * @returns {string} It as a person reads it, in metres to the centimetre.
 */
export const at = (position) => `(${position.map((value) => value.toFixed(2)).join(', ')}) m`;

/**
 * Where a step expects its objects until it is planned again.
 */
const VALIDATED_SPOT = 'planned';

/**
 * Where a step planned again expects its objects.
 */
const LAST_SEEN_SPOT = 'last seen';

/**
 * @param {Object} report A `PerceptionReport`.
 * @returns {string} Where the step expected the object, which distances are measured
 *   from: where the plan was validated, or, for a step planned again since, where the
 *   object was last seen.
 */
export const spotText = (report) => (report[PerceptionReportKey.VALIDATED] ? LAST_SEEN_SPOT : VALIDATED_SPOT);

/**
 * @param {string} summary A report's summary.
 * @returns {string} It without its closing full stop.
 */
const clause = (summary) => summary.replace(/\.$/, '');

/**
 * @param {Array<Object>} reports The `PerceptionReport`s of one step, in order.
 * @returns {string|null} Why its detections came to what they did, in one sentence:
 *   each report's summary, a repeated one counted, joined in order; null for none.
 */
export function perceptionSentence(reports) {
  const parts = [];
  for (const report of reports) {
    const summary = clause(report[PerceptionReportKey.SUMMARY] ?? '');
    const last = parts.at(-1);
    if (last && last.summary === summary) last.times += 1;
    else parts.push({ summary, times: 1 });
  }
  if (parts.length === 0) return null;
  const said = parts.map((part, index) => {
    const text = index === 0 ? part.summary : part.summary.charAt(0).toLowerCase() + part.summary.slice(1);
    return part.times > 1 ? `${text} (${part.times} times)` : text;
  });
  return `${said.join('; then ')}.`;
}

/**
 * @param {Object} report A `PerceptionReport`.
 * @returns {string} What it asked, as a person reads it: around where the step expected
 *   the object, how far it looked and how far the step lets the object lie, both
 *   measured from there.
 */
export function askedText(report) {
  const box = report[PerceptionReportKey.BOX];
  const [reachX, reachY] = box ? [cm((box[1][0] - box[0][0]) / 2), cm((box[1][1] - box[0][1]) / 2)] : ['', ''];
  const reach = reachX === reachY ? `${reachX} cm` : `${reachX} × ${reachY} cm`;
  const grounded = report[PerceptionReportKey.GROUNDED];
  const tolerance = cm(report[PerceptionReportKey.TOLERANCE] ?? 0);
  const allowed = tolerance === reach.replace(' cm', '') ? '' : `, ${tolerance} cm allowed`;
  if (report[PerceptionReportKey.TABLE_WIDE]) return 'Searched the whole table.';
  if (grounded) return `Searched within ${reach} of ${at(grounded)} (${spotText(report)})${allowed}.`;
  return `Searched ${at(box[0])} to ${at(box[1])}.`;
}

/**
 * The verdicts of an object the step took.
 */
const TAKEN = new Set([ReportedObjectVerdict.ACCEPTED, ReportedObjectVerdict.TOO_FAR]);

/**
 * @param {Object} seen A `ReportedObject`.
 * @returns {string} How far an object the step took was reported inside the surface it
 *   stands on, which it was raised onto; empty for any other.
 */
export function insideSurfaceText(seen) {
  const inside = seen[ReportedObjectKey.INSIDE_SURFACE];
  if (!inside || !TAKEN.has(seen[ReportedObjectKey.VERDICT])) return '';
  const mm = (metres) => `${Math.max(1, Math.round(metres * 1000))} mm`;
  return `; ${mm(inside[SurfaceDepthKey.DEPTH])} inside the ${inside[SurfaceDepthKey.SURFACE].replaceAll('_', ' ')}, raised`;
}

/**
 * @param {Object} seen A `ReportedObject`.
 * @param {Object} report The `PerceptionReport` it came back in.
 * @returns {string} That it was measured clearly unlike the object looked for, which
 *   hints at a perception error; empty for any other.
 */
export function sizeText(seen, report) {
  const expected = report[PerceptionReportKey.EXPECTED_SIZE];
  if (!seen[ReportedObjectKey.SIZE_DIFFERS] || !expected) return '';
  return `; size off (expected ${expected.map(cm).join(' × ')} cm)`;
}

/**
 * @param {Object} seen A `ReportedObject`.
 * @param {Object} report The `PerceptionReport` it came back in, which says where its
 *   distance is measured from.
 * @returns {string} It as a person reads it: colours, size, position, distance, verdict
 *   how far inside its surface it was reported and whether its size hints at a
 *   perception error; the type the perception reported is left out, a class name no
 *   person reads.
 */
export function objectText(seen, report = {}) {
  const colors = (seen[ReportedObjectKey.COLORS] ?? []).join(' and ') || 'no colour';
  const size = seen[ReportedObjectKey.SIZE];
  const extent = size ? `${size.map(cm).join(' × ')} cm` : 'size unknown';
  const distance = seen[ReportedObjectKey.DISTANCE];
  const off = report[PerceptionReportKey.VALIDATED] ? ` from ${LAST_SEEN_SPOT}` : ' off';
  const away = distance === null || distance === undefined ? '' : `, ${cm(distance)} cm${off}`;
  return `${colors}, ${extent}, ${at(seen[ReportedObjectKey.POSITION])}${away}: ${VERDICT_TEXTS[seen[ReportedObjectKey.VERDICT]] ?? seen[ReportedObjectKey.VERDICT]}${insideSurfaceText(seen)}${sizeText(seen, report)}`;
}

/**
 * @param {Object} report A `PerceptionReport`.
 * @returns {boolean} Whether the step used an object it reported.
 */
export const isUsed = (report) => (report[PerceptionReportKey.OBJECTS] ?? []).some((seen) => seen[ReportedObjectKey.VERDICT] === ReportedObjectVerdict.ACCEPTED);

/**
 * @param {Object} report A `PerceptionReport`.
 * @returns {string} The report as one log line: its summary and its warnings.
 */
export const reportLine = (report) => [report[PerceptionReportKey.SUMMARY], ...(report[PerceptionReportKey.WARNINGS] ?? []).map((warning) => `Warning: ${warning}`)].join(' ');

/**
 * Shows the perception reports of a run.
 */
export class PerceptionReportsView {
  /**
   * Builds the view's elements.
   * @type {import('./elements.js').Elements}
   */
  #elements;

  /**
   * Whether the person opened or closed each report, by its position and step, kept
   * across renders; a report not toggled shows its default.
   * @type {Map<string, boolean>}
   */
  #opened = new Map();

  /**
   * @param {import('./elements.js').Elements} elements Builds the view's elements.
   */
  constructor(elements) {
    this.#elements = elements;
  }

  /**
   * @param {Array<{name: string, report: Object}>} reports Every report of the run with
   *   the name of its step, in order.
   * @returns {Array<HTMLElement>} One block per report, open as the person left it,
   *   else the latest open, or a note that none came yet.
   */
  render(reports) {
    const elements = this.#elements;
    if (reports.length === 0) this.#opened.clear();
    if (reports.length === 0) return [elements.create('p', 'empty', 'No perception reported yet.')];
    return reports.map(({ name, report }, index) => {
      const block = elements.create('details', PerceptionViewClass.REPORT);
      const key = `${index}:${name}`;
      block.open = this.#opened.get(key) ?? index === reports.length - 1;
      block.dataset.answered = String(report[PerceptionReportKey.ANSWERED] !== false);
      const warnings = report[PerceptionReportKey.WARNINGS] ?? [];
      block.dataset.warning = String(warnings.length > 0);
      block.dataset.used = String(isUsed(report));
      const summary = elements.create('summary', '', `${name}: ${report[PerceptionReportKey.SUMMARY]}`);
      // a click on the summary toggles the block after this listener ran
      elements.listen(summary, DomEvent.CLICK, () => this.#opened.set(key, !block.open));
      block.append(summary, ...warnings.map((warning) => elements.create('p', PerceptionViewClass.WARNING, warning)));
      const instead = warnings.length > 0 && !isUsed(report) ? reports.slice(index + 1).find((later) => later.name === name && isUsed(later.report)) : null;
      if (instead) block.append(elements.create('p', PerceptionViewClass.INSTEAD, `Used instead: ${instead.report[PerceptionReportKey.SUMMARY]}`));
      block.append(elements.create('p', PerceptionViewClass.ASKED, askedText(report)));
      const objects = report[PerceptionReportKey.OBJECTS] ?? [];
      if (report[PerceptionReportKey.ANSWERED] === false) {
        block.append(elements.create('p', PerceptionViewClass.EMPTY, 'No answer came back.'));
      } else if (objects.length === 0) {
        block.append(elements.create('p', PerceptionViewClass.EMPTY, 'Nothing reported.'));
      } else {
        const list = elements.create('ul', PerceptionViewClass.OBJECTS);
        for (const seen of objects) {
          const item = elements.create('li', PerceptionViewClass.OBJECT);
          item.dataset.verdict = seen[ReportedObjectKey.VERDICT];
          item.dataset.sizeDiffers = String(seen[ReportedObjectKey.SIZE_DIFFERS] === true);
          const swatch = elements.create('span', PerceptionViewClass.SWATCH);
          swatch.style.background = (seen[ReportedObjectKey.COLORS] ?? [])[0] ?? 'transparent';
          item.append(swatch, elements.create('span', '', objectText(seen, report)));
          list.append(item);
        }
        block.append(list);
      }
      return block;
    });
  }
}
