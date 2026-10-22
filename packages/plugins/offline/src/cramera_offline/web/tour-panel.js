/**
 * The Tour side panel: the storyboard's chapters with controls to start, pause and
 * step through them, the shown chapter's narration, and the completeness check of the
 * shown bundle.
 */

import { SidePanel } from '../../panels/panel-host.js';
import {
  AssetProblemKey,
  BundleCheckKey,
  ChapterKey,
  PluginName,
  StoryboardKey,
  ViewerEvent,
} from '../../protocol.js';

// %% panel

export class TourPanel {
  /**
   * The side panel.
   * @type {SidePanel}
   */
  panel;

  /**
   * The page.
   * @type {Document}
   */
  #document;

  /**
   * The offline plugin's routes.
   * @type {import('./offline-client.js').OfflineClient}
   */
  #client;

  /**
   * The tour, once a storyboard is shown.
   * @type {import('./tour.js').Tour|null}
   */
  #tour = null;

  /**
   * The storyboard's part of the panel.
   * @type {HTMLElement}
   */
  storyboard;

  /**
   * The chapter buttons, in chapter order.
   * @type {Array<HTMLButtonElement>}
   */
  chapterButtons = [];

  /**
   * The button starting and pausing the tour.
   * @type {HTMLButtonElement|null}
   */
  runButton = null;

  /**
   * The shown chapter's narration.
   * @type {HTMLElement}
   */
  narration;

  /**
   * The shown bundle's completeness check.
   * @type {HTMLElement}
   */
  bundleCheck;

  /**
   * The bundle whose check was asked for last.
   * @type {string|null}
   */
  #checkedScene = null;

  /**
   * @param {Document} document The page.
   * @param {import('./offline-client.js').OfflineClient} client The offline plugin's routes.
   * @param {import('../../core/event-bus.js').EventBus} bus The application's event bus.
   */
  constructor(document, client, bus) {
    this.#document = document;
    this.#client = client;
    const element = document.createElement('section');
    element.className = 'tour-panel';
    this.panel = new SidePanel(PluginName.OFFLINE, 'Tour', element);
    this.storyboard = document.createElement('div');
    this.narration = document.createElement('p');
    this.narration.className = 'tour-narration';
    const checkHeading = document.createElement('h2');
    checkHeading.textContent = 'Bundle check';
    this.bundleCheck = document.createElement('div');
    this.bundleCheck.className = 'tour-check';
    element.append(this.storyboard, this.narration, checkHeading, this.bundleCheck);
    bus.subscribe(ViewerEvent.SCENE_LOADED, (loaded) => this.checkBundle(loaded.name));
  }

  /**
   * Show a storyboard and the controls of its tour.
   * @param {import('./tour.js').Tour} tour The tour through the storyboard.
   */
  showTour(tour) {
    this.#tour = tour;
    const storyboard = tour.storyboard;
    const title = this.#document.createElement('h2');
    title.textContent = storyboard[StoryboardKey.TITLE];
    const description = this.#document.createElement('p');
    description.className = 'tour-description';
    description.textContent = storyboard[StoryboardKey.DESCRIPTION] ?? '';
    const controls = this.#document.createElement('div');
    controls.className = 'tour-controls';
    const previous = this.#button('◀ Previous', () => tour.previous());
    this.runButton = this.#button('', () => (tour.running ? tour.pause() : tour.start()));
    this.runButton.className = 'primary';
    const next = this.#button('Next ▶', () => tour.next());
    controls.append(previous, this.runButton, next);
    const chapters = this.#document.createElement('ol');
    chapters.className = 'tour-chapters';
    this.chapterButtons = tour.chapters.map((chapter, position) => {
      const item = this.#document.createElement('li');
      const button = this.#button(chapter[ChapterKey.TITLE], () => tour.show(position));
      item.append(button);
      chapters.append(item);
      return button;
    });
    this.storyboard.replaceChildren(title, description, controls, chapters);
    this.update();
  }

  /**
   * Say why there is no tour.
   * @param {string} message The reason.
   * @param {boolean} failed Whether a storyboard exists but cannot be read.
   */
  showMessage(message, failed) {
    const text = this.#document.createElement('p');
    text.className = failed ? 'tour-error' : 'tour-note';
    text.textContent = message;
    this.storyboard.replaceChildren(text);
  }

  /**
   * Mark the shown chapter, its narration and whether the tour runs.
   */
  update() {
    if (!this.#tour) return;
    const position = this.#tour.position;
    this.chapterButtons.forEach((button, index) => button.setAttribute('aria-current', String(index === position)));
    this.narration.textContent = this.#tour.chapters[position][ChapterKey.NARRATION] ?? '';
    this.runButton.textContent = this.#tour.running ? 'Pause tour' : 'Start tour';
  }

  /**
   * Show the completeness check of a bundle; an answer for a bundle shown before is
   * dropped.
   * @param {string} scene The shown bundle.
   * @returns {Promise<void>} Settles once the check or why it is missing is shown.
   */
  async checkBundle(scene) {
    this.#checkedScene = scene;
    const report = await this.#client.bundleCheck(scene);
    if (this.#checkedScene !== scene) return;
    if (!report) {
      this.#say(this.bundleCheck, 'This server does not check bundles.', 'tour-note');
      return;
    }
    const problems = report[BundleCheckKey.PROBLEMS];
    if (!problems.length) {
      this.#say(this.bundleCheck, `${scene}: complete, ${report[BundleCheckKey.CHECKED_FILES].length} files.`, 'tour-note');
      return;
    }
    const list = this.#document.createElement('ul');
    for (const problem of problems) {
      const item = this.#document.createElement('li');
      item.textContent = `${problem[AssetProblemKey.KIND]}: ${problem[AssetProblemKey.SOURCE]} → ${problem[AssetProblemKey.REFERENCE]}`;
      list.append(item);
    }
    this.#say(this.bundleCheck, `${scene}: ${problems.length} references cannot be followed.`, 'tour-error');
    this.bundleCheck.append(list);
  }

  /**
   * @param {HTMLElement} element Where the message goes.
   * @param {string} message The message.
   * @param {string} className Its class.
   */
  #say(element, message, className) {
    const text = this.#document.createElement('p');
    text.className = className;
    text.textContent = message;
    element.replaceChildren(text);
  }

  /**
   * @param {string} text The button's text.
   * @param {function(): void} action What a click does.
   * @returns {HTMLButtonElement} The button.
   */
  #button(text, action) {
    const button = this.#document.createElement('button');
    button.type = 'button';
    button.textContent = text;
    button.addEventListener('click', action);
    return button;
  }
}
