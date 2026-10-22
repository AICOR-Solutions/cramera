/**
 * The viewer application: coordinates the scene picker, the 3D view, the timeline,
 * the side panels and the plugins. Each part owns its own elements and cleanup.
 */

import { EventBus } from '../core/event-bus.js';
import { sceneOf, withScene } from '../core/scene-address.js';
import { PageStatus } from '../core/page-status.js';
import { BuildKey, SceneKey, ViewerEvent, ViewerInfoKey } from '../protocol.js';
import { PlaybackClock } from '../playback/playback-clock.js';
import { TimelineView } from '../playback/timeline-view.js';
import { DetailsPanel } from '../panels/details-panel.js';
import { PanelHost } from '../panels/panel-host.js';
import { PlanPanel } from '../panels/plan-panel.js';
import { SceneChoice } from '../panels/scene-choice.js';
import { ScenePickerView } from '../panels/scene-picker-view.js';
import { StatechartPanel } from '../panels/statechart-panel.js';
import { StepsPanel } from '../panels/steps-panel.js';
import { ViewPanel, ViewSwitch } from '../panels/view-panel.js';
import { SceneLighting } from '../scene/scene-lighting.js';
import { SceneLoader } from '../scene/scene-loader.js';
import { SceneHighlights } from '../scene/scene-highlights.js';
import { ScenePicking } from '../scene/scene-picking.js';
import { SceneView } from '../scene/scene-view.js';
import { KeyboardShortcuts, PlaybackActions } from './keyboard-shortcuts.js';
import { PluginContext, PluginModules } from './plugin-modules.js';

/**
 * How many characters of a commit hash the version badge shows.
 */
const SHORT_COMMIT = 7;

// %% elements

/**
 * The page elements the application fills.
 */
export class PageElements {
  /**
   * @param {Document} document The page.
   */
  constructor(document) {
    /**
     * The page.
     * @type {Document}
     */
    this.document = document;
    /**
     * The 3D view's container.
     * @type {HTMLElement}
     */
    this.stage = document.getElementById('stage');
    /**
     * The message shown over the 3D view.
     * @type {HTMLElement}
     */
    this.stageMessage = document.getElementById('stage-message');
    /**
     * The scene picker.
     * @type {HTMLElement}
     */
    this.picker = document.getElementById('scene-picker');
    /**
     * The side panels.
     * @type {HTMLElement}
     */
    this.side = document.getElementById('side-panels');
    /**
     * The timeline.
     * @type {HTMLElement}
     */
    this.timeline = document.getElementById('timeline');
    /**
     * The version badge.
     * @type {HTMLElement}
     */
    this.version = document.getElementById('viewer-version');
    /**
     * The status line.
     * @type {HTMLElement}
     */
    this.statusLine = document.getElementById('status-line');
  }
}

// %% application

export class Application {
  /**
   * The page elements.
   * @type {PageElements}
   */
  #elements;

  /**
   * The viewer's routes.
   * @type {import('../core/viewer-api.js').ViewerApi}
   */
  #api;

  /**
   * The page's location, read for the requested scene and updated with the shown one.
   * @type {Location}
   */
  #location;

  /**
   * The browser's history, updated with the shown scene.
   * @type {History}
   */
  #history;

  /**
   * The event bus the parts and plugins talk through.
   * @type {EventBus}
   */
  bus = new EventBus();

  /**
   * How far the page is.
   * @type {PageStatus}
   */
  #status;

  /**
   * The 3D view, once created.
   * @type {SceneView|null}
   */
  #view = null;

  /**
   * The view's lights.
   * @type {SceneLighting}
   */
  #lighting = new SceneLighting();

  /**
   * The shown scene, once loaded.
   * @type {import('../scene/scene-loader.js').LoadedScene|null}
   */
  #scene = null;

  /**
   * The shown scene's clock.
   * @type {PlaybackClock|null}
   */
  #clock = null;

  /**
   * Cancels the scene being loaded when another is chosen.
   * @type {AbortController|null}
   */
  #loading = null;

  /**
   * The timeline.
   * @type {TimelineView}
   */
  #timeline;

  /**
   * The side panels.
   * @type {PanelHost}
   */
  #panels;

  /**
   * The steps panel.
   * @type {StepsPanel}
   */
  #steps;

  /**
   * The plan panel.
   * @type {PlanPanel}
   */
  #plan;

  /**
   * The details panel.
   * @type {DetailsPanel}
   */
  #details;

