/**
 * The controls under the 3D view: play and pause, saving a live episode, the speed,
 * and a slider with the recorded steps marked on it, coloured by what happens there,
 * next to the current time.
 */

import { SegmentKey } from '../protocol.js';

/**
 * The playback speeds offered, in recording seconds per second.
 */
export const SPEEDS = Object.freeze([0.25, 0.5, 1, 2, 4, 8]);

/**
 * What a mark on the slider stands for; each kind has a colour of its own.
 */
export const MarkKind = Object.freeze({
  /** A step starts. */
  STEP: 'step',
  /** The step picks an object up. */
  PICK: 'pick',
  /** The step lets the object go. */
  RELEASE: 'release',
});

/**
 * The texts of the play button.
 */
const PLAY_TEXT = Object.freeze({ PLAY: '▶ Play', PAUSE: '❚❚ Pause' });

// %% marks

/**
 * One mark on the slider.
 */
export class TimelineMark {
  /**
   * @param {string} kind A `MarkKind` value.
   * @param {number} frame The frame it marks.
   * @param {number} segment The position of the step it belongs to.
   * @param {string} text What happens there.
   */
  constructor(kind, frame, segment, text) {
    /**
     * A `MarkKind` value.
     * @type {string}
     */
    this.kind = kind;
    /**
     * The frame it marks.
     * @type {number}
     */
    this.frame = frame;
    /**
     * The position of the step it belongs to.
     * @type {number}
     */
    this.segment = segment;
    /**
     * What happens there.
     * @type {string}
     */
    this.text = text;
  }
}

/**
 * @param {Array<Object>} segments The recorded steps.
 * @returns {Array<TimelineMark>} A mark where each step starts, and where it picks an
 *   object up and lets it go.
 */
export function marksOf(segments) {
  return segments.flatMap((segment, position) => {
    const step = segment[SegmentKey.STEP];
    const picked = segment[SegmentKey.PICKS];
    const marks = [new TimelineMark(MarkKind.STEP, segment[SegmentKey.START], position, `${step} starts`)];
    if (segment[SegmentKey.ATTACH] !== undefined && segment[SegmentKey.ATTACH] !== null) {
      marks.push(new TimelineMark(MarkKind.PICK, segment[SegmentKey.ATTACH], position, `${step} picks up ${picked ?? 'an object'}`));
    }
    if (segment[SegmentKey.DETACH] !== undefined && segment[SegmentKey.DETACH] !== null) {
      marks.push(new TimelineMark(MarkKind.RELEASE, segment[SegmentKey.DETACH], position, `${step} lets go of ${picked ?? 'the object'}`));
    }
    return marks;
  });
}

// %% view

export class TimelineView {
  /**
   * The controls' element.
   * @type {HTMLElement}
   */
  #root;

  /**
   * The play and pause button.
   * @type {HTMLButtonElement}
   */
  #playButton;

  /**
   * The button saving a live episode.
   * @type {HTMLButtonElement}
   */
  #saveButton;

  /**
   * The frame slider.
   * @type {HTMLInputElement}
   */
  #slider;

  /**
   * The marks on the slider.
   * @type {HTMLElement}
   */
  #marks;

  /**
   * The current time.
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
   * @param {HTMLElement} root The controls' element.
   * @param {function(number): void} onSeek Called with the frame a person seeks to.
   * @param {function(): void} onSave Called when a person asks to save the live episode.
   */
  constructor(root, onSeek, onSave) {
    const document = root.ownerDocument;
    this.#root = root;
    this.#onSeek = onSeek;
    this.#playButton = document.createElement('button');
    this.#playButton.type = 'button';
    this.#playButton.className = 'play-button';
    this.#playButton.addEventListener('click', () => this.togglePlaying());
    this.#saveButton = document.createElement('button');
    this.#saveButton.type = 'button';
    this.#saveButton.className = 'save-button';
    this.#saveButton.textContent = '💾 Save episode…';
    this.#saveButton.title = 'Stop capturing the live run, then name and keep it';
    this.#saveButton.addEventListener('click', () => onSave());
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
    const buttons = document.createElement('div');
    buttons.className = 'workflow-buttons';
    buttons.append(this.#playButton, this.#saveButton, this.#speed);
    const track = document.createElement('div');
    track.className = 'track';
    this.#slider = document.createElement('input');
    this.#slider.type = 'range';
    this.#slider.min = '0';
    this.#slider.setAttribute('aria-label', 'Frame');
    this.#slider.addEventListener('input', () => this.#onSeek(Number(this.#slider.value)));
    this.#marks = document.createElement('div');
    this.#marks.className = 'marks';
    track.append(this.#slider, this.#marks);
    this.#clockText = document.createElement('span');
    this.#clockText.className = 'clock';
    const scrub = document.createElement('div');
    scrub.className = 'scrub-row';
    scrub.append(track, this.#clockText);
    root.replaceChildren(buttons, scrub);
    this.setSaveOffered(false);
    this.show(null, []);
  }

  /**
   * Show a recording's clock and steps; a still scene, or none, leaves the controls
   * disabled.
   * @param {import('./playback-clock.js').PlaybackClock|null} clock The recording's clock.
   * @param {Array<Object>} segments The recording's steps.
   */
  show(clock, segments) {
    this.#clock = clock;
    const still = !clock || clock.lastFrame === 0;
    this.#playButton.disabled = still;
    this.#slider.disabled = still;
    this.#speed.disabled = still;
    this.#root.dataset.still = String(still);
    if (clock) clock.speed = Number(this.#speed.value);
    const lastFrame = clock?.lastFrame ?? 0;
    this.#slider.max = String(lastFrame);
    const document = this.#root.ownerDocument;
    this.#marks.replaceChildren(
      ...(still ? [] : marksOf(segments)).map((mark) => {
        const element = document.createElement('button');
        element.type = 'button';
        element.className = `mark mark-${mark.kind}`;
        element.dataset.segment = String(mark.segment);
        element.dataset.kind = mark.kind;
        element.style.left = `${(100 * mark.frame) / lastFrame}%`;
        element.title = mark.text;
        element.setAttribute('aria-label', mark.text);
        element.addEventListener('click', () => this.#onSeek(mark.frame));
        return element;
      }),
    );
    this.update(-1);
  }

  /**
   * @param {boolean} offered Whether a live episode can be saved now.
   */
  setSaveOffered(offered) {
    this.#saveButton.hidden = !offered;
  }

  /**
   * Start or pause playback.
   */
  togglePlaying() {
    if (!this.#clock) return;
    this.setPlaying(!this.#clock.playing);
  }

  /**
   * Start or pause playback.
   * @param {boolean} playing Whether to play.
   */
  setPlaying(playing) {
    if (!this.#clock) return;
    this.#clock.playing = playing;
    this.update(-1);
  }

  /**
   * Show the clock's state.
   * @param {number} segment The position of the current step, -1 for none.
   */
  update(segment) {
    const playing = Boolean(this.#clock?.playing);
    this.#playButton.textContent = playing ? PLAY_TEXT.PAUSE : PLAY_TEXT.PLAY;
    this.#playButton.setAttribute('aria-pressed', String(playing));
    this.#slider.value = String(this.#clock?.frame ?? 0);
    this.#clockText.textContent = `${formatSeconds(this.#clock?.time ?? 0)} / ${formatSeconds(this.#clock?.duration ?? 0)}`;
    this.#clockText.title = `frame ${this.#clock?.frame ?? 0}`;
    for (const mark of this.#marks.children) {
      mark.classList.toggle('current', mark.dataset.kind === MarkKind.STEP && Number(mark.dataset.segment) === segment);
    }
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
