/**
 * A complete laboratory workspace with its own 3D view, controls and PR2 playback.
 * Scene changes stay on this page, including a freshly installed simulation or run.
 */

import { EventBus } from '../../core/event-bus.js';
import { PageStatus } from '../../core/page-status.js';
import { sceneOf, withScene } from '../../core/scene-address.js';
import { LiveClient } from '../../live/live-client.js';
import { LiveListener, LiveSession } from '../../live/live-session.js';
import { PlaybackClock } from '../../playback/playback-clock.js';
import { TimelineView } from '../../playback/timeline-view.js';
import { saveVideo, VideoRecording } from '../../playback/video-recording.js';
import { SceneLighting } from '../../scene/scene-lighting.js';
import { SceneLoader } from '../../scene/scene-loader.js';
import { SceneView } from '../../scene/scene-view.js';
import { InstalledLaboratoryKey, LaboratoryChoiceKey, LaboratoryDemo, LaboratoryRoute, SceneKey, TaskRunKey, TaskRunState, ViewerEvent } from '../../protocol.js';
import { connectLaboratory } from './index.js';
import { LaboratoryClient } from './laboratory-client.js';
import { BrowserTimer } from './simulation-follower.js';

/** The sole workbench offered by this page. */
const BENCH = 'aicor_medical_lab';

/**
 * What the timeline says while it follows a robot demo, by `LaboratoryDemo` value.
 */
export const FollowingText = Object.freeze({
  [LaboratoryDemo.TRANSFER]: 'Following the local PR2 vessel transfer. The recording appears here when it finishes.',
  [LaboratoryDemo.WORKFLOW]: 'Following the local PR2 lab workflow. The recording appears here when it finishes.',
});

/** @returns {string} The viewer root, preserving a reverse proxy's path prefix. */
export function viewerRootOf(page) {
  return new URL('../../', page).href;
}

export class LaboratoryPage {
  /** The workspace's event bus. */
  bus = new EventBus();
  /** The workspace's page and API services. */
  #environment;
  /** The page document. */
  #document;
  /** The container for the native renderer. */
  #stage;
  /** The fixed control column, without a panel tab strip. */
  #controls;
  /** The status of the page's initial loading and subsequent scene changes. */
  #status;
  /** The 3D view once started. */
  #view = null;
  /** The lights reused between scenes. */
  #lighting = new SceneLighting();
  /** The active bundle, once loaded. */
  #scene = null;
  /** The current scene load, cancelled by a newer request. */
  #loading = null;
  /** The shared laboratory controls and polling. */
  #parts = null;
  /** The recording's playback clock, or null. */
  #clock = null;
  /** Playback controls under the scene. */
  #timeline;
  /** The active live PR2 session, or null. */
  #live = null;
  /** The live endpoint followed, or null. */
  #liveUrl = null;
  /** The most recent state of every robot demo, by `LaboratoryDemo` value. */
  #runs = new Map();
  /** The robot demo whose live run the view follows, or null. */
  #followed = null;
  /** Whether the initial view is ready for robot demo updates. */
  #started = false;
  /** Whether the page has been left. */
  #disposed = false;
  /** The browser's current video recording, or null. */
  #video = null;