  /**
   * The statechart panel.
   * @type {StatechartPanel}
   */
  #statechart;

  /**
   * The view panel, once the 3D view exists.
   * @type {ViewPanel|null}
   */
  #viewPanel = null;

  /**
   * Selects links and objects in the 3D view, once it exists.
   * @type {ScenePicking|null}
   */
  #picking = null;

  /**
   * Lights up what answers name, once the 3D view exists.
   * @type {SceneHighlights|null}
   */
  #highlights = null;

  /**
   * The scene picker's choice, once the scenes are known.
   * @type {SceneChoice|null}
   */
  #choice = null;

  /**
   * The scene picker, once the scenes are known.
   * @type {ScenePickerView|null}
   */
  #picker = null;

  /**
   * @param {PageElements} elements The page elements.
   * @param {import('../core/viewer-api.js').ViewerApi} api The viewer's routes.
   * @param {Location} location The page's location.
   * @param {History} history The browser's history.
   */
  constructor(elements, api, location, history) {
    this.#elements = elements;
    this.#api = api;
    this.#location = location;
    this.#history = history;
    this.#status = new PageStatus(elements.document.documentElement, elements.statusLine);
    this.#timeline = new TimelineView(elements.timeline, (frame) => this.seek(frame));
    this.#panels = new PanelHost(elements.side);
    this.#steps = new StepsPanel(elements.document, (frame) => this.seek(frame));
    this.#plan = new PlanPanel(elements.document);
    this.#details = new DetailsPanel(elements.document);
    this.#statechart = new StatechartPanel(elements.document);
    for (const part of [this.#steps, this.#plan, this.#statechart, this.#details]) this.#panels.add(part.panel);
  }

  /**
   * Load the viewer's information and scenes, then show the requested or default scene.
   * @param {function(string): Promise<Object>} importModule Imports a plugin module by URL.
   * @returns {Promise<void>} Settles once the first scene is shown or has failed.
   */
  async start(importModule) {
    this.#status.loading('Loading scenes…');
    const [info, index] = await Promise.all([this.#api.info(), this.#api.scenes()]);
    this.#showVersion(info);
    const choice = new SceneChoice(index);
    const requested = sceneOf(this.#location.href);
    if (requested) choice.chooseScene(requested);
    if (!choice.scene) {
      this.#fail('No scenes found. Record a run or add a scenes directory.');
      return;
    }
    this.#choice = choice;
    this.#picker = new ScenePickerView(this.#elements.picker, choice, (name) => this.show(name));
    this.#view = new SceneView(this.#elements.stage);
    this.#view.scene.add(this.#lighting.group);
    this.#addViewPanel(this.#view);
    this.#picking = new ScenePicking(this.#view, this.bus);
    this.#highlights = new SceneHighlights(this.#view);
    this.bus.subscribe(ViewerEvent.ENTITY_HIGHLIGHTED, (keys) => this.#highlights.show(keys ?? []));
    this.bus.subscribe(ViewerEvent.ENTITY_SELECTED, (selection) => this.#details.showSelection(selection));
    this.bus.subscribe(ViewerEvent.SCENE_REQUESTED, (name) => this.showRequested(name));
    this.bus.subscribe(ViewerEvent.FRAME_REQUESTED, (frame) => this.seek(frame));
    this.bus.subscribe(ViewerEvent.PLAYBACK_REQUESTED, (playing) => this.#timeline.setPlaying(playing));
    new KeyboardShortcuts(
      this.#elements.document,
      new PlaybackActions(
        () => this.#timeline.togglePlaying(),
        (frames) => this.seek((this.#clock?.frame ?? 0) + frames),
        (last) => this.seek(last ? (this.#clock?.lastFrame ?? 0) : 0),
      ),
    );
    this.#view.start((seconds) => this.#tick(seconds));
    const context = new PluginContext(this.bus, this.#panels, this.#api, this.#view);
    await new PluginModules(importModule).register(info, context, (module) => this.#api.url(module));
    await this.show(choice.scene);
  }

  /**
   * Show a bundle; a scene still loading is cancelled.
   * @param {string} name The bundle's name.
   * @returns {Promise<void>} Settles once the scene is shown, has failed or was replaced.
   */
  async show(name) {
    this.#loading?.abort();
    const loading = new AbortController();
    this.#loading = loading;
    this.#status.loading(`Loading ${name}…`);
    this.bus.publish(ViewerEvent.SCENE_LOADING, name);
    const loader = new SceneLoader(this.#api);
    const progress = (loaded, total) => this.#status.loading(`Loading ${name}: ${loaded} of ${total} files`);
    const loaded = await loader.load(name, this.#view, this.#lighting, loading.signal, progress).catch((error) => {
      if (!loading.signal.aborted) this.#fail(`Could not show ${name}: ${error.message}`);
      return null;
    });
    if (!loaded) return;
    this.#scene?.dispose();
    this.#scene = loaded;
    this.#picking.select(null);
    this.#highlights.clear();
    this.#viewPanel.refresh();
    this.#clock = new PlaybackClock(loaded.frames.framesPerSecond, loaded.frames.frameCount);
    const segments = loaded.description[SceneKey.SEGMENTS] ?? [];
    this.#timeline.show(this.#clock, segments);
    this.#steps.show(segments);
    this.#plan.show(loaded.description[SceneKey.PLAN_TREES] ?? []);
    this.#statechart.show(loaded.statecharts);
    this.#details.show(loaded);
    this.#rememberScene(name);
    this.#elements.stageMessage.hidden = true;
    const missing = loaded.missingFiles().length;
    this.#status.ready(missing ? `Showing ${name}; ${missing} files could not be loaded (see Details)` : `Showing ${name}`);
    this.bus.publish(ViewerEvent.SCENE_LOADED, loaded);
  }

  /**
   * Show a bundle another part asked for, and let the scene picker show it as chosen.
   * @param {string} name The bundle's name.
   * @returns {Promise<void>} Settles once the scene is shown, has failed or was replaced.
   */
  showRequested(name) {
    if (!this.#choice.chooseScene(name)) {
      this.#fail(`No scenes directory holds a bundle named ${name}.`);
      return Promise.resolve();
    }
    this.#picker.render();
    return this.show(name);
  }

  /**
   * Show a frame of the current recording.
   * @param {number} frame The frame.
   */
  seek(frame) {
    if (!this.#clock) return;
    this.#clock.seek(frame);
    this.#showFrame();
  }

  /**
   * Let playback time pass.
   * @param {number} seconds Wall-clock seconds since the previous call.
   * @returns {boolean} Whether the shown frame changed.
   */
  #tick(seconds) {
    if (!this.#clock || !this.#clock.advance(seconds)) return false;
    this.#showFrame();
    return true;
  }

  /**
   * Pose the scene for the clock's frame and update the parts that show it.
   */
  #showFrame() {
    const frame = this.#clock.frame;
    this.#scene.showFrame(frame);
    const segment = this.#scene.frames.segmentAt(frame);
    this.#timeline.update(segment);
    this.#steps.mark(segment);
    this.#statechart.showFrame(frame);
    this.#picking.update();
    this.#highlights.update();
    this.#view.requestRender();
    this.bus.publish(ViewerEvent.FRAME_CHANGED, frame);
  }

  /**
   * @param {SceneView} view The 3D view the panel's switches change.
   */
  #addViewPanel(view) {
    this.#viewPanel = new ViewPanel(this.#elements.document, [
      new ViewSwitch('Ambient occlusion', () => view.ambientOcclusion, (enabled) => view.setAmbientOcclusion(enabled)),
      new ViewSwitch('Shadows on the ground', () => view.ground.visible, (shown) => view.showGround(shown)),
    ]);
    this.#panels.add(this.#viewPanel.panel);
  }

  /**
   * @param {Object} info The viewer's information.
   */
  #showVersion(info) {
    const build = info[ViewerInfoKey.BUILD];
    const stamp = build ? ` · ${build[BuildKey.COMMIT].slice(0, SHORT_COMMIT)} · ${build[BuildKey.BUILT_AT]}` : '';
    this.#elements.version.textContent = `v${info[ViewerInfoKey.VERSION]}${stamp}`;
  }

  /**
   * Put the shown scene into the page's address, so it can be shared and reloaded.
   * @param {string} name The bundle's name.
   */
  #rememberScene(name) {
    this.#history.replaceState(null, '', withScene(this.#location.href, name));
  }

  /**
   * @param {string} message Why the page cannot show its scene.
   */
  #fail(message) {
    this.#status.failed(message);
    this.#elements.stageMessage.textContent = message;
    this.#elements.stageMessage.hidden = false;
    this.bus.publish(ViewerEvent.SCENE_FAILED, message);
  }
}
