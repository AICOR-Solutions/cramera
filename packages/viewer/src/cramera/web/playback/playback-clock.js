/**
 * Which trajectory frame to show: playback follows elapsed time and speed, never the
 * screen's frame rate.
 */

// %% clock

export class PlaybackClock {
  /**
   * How many trajectory frames make one second of the recording.
   * @type {number}
   */
  #framesPerSecond;

  /**
   * How many frames the trajectory has.
   * @type {number}
   */
  #frameCount;

  /**
   * The recording time shown, in seconds.
   * @type {number}
   */
  #time = 0;

  /**
   * Recording seconds per wall-clock second.
   * @type {number}
   */
  #speed = 1;

  /**
   * Whether time advances.
   * @type {boolean}
   */
  #playing = false;

  /**
   * Whether playback starts over after the last frame.
   * @type {boolean}
   */
  #looping = false;

  /**
   * @param {number} framesPerSecond How many frames make one second; must be positive.
   * @param {number} frameCount How many frames the trajectory has.
   */
  constructor(framesPerSecond, frameCount) {
    if (!(framesPerSecond > 0)) throw new RangeError(`frames per second must be positive, got ${framesPerSecond}`);
    this.#framesPerSecond = framesPerSecond;
    this.#frameCount = Math.max(frameCount, 0);
  }

  /**
   * @returns {number} The frame shown now.
   */
  get frame() {
    return this.#frameAt(this.#time);
  }

  /**
   * @returns {number} The last frame.
   */
  get lastFrame() {
    return Math.max(this.#frameCount - 1, 0);
  }

  /**
   * @returns {number} The recording's duration in seconds.
   */
  get duration() {
    return this.lastFrame / this.#framesPerSecond;
  }

  /**
   * @returns {number} The recording time shown, in seconds.
   */
  get time() {
    return this.#time;
  }

  /**
   * @returns {boolean} Whether time advances.
   */
  get playing() {
    return this.#playing;
  }

  /**
   * @returns {number} Recording seconds per wall-clock second.
   */
  get speed() {
    return this.#speed;
  }

  /**
   * @param {boolean} playing Whether time advances; playing at the end starts over.
   */
  set playing(playing) {
    if (playing && this.frame >= this.lastFrame) this.#time = 0;
    this.#playing = playing;
  }

  /**
   * @param {number} speed Recording seconds per wall-clock second; must be positive.
   */
  set speed(speed) {
    if (!(speed > 0)) throw new RangeError(`speed must be positive, got ${speed}`);
    this.#speed = speed;
  }

  /**
   * @param {boolean} looping Whether playback starts over after the last frame.
   */
  set looping(looping) {
    this.#looping = looping;
  }

  /**
   * Show a frame.
   * @param {number} frame The frame; clamped to the trajectory.
   */
  seek(frame) {
    const clamped = Math.min(Math.max(Math.round(frame), 0), this.lastFrame);
    this.#time = clamped / this.#framesPerSecond;
  }

  /**
   * Let wall-clock time pass.
   * @param {number} seconds Wall-clock seconds since the last call.
   * @returns {boolean} Whether the shown frame changed.
   */
  advance(seconds) {
    if (!this.#playing || seconds <= 0) return false;
    const before = this.frame;
    this.#time += seconds * this.#speed;
    if (this.#time >= this.duration) {
      if (this.#looping && this.duration > 0) this.#time %= this.duration;
      else {
        this.#time = this.duration;
        this.#playing = false;
      }
    }
    return this.frame !== before;
  }

  /**
   * @param {number} time A recording time in seconds.
   * @returns {number} The frame shown at that time.
   */
  #frameAt(time) {
    return Math.min(Math.floor(time * this.#framesPerSecond + 1e-9), this.lastFrame);
  }
}