  /**
   * @param {HTMLElement} root The complete laboratory workspace.
   * @param {Object} environment Viewer API, location, history, fetch and optional test services.
   */
  constructor(root, environment) {
    this.#environment = {
      timer: new BrowserTimer(), timers: globalThis,
      createView: (stage) => new SceneView(stage), createLoader: (api) => new SceneLoader(api),
      ...environment,
    };
    this.#document = root.ownerDocument;
    const element = (tag, className, text = '') => Object.assign(this.#document.createElement(tag), { className, textContent: text });
    const scene = element('section', 'card laboratory-scene');
    scene.setAttribute('aria-label', 'Small physical lab and PR2');
    const heading = element('div', 'card-head');
    heading.append(element('h2', '', 'Physical lab · small workbench and PR2'));
    this.#stage = element('section', 'stage');
    this.#stage.setAttribute('aria-label', 'Physical lab 3D view');
    const status = element('p', 'viewer-status status-line', 'Loading physical lab…');
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    this.#status = new PageStatus(this.#document.documentElement, status);
    this.#stage.append(status, element('p', 'stage-hint', 'drag orbit · scroll zoom · right-drag pan'));
    const timeline = element('footer', 'workflow');
    timeline.setAttribute('aria-label', 'PR2 recording playback');
    this.#timeline = new TimelineView(timeline, (frame) => this.seek(frame), () => {}, () => this.toggleVideo());
    scene.append(heading, this.#stage, timeline);
    this.#controls = element('aside', 'card laboratory-controls');
    this.#controls.setAttribute('aria-label', 'Laboratory controls');
    root.replaceChildren(scene, this.#controls);
  }

  /** Prepare the real PR2 preview and show the small lab immediately on entry. */
  async start() {
    const environment = this.#environment;
    this.#view = environment.createView(this.#stage);
    this.#view.scene.add(this.#lighting.group);
    this.#view.start((seconds) => {
      if (this.#live || !this.#clock || !this.#clock.advance(seconds)) return false;
      this.#showFrame();
      if (this.#video && !this.#clock.playing) this.toggleVideo();
      return true;
    });
    this.#parts = await connectLaboratory(
      { bus: this.bus, api: environment.api, view: this.#view },
      (name) => { this.disconnectLive(); return this.show(name); },
      this.#document, environment.timer, environment.fetch, () => {}, (demo, run) => this.followDemo(demo, run),
    );
    if (this.#disposed) { this.#parts.dispose(); return; }
    this.#controls.replaceChildren(this.#parts.panel.panel.element);
    const client = new LaboratoryClient(environment.fetch, environment.api);
    let prepared;
    try {
      this.#status.loading('Preparing the PR2 and small physical lab…');
      prepared = await client.send(LaboratoryRoute.PREVIEW);
    } catch (error) {
      this.#parts.panel.showMessage(error.reason ?? error.message, true);
      prepared = await client.send(LaboratoryRoute.INSTALL, { [LaboratoryChoiceKey.LABORATORY]: BENCH });
    }
    await this.show(sceneOf(environment.location.href) ?? prepared[InstalledLaboratoryKey.SCENE]);
    this.#started = true;
    for (const [demo, run] of this.#runs) this.followDemo(demo, run);
  }

  /** Load any lab bundle in place, without restarting the page or losing controls. */
  async show(name) {
    if (this.#disposed) return false;
    if (this.#video) this.toggleVideo();
    this.#loading?.abort();
    const loading = new AbortController();
    this.#loading = loading;
    this.#status.loading(`Loading ${name}…`);
    this.bus.publish(ViewerEvent.SCENE_LOADING, name);
    try {
      const loaded = await this.#environment.createLoader(this.#environment.api).load(
        name, this.#view, this.#lighting, loading.signal,
        (count, total) => this.#status.loading(`Loading ${name}: ${count} of ${total} files`),
      );
      if (loading.signal.aborted || this.#disposed) { loaded.dispose(); return false; }
      this.#scene?.dispose();
      this.#scene = loaded;
      this.#clock = new PlaybackClock(loaded.frames.framesPerSecond, loaded.frames.frameCount);
      this.#timeline.show(this.#clock, loaded.description[SceneKey.SEGMENTS] ?? []);
      this.#environment.history.replaceState(null, '', withScene(this.#environment.location.href, name));
      const missing = loaded.missingFiles().length;
      this.#status.ready(missing ? `Showing ${name}; ${missing} model files could not load.` : `Showing ${name}`);
      this.bus.publish(ViewerEvent.SCENE_LOADED, loaded);
      this.#view.requestRender();
      return true;
    } catch (error) {
      if (!loading.signal.aborted) this.fail(error.reason ?? error.message);
      return false;
    }
  }

  /**
   * Follow a robot demo's local PR2 while it runs and open its completed recording.
   * @param {string} demo A `LaboratoryDemo` value.
   * @param {Object} run The demo's state, keyed by `TaskRunKey`.
   */
  followDemo(demo, run) {
    const previous = this.#runs.get(demo);
    this.#runs.set(demo, run);
    if (!this.#started || this.#disposed) return;
    const state = run[TaskRunKey.STATE];
    const liveUrl = run[TaskRunKey.LIVE_URL];
    if (state === TaskRunState.RUNNING && liveUrl) {
      if (liveUrl === this.#liveUrl) return;
      this.disconnectLive();
      this.#liveUrl = liveUrl;
      this.#followed = demo;
      const environment = this.#environment;
      const session = new LiveSession(new LiveClient(environment.fetch, environment.api.url(liveUrl)), environment.timers, this.bus,
        new LiveListener(
          (name) => {
            if (this.#live !== session) return;
            this.show(name).then((shown) => { if (shown && this.#live === session) session.sceneShown(); });
          },
          (snapshot) => {
            if (this.#live !== session) return;
            this.#scene?.showState(snapshot);
            this.#view.requestRender();
          },
          () => {}, () => {}, () => {},
        ));
      this.#live = session;
      this.#timeline.setLive(true, FollowingText[demo]);
      session.start();
    } else if (state !== TaskRunState.RUNNING) {
      if (this.#followed === demo) this.disconnectLive();
      if (state === TaskRunState.RECORDED && previous?.[TaskRunKey.STATE] === TaskRunState.RUNNING) this.show(run[TaskRunKey.SCENE]);
    }
  }

  /** Leave live following without stopping the robot's owned server process. */
  disconnectLive() {
    this.#live?.stop();
    this.#live = null;
    this.#liveUrl = null;
    this.#followed = null;
    this.#timeline.setLive(false);
  }

  /** Seek a frame in the saved PR2 recording. */
  seek(frame) {
    if (!this.#clock || this.#live) return;
    this.#clock.seek(frame);
    this.#showFrame();
  }

  /** Apply a recorded frame to the robot, vessels and playback controls. */
  #showFrame() {
    this.#scene.showFrame(this.#clock.frame);
    this.#timeline.update(this.#scene.frames.segmentAt(this.#clock.frame));
    this.#view.requestRender();
    this.bus.publish(ViewerEvent.FRAME_CHANGED, this.#clock.frame);
  }

  /** Record the displayed PR2 replay into a downloadable video. */
  toggleVideo() {
    if (this.#video) {
      const recording = this.#video;
      const name = this.#scene.name;
      this.#video = null;
      this.#timeline.setPlaying(false);
      this.#timeline.setFilming(false);
      this.#view.setSolidBackground(null);
      recording.stop().then((video) => saveVideo(this.#document, video, name));
      return;
    }
    const canvas = this.#view?.renderer.domElement;
    const window = this.#document.defaultView;
    if (!this.#clock || this.#live || !canvas) return;
    if (!VideoRecording.supported(canvas, window)) {
      this.#parts.panel.showMessage('This browser cannot record the 3D view as video.');
      return;
    }
    this.#view.setSolidBackground(window.getComputedStyle(this.#stage).getPropertyValue('--stage').trim());
    this.#video = new VideoRecording(canvas, window.MediaRecorder, (listener) => this.#view.onRender(listener));
    this.#timeline.setFilming(true);
    this.seek(0);
    this.#video.start();
    this.#timeline.setPlaying(true);
  }

  /** Show a scene-loading or startup error on the dedicated page. */
  fail(message) {
    this.#status.failed(`The physical lab could not load: ${message}`);
  }

  /** Release browser resources when leaving the dedicated laboratory page. */
  dispose() {
    this.#disposed = true;
    this.#loading?.abort();
    this.#video?.stop();
    this.#video = null;
    this.disconnectLive();
    this.#parts?.dispose();
    this.#scene?.dispose();
    if (this.#view) this.#lighting.dispose(this.#view.scene);
    this.#view?.dispose();
  }
}
