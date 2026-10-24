/**
 * The Perception panel: what the robot's perception was asked and what it reported. One
 * entry per perception step of the shown recording's plans, or of the live plan: the
 * action it belongs to with its parameters, how it ended, why it failed, and the
 * objects it reported, which light up in the 3D view, and the images of what it saw; a
 * step whose frames are recorded replays its moment.
 */

import { LivePlanKey, LivePlanNodeKey, PerceptionImageKey, PerceptionImageSource, PlanNodeKey, ViewerEvent } from '../protocol.js';
import { SidePanel } from './panel-host.js';

/**
 * What the panel says before a perception step is known.
 */
export const NO_PERCEPTION = 'No perception step ran in this scene. A plan’s detect actions appear here with what they were asked and what they reported.';

/**
 * What a step that reported no object and gave no reason says.
 */
export const NOTHING_REPORTED = 'Nothing reported yet.';

/**
 * Where perception answers, for people reading the panel.
 */
export const PERCEPTION_SOURCES = 'In simulation perception reads the world model; on the real robot it asks RoboKudo.';

/**
 * Where each kind of image comes from, for people reading the panel.
 */
export const IMAGE_SOURCES = {
  [PerceptionImageSource.CAMERA]: 'rendered from the world model',
  [PerceptionImageSource.ROBOKUDO]: 'RoboKudo',
};

/**
 * What a step that ended without images says where its images would be.
 */
export const NO_IMAGES = 'No images were taken.';

// %% steps

/**
 * One perception step of a plan.
 */
export class PerceptionStep {
  /**
   * @param {Object} parts The step's parts: `identifier`, `action` (the label of the
   *   action it belongs to), `parameters` (that action's parameters, else the step's
   *   own), `status`, `reason`, `perceived` (object keys or names), `images` (each with
   *   its `title`, `source` and `url`), `start`, `end` and `robot`.
   */
  constructor(parts) {
    Object.assign(this, parts);
  }
}

/**
 * @param {Array<Object>} roots Recorded plan trees.
 * @returns {Array<Object>} Their nodes, each with its parent's identity and its plan's
 *   robot, as a live plan lists them; a node recorded without an identity is named by
 *   its place in the trees.
 */
export function flattened(roots) {
  const nodes = [];
  const visit = (node, place, parent, robot) => {
    const identifier = node[PlanNodeKey.IDENTIFIER] ?? place;
    const own = node[PlanNodeKey.ROBOT] ?? robot;
    nodes.push({ ...node, [PlanNodeKey.IDENTIFIER]: identifier, [PlanNodeKey.PARENT]: parent, robot: own });
    (node[PlanNodeKey.CHILDREN] ?? []).forEach((child, position) => visit(child, `${place}.${position}`, identifier, own));
  };
  roots.forEach((root, position) => visit(root, String(position), null, null));
  return nodes;
}

/**
 * @param {Array<Object>} nodes A plan's nodes, each naming its parent; a recorded node
 *   and a live one carry the same keys.
 * @param {function(string): string} imageUrl The URL of an image, from where the node
 *   says it is.
 * @returns {Array<PerceptionStep>} Its perception steps, in plan order.
 */
export function perceptionSteps(nodes, imageUrl = (file) => file) {
  const byIdentifier = new Map(nodes.map((node) => [node[PlanNodeKey.IDENTIFIER], node]));
  return nodes
    .filter((node) => Array.isArray(node[PlanNodeKey.PERCEIVED]))
    .map((node) => {
      const action = byIdentifier.get(node[PlanNodeKey.PARENT]) ?? node;
      const own = node[PlanNodeKey.PARAMETERS] ?? {};
      return new PerceptionStep({
        identifier: node[PlanNodeKey.IDENTIFIER],
        action: action[PlanNodeKey.LABEL],
        parameters: Object.keys(action[PlanNodeKey.PARAMETERS] ?? {}).length ? action[PlanNodeKey.PARAMETERS] : own,
        status: node[PlanNodeKey.STATUS],
        reason: node[PlanNodeKey.REASON] ?? action[PlanNodeKey.REASON] ?? null,
        perceived: node[PlanNodeKey.PERCEIVED],
        images: (node[PlanNodeKey.IMAGES] ?? []).map((image) => ({
          title: image[PerceptionImageKey.TITLE],
          source: image[PerceptionImageKey.SOURCE],
          url: imageUrl(image[PerceptionImageKey.FILE]),
        })),
        start: node[PlanNodeKey.START] ?? action[PlanNodeKey.START] ?? null,
        end: node[PlanNodeKey.END] ?? action[PlanNodeKey.END] ?? null,
        robot: node.robot ?? null,
      });
    });
}

// %% panel

export class PerceptionPanel {
  /**
   * The panel.
   * @type {SidePanel}
   */
  panel;

  /**
   * The bus the panel lights objects up and requests frames on.
   * @type {import('../core/event-bus.js').EventBus}
   */
  #bus;

  /**
   * The names of the shown scene's objects, by key.
   * @type {Map<string, string>}
   */
  #names = new Map();

  /**
   * The steps shown.
   * @type {Array<PerceptionStep>}
   */
  steps = [];

  /**
   * The list of steps.
   * @type {HTMLElement}
   */
  #list;

