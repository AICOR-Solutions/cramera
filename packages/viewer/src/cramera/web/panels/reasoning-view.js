/**
 * How a backend reasoned to its answers, drawn: what perception saw and how well each
 * outline fits, the contacts a working memory tested, the cascade of rules walked to
 * the one that fires, and the distribution a probabilistic model was sampled from.
 * Each part fades in after the one before it over a given span.
 */

import {
  ContactReadingKey,
  ContactReasoningKey,
  KnowledgeSource,
  LayoutRegionKey,
  OutcomeProbabilityKey,
  OutlineFitKey,
  PerceptionReasoningKey,
  ReasoningImageKey,
  ReasoningKey,
  RegionLayoutKey,
  RuleReadingKey,
  RuleReasoningKey,
  SamplingReasoningKey,
} from '../protocol.js';
import { element, svgElement } from './elements.js';

/**
 * What each kind of knowledge is shown as: its symbol and what a backend of it reads.
 */
export const KNOWLEDGE_SOURCES = Object.freeze({
  [KnowledgeSource.PERCEPTION]: Object.freeze({ symbol: '◉', note: 'what the robot’s sensors saw' }),
  [KnowledgeSource.WORKING_MEMORY]: Object.freeze({ symbol: '◈', note: 'the digital twin, read off its geometry' }),
  [KnowledgeSource.RULES]: Object.freeze({ symbol: '⋔', note: 'rules stated about the task' }),
  [KnowledgeSource.PROBABILISTIC]: Object.freeze({ symbol: '∿', note: 'a probabilistic model, sampled' }),
});

/**
 * How many pixels one metre of a layout takes in its drawing.
 */
export const LAYOUT_SCALE = 900;

/**
 * How many pixels one metre of a contact's boxes takes in its drawing.
 */
export const CONTACT_SCALE = 600;

/**
 * @param {string} source A `KnowledgeSource` value.
 * @returns {{symbol: string, note: string}} How the kind of knowledge is shown.
 */
export function knowledgeSource(source) {
  return KNOWLEDGE_SOURCES[source] ?? KNOWLEDGE_SOURCES[KnowledgeSource.WORKING_MEMORY];
}

/**
 * @param {HTMLElement} shown An element that fades in.
 * @param {number} milliseconds How long after the drawing appears it fades in.
 * @returns {HTMLElement} The element.
 */
function fadingIn(shown, milliseconds) {
  shown.className = `${shown.className} fades-in`.trim();
  shown.style.animationDelay = `${Math.round(milliseconds)}ms`;
  return shown;
}

/**
 * @param {number} share A share from 0 to 1.
 * @returns {string} It as a whole percentage.
 */
function percentage(share) {
  return `${Math.round(share * 100)}%`;
}

// %% each kind of reasoning

/**
 * @param {Document} document The page.
 * @param {Object} reasoning A perception backend's reasoning.
 * @param {number} span Over how many milliseconds the drawing appears.
 * @returns {Array<HTMLElement>} The images seen and how well each candidate fits.
 */
function perceptionParts(document, reasoning, span) {
  const images = (reasoning[PerceptionReasoningKey.IMAGES] ?? []).map((seen, index) => {
    const picture = document.createElement('img');
    picture.src = seen[ReasoningImageKey.IMAGE];
    picture.alt = seen[ReasoningImageKey.CAPTION];
    return fadingIn(element(document, 'figure', 'reasoning-image', null, [picture, element(document, 'figcaption', '', seen[ReasoningImageKey.CAPTION])]), span * 0.25 * index);
  });
  const fits = (reasoning[PerceptionReasoningKey.CANDIDATES] ?? []).map((candidate, index) => {
    const selected = candidate[OutlineFitKey.SELECTED];
    const bar = element(document, 'span', 'reasoning-bar');
    bar.style.width = percentage(candidate[OutlineFitKey.FIT]);
    const row = element(document, 'li', selected ? 'answers' : 'rejected', null, [
      element(document, 'span', 'tick', selected ? '✓' : '✗'),
      element(document, 'strong', '', candidate[OutlineFitKey.NAME]),
      element(document, 'span', 'muted', candidate[OutlineFitKey.KIND]),
      element(document, 'span', 'reasoning-meter', null, [bar]),
      element(document, 'span', 'muted', `outline fits ${percentage(candidate[OutlineFitKey.FIT])}`),
    ]);
    return fadingIn(row, span * (0.45 + index * 0.08));
  });
  return [element(document, 'div', 'reasoning-images', null, images), element(document, 'ul', 'reasoning-rows', null, fits)];
}

/**
 * @param {Document} document The page.
 * @param {Object} reading A contact a working memory tested, with its box's size.
 * @returns {Element} The box dropped onto its support, seen from the side.
 */
