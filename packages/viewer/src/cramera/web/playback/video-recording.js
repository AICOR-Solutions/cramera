/**
 * Filming the 3D view into a video file: every frame the view renders is captured while
 * the recording plays, and saved as a WebM file once it ends.
 */

/**
 * The video formats tried, best first; the browser films in the first it supports.
 */
export const VIDEO_TYPES = Object.freeze(['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm']);

/**
 * The suffix of a saved video's file name.
 */
export const VIDEO_SUFFIX = '.webm';

// %% recording

export class VideoRecording {
  /**
   * The recorder filming the canvas.
   * @type {MediaRecorder}
   */
  #recorder;

  /**
   * The parts of the video filmed so far.
   * @type {Array<Blob>}
   */
  #chunks = [];

  /**
   * Settles with the whole video once the recorder stopped.
   * @type {Promise<Blob>}
   */
  #finished;

  /**
   * Stops capturing a frame after each render.
   * @type {function(): void}
   */
  #unlisten;

  /**
   * @param {HTMLCanvasElement} canvas The canvas filmed.
   * @param {typeof MediaRecorder} Recorder The browser's `MediaRecorder`.
   * @param {function(function(): void): function(): void} onRender Calls a listener after
   *   each frame the view renders and answers how to stop; each render becomes one
   *   frame of the video, as a browser need not capture a canvas that is not shown.
   */
  constructor(canvas, Recorder, onRender) {
    const type = VIDEO_TYPES.find((candidate) => Recorder.isTypeSupported(candidate)) ?? '';
    const stream = canvas.captureStream(0);
    const [track] = stream.getVideoTracks();
    this.#unlisten = onRender(() => track.requestFrame());
    this.#recorder = new Recorder(stream, type ? { mimeType: type } : {});
    this.#recorder.addEventListener('dataavailable', (event) => {
      if (event.data?.size) this.#chunks.push(event.data);
    });
    this.#finished = new Promise((resolve) => {
      this.#recorder.addEventListener('stop', () => resolve(new Blob(this.#chunks, { type: type || 'video/webm' })));
    });
  }

  /**
   * @param {HTMLCanvasElement} canvas A canvas.
   * @param {Object} window The browser's window.
   * @returns {boolean} Whether the browser can film the canvas.
   */
  static supported(canvas, window) {
    return typeof canvas.captureStream === 'function' && typeof window.MediaRecorder === 'function';
  }

  /**
   * Start filming.
   */
  start() {
    this.#recorder.start();
  }

  /**
   * Stop filming.
   * @returns {Promise<Blob>} The whole video.
   */
  stop() {
    this.#unlisten();
    if (this.#recorder.state !== 'inactive') this.#recorder.stop();
    return this.#finished;
  }
}

/**
 * Hand a video to the person as a file download.
 * @param {Document} document The page.
 * @param {Blob} video The video.
 * @param {string} name The file name without its suffix.
 */
export function saveVideo(document, video, name) {
  const url = URL.createObjectURL(video);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${name}${VIDEO_SUFFIX}`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