  /**
   * @param {Document} document The page.
   * @param {import('../core/event-bus.js').EventBus} bus The bus the panel lights
   *   objects up and requests frames on.
   */
  constructor(document, bus) {
    this.#bus = bus;
    this.panel = new SidePanel('perception', 'Perception', document.createElement('section'));
    this.panel.element.classList.add('perception');
    const sources = document.createElement('p');
    sources.className = 'muted';
    sources.textContent = PERCEPTION_SOURCES;
    this.#list = document.createElement('ol');
    this.#list.className = 'perception-steps';
    this.panel.element.append(sources, this.#list);
    this.showSteps([]);
  }

  /**
   * @param {import('../scene/scene-loader.js').LoadedScene} scene The shown scene.
   * @param {string} plansKey The scene description's key of its plan trees.
   * @param {function(string): string} fileUrl The URL of one of the scene's files.
   */
  show(scene, plansKey, fileUrl) {
    this.#names = new Map(scene.objects.named().map(({ key, name }) => [key, name]));
    this.showSteps(perceptionSteps(flattened(scene.description[plansKey] ?? []), fileUrl));
  }

  /**
   * @param {Object} plan The live plan.
   * @param {function(string): string} imageUrl The URL of an image the publisher
   *   serves, by its key.
   */
  showLive(plan, imageUrl) {
    const nodes = (plan[LivePlanKey.NODES] ?? []).map((node) => ({
      ...node,
      [PlanNodeKey.PERCEIVED]: node[LivePlanNodeKey.PERCEIVED],
      [PlanNodeKey.IMAGES]: node[LivePlanNodeKey.IMAGES],
    }));
    this.showSteps(perceptionSteps(nodes, imageUrl));
  }

  /**
   * @param {Array<PerceptionStep>} steps The steps to show.
   */
  showSteps(steps) {
    this.steps = steps;
    const document = this.panel.element.ownerDocument;
    if (!steps.length) {
      const empty = document.createElement('li');
      empty.className = 'empty';
      empty.textContent = NO_PERCEPTION;
      this.#list.replaceChildren(empty);
      return;
    }
    this.#list.replaceChildren(...steps.map((step) => this.#entry(document, step)));
  }

  /**
   * @param {Document} document The page.
   * @param {PerceptionStep} step A step.
   * @returns {HTMLElement} The step's entry.
   */
  #entry(document, step) {
    const entry = document.createElement('li');
    entry.className = 'perception-step';
    entry.dataset.step = step.identifier;
    entry.dataset.status = step.status;
    const head = document.createElement('div');
    head.className = 'perception-head';
    const title = document.createElement('strong');
    title.textContent = step.action;
    const status = document.createElement('span');
    status.className = 'perception-status';
    status.textContent = step.status;
    head.append(title, status);
    if (step.robot) head.append(this.#text(document, 'span', 'muted', step.robot));
    if (step.start !== null) {
      const replay = document.createElement('button');
      replay.type = 'button';
      replay.textContent = '↺ Replay';
      replay.title = 'Show the moment this step ran';
      replay.addEventListener('click', () => this.#bus.publish(ViewerEvent.FRAME_REQUESTED, step.start));
      head.append(replay);
    }
    const asked = document.createElement('dl');
    asked.className = 'facts';
    for (const [name, value] of Object.entries(step.parameters)) {
      asked.append(this.#text(document, 'dt', '', name.replaceAll('_', ' ')), this.#text(document, 'dd', '', value));
    }
    const parts = [head, this.#text(document, 'h4', '', 'Asked'), asked, this.#text(document, 'h4', '', 'Reported')];
    if (step.perceived.length) {
      const seen = document.createElement('ul');
      seen.className = 'perception-seen';
      for (const key of step.perceived) {
        const item = document.createElement('li');
        const button = document.createElement('button');
        button.type = 'button';
        button.dataset.key = key;
        button.textContent = this.#names.get(key) ?? key;
        button.title = 'Light it up in the 3D view';
        button.addEventListener('click', () => this.#bus.publish(ViewerEvent.ENTITY_HIGHLIGHTED, [key]));
        item.append(button);
        seen.append(item);
      }
      parts.push(seen);
    } else {
      parts.push(this.#text(document, 'p', 'muted', step.reason ?? NOTHING_REPORTED));
    }
    if (step.reason && step.perceived.length) parts.push(this.#text(document, 'p', 'perception-reason', step.reason));
    if (step.status !== 'RUNNING' && step.status !== 'CREATED') parts.push(this.#text(document, 'h4', '', 'Saw'), this.#images(document, step));
    entry.append(...parts);
    return entry;
  }

  /**
   * @param {Document} document The page.
   * @param {PerceptionStep} step A step that ended.
   * @returns {HTMLElement} Its images, each opening full size, or the note that none
   *   were taken.
   */
  #images(document, step) {
    if (!step.images.length) return this.#text(document, 'p', 'muted', NO_IMAGES);
    const strip = document.createElement('div');
    strip.className = 'perception-images';
    for (const image of step.images) {
      const figure = document.createElement('figure');
      figure.dataset.source = image.source;
      const link = document.createElement('a');
      link.href = image.url;
      link.target = '_blank';
      link.rel = 'noopener';
      link.title = 'Open full size';
      const picture = document.createElement('img');
      picture.src = image.url;
      picture.alt = `${image.title} of ${step.action}`;
      picture.loading = 'lazy';
      link.append(picture);
      const caption = document.createElement('figcaption');
      caption.append(this.#text(document, 'strong', '', image.title), this.#text(document, 'span', 'muted', IMAGE_SOURCES[image.source] ?? image.source));
      figure.append(link, caption);
      strip.append(figure);
    }
    return strip;
  }

  /**
   * @param {Document} document The page.
   * @param {string} tag The element's tag.
   * @param {string} className Its classes.
   * @param {string} text Its text.
   * @returns {HTMLElement} The element.
   */
  #text(document, tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = text;
    return element;
  }
}