function contactDrawing(document, reading) {
  const [depth, , height] = reading[ContactReadingKey.SIZE];
  const width = depth * CONTACT_SCALE;
  const tall = height * CONTACT_SCALE;
  const gap = (reading[ContactReadingKey.GAP] ?? 0) * CONTACT_SCALE;
  const slab = width * 2.6;
  return svgElement(document, 'svg', { viewBox: `${-slab / 2} ${-tall - gap - 4} ${slab} ${tall + gap + 14}`, class: 'contact-drawing' }, [
    svgElement(document, 'rect', { x: -slab / 2, y: 0, width: slab, height: 8, class: 'support' }),
    svgElement(document, 'rect', { x: -width / 2, y: -tall - gap, width, height: tall, class: reading[ContactReadingKey.SELECTED] ? 'answers' : 'rejected' }),
  ]);
}

/**
 * @param {Document} document The page.
 * @param {Object} reasoning A working-memory backend's reasoning.
 * @param {number} span Over how many milliseconds the drawing appears.
 * @returns {Array<HTMLElement>} The condition tested and each thing tested against it.
 */
function contactParts(document, reasoning, span) {
  const parts = [];
  const condition = reasoning[ContactReasoningKey.CONDITION];
  if (condition) parts.push(element(document, 'p', 'reasoning-condition', `where ${condition}`));
  const readings = (reasoning[ContactReasoningKey.READINGS] ?? []).map((reading, index) => {
    const selected = reading[ContactReadingKey.SELECTED];
    const support = reading[ContactReadingKey.SUPPORT];
    const said = support ? `rests on ${support} · gap ${(reading[ContactReadingKey.GAP] * 1000).toFixed(1)} mm` : reading[ContactReadingKey.RELATION];
    const row = element(document, 'li', selected ? 'answers' : 'rejected', null, [
      element(document, 'span', 'tick', selected ? '✓' : '✗'),
      element(document, 'strong', '', reading[ContactReadingKey.NAME]),
      element(document, 'span', 'muted', said),
    ]);
    if (reading[ContactReadingKey.SIZE]) row.append(contactDrawing(document, reading));
    return fadingIn(row, span * (0.1 + index * 0.15));
  });
  parts.push(element(document, 'ul', 'reasoning-rows', null, readings));
  return parts;
}

/**
 * @param {Document} document The page.
 * @param {Object} layout A layout of regions seen from above.
 * @returns {Element} The layout with its regions, those concluded marked.
 */
function layoutDrawing(document, layout) {
  const width = layout[RegionLayoutKey.WIDTH];
  const length = layout[RegionLayoutKey.LENGTH];
  // the layout's y runs left to right and its x bottom to top, as seen from its front
  const drawn = ([x, y]) => `${((y + length / 2) * LAYOUT_SCALE).toFixed(1)},${((width / 2 - x) * LAYOUT_SCALE).toFixed(1)}`;
  const regions = (layout[RegionLayoutKey.REGIONS] ?? []).map((region) =>
    svgElement(document, 'polygon', {
      points: region[LayoutRegionKey.OUTLINE].map(drawn).join(' '),
      class: region[LayoutRegionKey.CONCLUDED] ? 'concluded' : 'region',
    }),
  );
  return svgElement(document, 'svg', { viewBox: `-10 -10 ${(length * LAYOUT_SCALE + 20).toFixed(0)} ${(width * LAYOUT_SCALE + 20).toFixed(0)}`, class: 'layout-drawing' }, [
    svgElement(document, 'rect', { x: 0, y: 0, width: (length * LAYOUT_SCALE).toFixed(1), height: (width * LAYOUT_SCALE).toFixed(1), rx: 6, class: 'layout' }),
    ...regions,
  ]);
}

/**
 * @param {Object} rule A rule of a cascade.
 * @returns {string} How far the backend got with it: `fired`, `tried` or `untried`.
 */
export function ruleState(rule) {
  if (rule[RuleReadingKey.FIRED]) return 'fired';
  return rule[RuleReadingKey.TRIED] ? 'tried' : 'untried';
}

/**
 * @param {Document} document The page.
 * @param {Object} reasoning A rules backend's reasoning.
 * @param {number} span Over how many milliseconds the drawing appears.
 * @returns {Array<HTMLElement>} The case, the cascade walked and the layout concluded on.
 */
