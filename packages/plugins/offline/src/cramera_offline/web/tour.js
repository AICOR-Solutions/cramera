/**
 * The tour through a storyboard: shows each chapter's bundle, starts it at the
 * chapter's frame, plays it when the chapter asks, and in an automatic tour moves on
 * once the chapter's time is over and its recording has reached its last frame.
 */

import { ChapterKey, StoryboardKey, ViewerEvent } from '../../protocol.js';

/**
 * How many milliseconds make one second.
 */
const MILLISECONDS_PER_SECOND = 1000;

// %% timer

/**
 * Calls back after a delay; the browser's timers.
 */
export class BrowserTimer {
  /**
   * @param {number} milliseconds The delay.
   * @param {function(): void} callback Called once the delay is over.
   * @returns {number} The handle that cancels the call.
   */
  after(milliseconds, callback) {
    return setTimeout(callback, milliseconds);
  }

  /**
   * @param {number|null} handle A handle `after` returned, or null.
   */
  cancel(handle) {
    clearTimeout(handle ?? undefined);
  }
}

// %% tour

export class Tour {
  /**
   * The storyboard.
   * @type {Object}
   */
  storyboard;

  /**
   * The application's event bus.
   * @type {import('../../core/event-bus.js').EventBus}
   */
  #bus;

  /**
   * The side panels, for the panel a chapter opens.
   * @type {import('../../panels/panel-host.js').PanelHost}
   */
  #panels;

  /**
   * Calls back after a chapter's time.
   * @type {BrowserTimer}
   */
  #timer;

  /**
   * Called whenever the shown chapter or the running state changes.
   * @type {function(): void}
   */
  #onChange;

  /**
   * The position of the shown chapter.
   * @type {number}
   */
  #position = 0;

  /**
   * Whether the tour moves on by itself.
   * @type {boolean}
   */
  #running = false;

  /**
   * The bundle the application shows, once one is loaded.
   * @type {string|null}
   */
  #shownScene = null;

  /**
   * The last frame of the shown bundle's recording.
   * @type {number}
   */
  #lastFrame = 0;

  /**
   * The position of the chapter waiting for its bundle to load, or null.
   * @type {number|null}
   */
  #waiting = null;

  /**
   * Whether the shown chapter's time is over.
   * @type {boolean}
   */
  #timeOver = false;

  /**
   * Whether the shown chapter's recording reached its last frame, or plays nothing.
   * @type {boolean}
   */
  #playbackOver = false;

  /**
   * The handle of the shown chapter's timer, or null.
   * @type {number|null}
   */
  #timeout = null;

  /**
   * @param {Object} storyboard The storyboard, as the offline plugin answers it.
   * @param {import('../../core/event-bus.js').EventBus} bus The application's event bus.
   * @param {import('../../panels/panel-host.js').PanelHost} panels The side panels.
   * @param {BrowserTimer} timer Calls back after a chapter's time.
   * @param {function(): void} onChange Called when the chapter or the running state changes.
   */
  constructor(storyboard, bus, panels, timer, onChange) {
    this.storyboard = storyboard;
    this.#bus = bus;
    this.#panels = panels;
    this.#timer = timer;
    this.#onChange = onChange;
    bus.subscribe(ViewerEvent.SCENE_LOADED, (loaded) => this.#sceneLoaded(loaded));
    bus.subscribe(ViewerEvent.SCENE_FAILED, () => this.#sceneFailed());
    bus.subscribe(ViewerEvent.FRAME_CHANGED, (frame) => this.#frameChanged(frame));
  }

  /**
   * @returns {Array<Object>} The chapters, in order.
   */
  get chapters() {
    return this.storyboard[StoryboardKey.CHAPTERS];
  }

  /**
   * @returns {number} The position of the shown chapter.
   */
  get position() {
    return this.#position;
  }

  /**
   * @returns {boolean} Whether the tour moves on by itself.
   */
  get running() {
    return this.#running;
  }

  /**
   * Run the tour from the shown chapter on.
   */
  start() {
    this.#running = true;
    this.show(this.#position);
  }

  /**
   * Stop moving on by itself and pause the recording.
   */
  pause() {
    this.#running = false;
    this.#timer.cancel(this.#timeout);
    this.#timeout = null;
    this.#bus.publish(ViewerEvent.PLAYBACK_REQUESTED, false);
    this.#onChange();
  }

  /**
   * Show the next chapter; after the last one a running tour stops.
   */
  next() {
    if (this.#position + 1 < this.chapters.length) {
      this.show(this.#position + 1);
      return;
    }
    this.pause();
  }

  /**
   * Show the previous chapter, or the first one again.
   */
  previous() {
    this.show(Math.max(0, this.#position - 1));
  }

  /**
   * Show a chapter: open its panel, load its bundle unless it is shown, then start it.
   * @param {number} position The chapter's position.
   */
  show(position) {
    this.#timer.cancel(this.#timeout);
    this.#timeout = null;
    this.#position = position;
    const chapter = this.chapters[position];
    const panel = chapter[ChapterKey.PANEL];
    if (panel && this.#panels.identifiers().includes(panel)) this.#panels.show(panel);
    this.#onChange();
    if (this.#shownScene === chapter[ChapterKey.SCENE]) {
      this.#begin(position);
      return;
    }
    this.#waiting = position;
    this.#bus.publish(ViewerEvent.SCENE_REQUESTED, chapter[ChapterKey.SCENE]);
  }

  /**
   * Start a chapter whose bundle is shown.
   * @param {number} position The chapter's position.
   */
  #begin(position) {
    const chapter = this.chapters[position];
    const frame = chapter[ChapterKey.FRAME] ?? 0;
    const playback = Boolean(chapter[ChapterKey.PLAYBACK]);
    this.#bus.publish(ViewerEvent.PLAYBACK_REQUESTED, false);
    this.#bus.publish(ViewerEvent.FRAME_REQUESTED, frame);
    this.#timeOver = false;
    this.#playbackOver = !playback || frame >= this.#lastFrame;
    if (!this.#playbackOver) this.#bus.publish(ViewerEvent.PLAYBACK_REQUESTED, true);
    if (!this.#running) return;
    this.#timeout = this.#timer.after(chapter[ChapterKey.DURATION] * MILLISECONDS_PER_SECOND, () => {
      this.#timeout = null;
      this.#timeOver = true;
      this.#moveOnWhenDone();
    });
  }

  /**
   * Move on once the shown chapter's time is over and its recording has ended.
   */
  #moveOnWhenDone() {
    if (this.#running && this.#timeOver && this.#playbackOver) this.next();
  }

  /**
   * @param {Object} loaded The loaded scene: its `name` and its `frames`.
   */
  #sceneLoaded(loaded) {
    this.#shownScene = loaded.name;
    this.#lastFrame = Math.max(0, loaded.frames.frameCount - 1);
    const waiting = this.#waiting;
    if (waiting === null || this.chapters[waiting][ChapterKey.SCENE] !== loaded.name) return;
    this.#waiting = null;
    this.#begin(waiting);
  }

  /**
   * A chapter whose bundle cannot be loaded stops the tour.
   */
  #sceneFailed() {
    this.#shownScene = null;
    if (this.#waiting === null) return;
    this.#waiting = null;
    this.pause();
  }

  /**
   * @param {number} frame The shown frame.
   */
  #frameChanged(frame) {
    if (this.#playbackOver || frame < this.#lastFrame) return;
    this.#playbackOver = true;
    this.#moveOnWhenDone();
  }
}
