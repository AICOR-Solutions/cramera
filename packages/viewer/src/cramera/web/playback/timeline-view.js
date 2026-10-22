/**
 * The timeline under the 3D view: play and pause, speed, a slider with the recorded
 * steps under it, and the current time.
 */

import { SegmentKey } from '../protocol.js';

/**
 * The playback speeds offered, in recording seconds per second.
 */
export const SPEEDS = Object.freeze([0.25, 0.5, 1, 2, 4, 8]);

// %% view

export class TimelineView {
  /**
   * The timeline element.
   * @type {HTMLElement}
   */
  #root;

  /**
   * The play and pause button.
   * @type {HTMLButtonElement}
   */
  #playButton;

  /**
   * The frame slider.
   * @type {HTMLInputElement}
   */
  #slider;

  /**
   * The step markers under the slider.
   * @type {HTMLElement}
   */
  #segments;

  /**
   * The current time and frame.
   * @type {HTMLElement}
   */
  #clockText;

  /**
   * The speed choice.
   * @type {HTMLSelectElement}
   */
  #speed;

  /**
   * The clock the view shows and controls.
   * @type {import('./playback-clock.js').PlaybackClock|null}
   */
  #clock = null;

  /**
   * Called with the frame a person seeks to.
   * @type {function(number): void}
   */
  #onSeek;

  /**
   * @param {HTMLElement} root The timeline element.
   * @param {function(number): void} onSeek Called with the frame a person seeks to.
   */
  constructor(root, onSeek) {
    const document = root.ownerDocument;
    this.#root = root;
    this.#onSeek = onSeek;
    this.#playButton = document.createElement('button');
    this.#playButton.className = 'primary';
    this.#playButton.addEventListener('click', () => this.togglePlaying());
    this.#speed = document.createElement('select');
    this.#speed.className = 'speed';
    this.#speed.setAttribute('aria-label', 'Playback speed');
    for (const speed of SPEEDS) {
      const option = document.createElement('option');
      option.value = String(speed);
      option.textContent = `${speed}×`;
      this.#speed.append(option);
    }
    this.#speed.value = '1';
    this.#speed.addEventListener('change', () => { if (this.#clock) this.#clock.speed = Number(this.#speed.value); });
    const track = document.createElement('div');
    track.className = 'track';
    this.#slider = document.createElement('input');
    this.#slider.type = 'range';
    this.#slider.min = '0';
    this.#slider.setAttribute('aria-label', 'Frame');
    this.#slider.addEventListener('input', () => this.#onSeek(Number(this.#slider.value)));
    this.#segments = document.createElement('div');
    this.#segments.className = 'segments';
    track.append(this.#slider, this.#segments);
    this.#clockText = document.createElement('span');
    this.#clockText.className = 'clock';
    root.replaceChildren(this.#playButton, this.#speed, track, this.#clockText);
    this.show(null, []);
  }

  /**
   * Show a recording's clock and steps, or hide the timeline for a still scene.
   * @param {import('./playback-clock.js').PlaybackClock|null} clock The recording's clock.
   * @param {Array<Object>} segments The recording's steps.
   */
  show(clock, segments) {
    this.#clock = clock;
    this.#root.hidden = !clock || clock.lastFrame === 0;
    if (!clock) return;
    clock.speed = Number(this.#speed.value);
    this.#slider.max = String(clock.lastFrame);
    const total = clock.lastFrame + 1;
    this.#segments.replaceChildren(
      ...segments.map((segment) => {
        const marker = this.#root.ownerDocument.createElement('span');
        marker.style.left = `${(100 * segment[SegmentKey.START]) / total}%`;
        marker.style.width = `${(100 * (segment[SegmentKey.END] - segment[SegmentKey.START] + 1)) / total}%`;
        marker.title = segment[SegmentKey.STEP];
        return marker;
      }),
    );
    this.update(-1);
  }

  /**
   * Start or pause playback.
   */
  togglePlaying() {
    if (!this.#clock) return;
    this.#clock.playing = !this.#clock.playing;
    this.update(-1);
  }

  /**
   * Show the clock's state.
   * @param {number} segment The position of the current step, -1 for none.
   */
  update(segment) {
    if (!this.#clock) return;
    this.#playButton.textContent = this.#clock.playing ? 'Pause' : 'Play';
    this.#slider.value = String(this.#clock.frame);
    this.#clockText.textContent = `${formatSeconds(this.#clock.time)} / ${formatSeconds(this.#clock.duration)} · frame ${this.#clock.frame}`;
    [...this.#segments.children].forEach((marker, position) => marker.classList.toggle('current', position === segment));
  }
}

// %% formatting

/**
 * @param {number} seconds A duration.
 * @returns {string} The duration as minutes and seconds with tenths.
 */
export function formatSeconds(seconds) {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${(seconds - minutes * 60).toFixed(1).padStart(4, '0')}`;
}