function ruleParts(document, reasoning, span) {
  const rules = reasoning[RuleReasoningKey.RULES] ?? [];
  const fired = rules.findIndex((rule) => rule[RuleReadingKey.FIRED]);
  const step = (span * 0.5) / Math.max(1, fired < 0 ? rules.length : fired + 1);
  const cascade = rules.map((rule, index) =>
    fadingIn(
      element(document, 'li', `rule ${ruleState(rule)}`, null, [
        element(document, 'span', 'rule-condition', `${index ? 'else if' : 'if'} ${rule[RuleReadingKey.CONDITION]}`),
        element(document, 'span', 'rule-conclusion', `then ${rule[RuleReadingKey.CONCLUSION]}`),
      ]),
      step * index,
    ),
  );
  const parts = [
    element(document, 'p', 'reasoning-case', `case: ${reasoning[RuleReasoningKey.CASE]} · kind ${reasoning[RuleReasoningKey.CASE_KIND]}`),
    element(document, 'ol', 'rule-cascade', null, cascade),
  ];
  const layout = reasoning[RuleReasoningKey.LAYOUT];
  if (layout) parts.push(fadingIn(element(document, 'figure', 'reasoning-layout', null, [layoutDrawing(document, layout)]), span * 0.5));
  return parts;
}

/**
 * @param {Object} reasoning A probabilistic backend's reasoning.
 * @param {Array<string>} answers The backend's answers, most likely first.
 * @returns {Array<string>} The outcomes, most likely first: the answers where there are
 *   any, else the outcomes by their probability.
 */
export function rankedOutcomes(reasoning, answers) {
  if (answers.length) return answers;
  return [...(reasoning[SamplingReasoningKey.PRIOR] ?? [])]
    .sort((first, second) => second[OutcomeProbabilityKey.PROBABILITY] - first[OutcomeProbabilityKey.PROBABILITY])
    .map((outcome) => outcome[OutcomeProbabilityKey.OUTCOME]);
}

/**
 * @param {Document} document The page.
 * @param {Object} reasoning A probabilistic backend's reasoning.
 * @param {number} span Over how many milliseconds the drawing appears.
 * @param {Array<string>} answers The backend's answers.
 * @returns {Array<HTMLElement>} The distribution with how often each outcome was drawn,
 *   and the outcomes ranked.
 */
function samplingParts(document, reasoning, span, answers) {
  const prior = reasoning[SamplingReasoningKey.PRIOR] ?? [];
  const samples = reasoning[SamplingReasoningKey.SAMPLES] ?? [];
  const highest = Math.max(...prior.map((outcome) => outcome[OutcomeProbabilityKey.PROBABILITY]), Number.EPSILON);
  const ranked = rankedOutcomes(reasoning, answers);
  const columns = prior.map((outcome) => {
    const name = outcome[OutcomeProbabilityKey.OUTCOME];
    const probability = outcome[OutcomeProbabilityKey.PROBABILITY];
    const bar = element(document, 'span', 'reasoning-bar');
    bar.style.height = percentage(probability / highest);
    return element(document, 'li', name === ranked[0] ? 'outcome most-likely' : 'outcome', null, [
      element(document, 'span', 'outcome-bar', null, [bar]),
      element(document, 'span', 'muted', `P = ${probability.toFixed(2)}`),
      element(document, 'strong', '', name),
      fadingIn(element(document, 'span', 'muted', `${samples.filter((sample) => sample === name).length} drawn`), span * 0.72),
    ]);
  });
  return [
    element(document, 'p', 'muted', `${samples.length} samples drawn for ${reasoning[SamplingReasoningKey.SUBJECT]}`),
    element(document, 'ul', 'outcomes', null, columns),
    fadingIn(element(document, 'p', 'reasoning-ranked', `most likely first: ${ranked.join(' › ')}`), span * 0.8),
  ];
}

// %% drawing

/**
 * How the reasoning of each kind of knowledge is drawn: called with the page, the
 * reasoning, the span it appears over and the backend's answers.
 */
const DRAWN_PARTS = Object.freeze({
  [KnowledgeSource.PERCEPTION]: perceptionParts,
  [KnowledgeSource.WORKING_MEMORY]: contactParts,
  [KnowledgeSource.RULES]: ruleParts,
  [KnowledgeSource.PROBABILISTIC]: samplingParts,
});

/**
 * @param {Document} document The page.
 * @param {Object|null} reasoning How a backend reasoned, or null for a backend that does
 *   not say.
 * @param {Array<string>} answers The backend's answers, most likely first.
 * @param {Array<string>} evidence What the backend based its answers on, in words.
 * @param {number} span Over how many milliseconds the drawing appears.
 * @returns {HTMLElement} The drawing; the evidence alone for a backend that does not say
 *   how it reasoned.
 */
export function reasoningView(document, reasoning, answers, evidence, span) {
  const view = element(document, 'div', 'reasoning');
  const drawn = DRAWN_PARTS[reasoning?.[ReasoningKey.SOURCE]];
  view.dataset.source = reasoning?.[ReasoningKey.SOURCE] ?? '';
  if (drawn) view.append(...drawn(document, reasoning, span, answers));
  else view.append(element(document, 'ul', 'reasoning-evidence', null, evidence.map((said) => element(document, 'li', '', said))));
  return view;
}
