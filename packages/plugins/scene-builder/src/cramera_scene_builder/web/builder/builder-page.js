/**
 * The builder page: lays out the menus, library, 3D view, instance list and inspector,
 * and connects them to the draft being edited and to the server.
 */

import {
  AppearanceKey,
  BuilderPageParameter,
  CatalogKey,
  DraftListKey,
  DraftRecordKey,
  DraftKey,
  InstanceKey,
  PointCloudFormat,
  ResourceKey,
  ResourceKind,
} from '../../../protocol.js';
import { PageStatus } from '../../../core/page-status.js';
import { DraftCheck } from './draft-check.js';
import { BuilderHeader, DraftMenu, MenuActions, ViewToolbar } from './draft-menu.js';
import { DraftRecovery } from './draft-recovery.js';
import { DraftState } from './draft-state.js';
import { DraftViewListeners, Selection, TransformMode } from './draft-view.js';
import { DomEvent, Elements } from './elements.js';
import { InspectorActions, InspectorView } from './inspector-view.js';
import { InstanceList } from './instance-list.js';
import { LibraryView } from './library-view.js';

/**
 * The suffix of an exported draft's file name.
 */
const EXPORT_SUFFIX = '.scene.json';

/**
 * The media type of an exported draft.
 */
const EXPORT_MEDIA_TYPE = 'application/json';

/**
 * Characters an exported file name keeps; others become `_`.
 */
const FILE_NAME_CHARACTERS = /[^A-Za-z0-9_-]+/g;

/**
 * The key that undoes with Ctrl or Cmd, and redoes with Shift as well.
 */
const UNDO_KEY = 'z';

/**
 * The elements whose own keys win over the builder's shortcuts.
 */
const FORM_CONTROLS = Object.freeze(['INPUT', 'SELECT', 'TEXTAREA']);

/**
 * Separates a file name from its suffix.
 */
const SUFFIX_SEPARATOR = '.';

// %% errors

/**
 * A point cloud file of a format the builder does not read.
 */
export class UnsupportedPointCloudFile extends Error {
  /**
   * @param {string} name The file's name.
   */
  constructor(name) {
    super(`${name} is no ${Object.values(PointCloudFormat).join(' or ').toUpperCase()} file.`);
    /**
     * The file's name.
     * @type {string}
     */
    this.name = name;
  }
}

// %% environment

/**
 * What the page needs of the browser.
 */
export class BuilderEnvironment {
  /**
   * @param {Object} parts The parts, by name: `document`, `api` (a `BuilderApi`),
   *   `storage` (a `Storage`), `query` (the page's `URLSearchParams`), `viewerUrl`,
   *   `createView` (builds a `DraftView` in a container with listeners, or null without
   *   WebGL) and `download` (offers a `Blob` as a file of a name).
   */
  constructor(parts) {
    /**
     * The page's document.
     * @type {Document}
     */
    this.document = parts.document;
    /**
     * The builder's routes.
     * @type {import('./builder-api.js').BuilderApi}
     */
    this.api = parts.api;
    /**
     * The browser's storage.
     * @type {Storage}
     */
    this.storage = parts.storage;
    /**
     * The page's query parameters.
     * @type {URLSearchParams}
     */
    this.query = parts.query;
    /**
     * The viewer's page.
     * @type {string}
     */
    this.viewerUrl = parts.viewerUrl;
    /**
     * Builds the 3D view, or null when the browser cannot show one.
     * @type {(function(HTMLElement, DraftViewListeners): import('./draft-view.js').DraftView)|null}
     */
    this.createView = parts.createView;
    /**
     * Offers a file to save.
     * @type {function(Blob, string): void}
     */
    this.download = parts.download;
  }
}

// %% page

export class BuilderPage {
  /**
   * What the page needs of the browser.
   * @type {BuilderEnvironment}
   */
  #environment;

  /**
   * Builds the page's frame and owns its listeners.
   * @type {Elements}
   */
  #elements;

  /**
   * The draft being edited, or null until the catalog arrived.
   * @type {DraftState|null}
   */
  #state = null;

  /**
   * The 3D view, or null without WebGL.
   * @type {import('./draft-view.js').DraftView|null}
   */
  #view = null;

  /**
   * The copy of the draft in the browser's storage.
   * @type {DraftRecovery}
   */
  #recovery;

  /**
   * The selection, or null.
   * @type {Selection|null}
   */
  #selection = null;

  /**
   * What the handles change.
   * @type {string}
   */
  #mode = TransformMode.MOVE;

  /**
   * The identity of the saved draft being edited, or null for a new draft.
   * @type {string|null}
   */
  #draftIdentifier = null;

  /**
   * The draft as last saved, as JSON, or null.
   * @type {string|null}
   */
  #savedText = null;

  /**
   * Counts the requests that replace the draft, so a late answer does not replace a newer draft.
   * @type {number}
   */
  #revision = 0;

  /**
   * How far the page is, for people and for tools such as the screenshot command.
   * @type {PageStatus}
   */
  #pageStatus;

  /**
   * The message shown once the 3D view has shown every pending resource, or null.
   * @type {string|null}
   */
  #readyMessage = null;

  /**
   * Whether to look at every instance once the 3D view has shown them.
   * @type {boolean}
   */
  #framePending = false;

  /**
   * The scenes a draft can start from, as the catalog lists them.
   * @type {Array<Object>}
   */
  #scenes = [];

  /**
   * The parts of the page.
   * @type {{header: BuilderHeader, menu: DraftMenu, toolbar: ViewToolbar, library: LibraryView, instances: InstanceList, inspector: InspectorView, stage: HTMLElement}}
   */
  #parts;

  /**
   * @param {HTMLElement} root The element the page fills.
   * @param {BuilderEnvironment} environment What the page needs of the browser.
   */
  constructor(root, environment) {
    this.#environment = environment;
    this.#recovery = new DraftRecovery(environment.storage);
    const elements = new Elements(environment.document);
    this.#elements = elements;
    const menuActions = this.#menuActions();
    const status = elements.create('p', 'status-line');
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    this.#pageStatus = new PageStatus(environment.document.documentElement, status);
    this.#parts = {
      header: new BuilderHeader(elements, menuActions, environment.viewerUrl),
      menu: new DraftMenu(elements, menuActions),
      toolbar: new ViewToolbar(elements, menuActions),
      library: new LibraryView(elements, (identifier) => this.#attempt(() => this.#add(identifier))),
      instances: new InstanceList(elements, (identifier) => this.#select(new Selection(identifier))),
      inspector: new InspectorView(elements, this.#inspectorActions()),
      stage: elements.create('div', 'builder-stage'),
    };
    const left = elements.create('aside', 'builder-side');
    left.append(this.#parts.menu.element, this.#parts.library.element);
    const center = elements.create('section', 'builder-center');
    center.append(this.#parts.toolbar.element, this.#parts.stage, status);
    const right = elements.create('aside', 'builder-side');
    right.append(this.#parts.instances.element, this.#parts.inspector.element);
    const main = elements.create('div', 'builder-main');
    main.append(left, center, right);
    root.replaceChildren(this.#parts.header.element, main);
    elements.listen(environment.document, DomEvent.KEY_DOWN, (event) => this.#shortcut(event));
  }

  /**
   * @returns {DraftState|null} The draft being edited, once the catalog arrived.
   */
  get state() {
    return this.#state;
  }

  /**
   * @returns {Selection|null} The selection.
   */
  get selection() {
    return this.#selection;
  }

  /**
   * @returns {string|null} The identity of the saved draft being edited.
   */
  get draftIdentifier() {
    return this.#draftIdentifier;
  }

  /**
   * Read the catalog, restore the draft of the last visit, show the 3D view and, when
   * the page names a scene, start a draft from it.
   * @returns {Promise<void>} Resolves once the page is ready.
   */
  async start() {
    this.#pageStatus.loading('Reading the catalog…');
    const catalog = await this.#environment.api.catalog();
    const check = new DraftCheck(catalog[CatalogKey.LIMITS], catalog[CatalogKey.DEFAULT_APPEARANCE]);
    this.#state = new DraftState(check);
    this.#state.setResources(catalog[CatalogKey.RESOURCES]);
    this.#parts.library.show(catalog[CatalogKey.RESOURCES]);
    this.#scenes = catalog[CatalogKey.SCENES];
    this.#parts.menu.show(this.#scenes, catalog[CatalogKey.DRAFTS]);
    this.#state.subscribe((draft) => this.#render(draft));
    this.#view = this.#environment.createView?.(this.#parts.stage, this.#viewListeners()) ?? null;
    if (!this.#view) {
      this.#parts.stage.append(this.#elements.create('p', 'stage-message', 'This browser cannot show the 3D view; the fields still place every instance.'));
    }
    this.#status(`${catalog[CatalogKey.RESOURCES].length} resources. Place one, or start from a scene.`);
    await this.#restore();
    this.#render(this.#state.draft);
    const scene = this.#environment.query.get(BuilderPageParameter.SCENE);
    if (scene) await this.#attempt(() => this.#openScene(scene));
  }

  /**
   * Remove every listener and free the 3D view.
   */
  dispose() {
    this.#elements.dispose();
    this.#parts.library.dispose();
    this.#parts.instances.dispose();
    this.#parts.inspector.dispose();
    this.#view?.dispose();
  }

  // %% drafts

  /**
   * @param {string} identifier A resource identifier.
   */
  #add(identifier) {
    const instance = this.#state.add(identifier);
    this.#select(new Selection(instance[InstanceKey.IDENTIFIER]));
    this.#status(`Placed ${instance[InstanceKey.NAME]}. Drag its handles or edit its fields.`);
  }

  /**
   * @param {string} scene A bundle name.
   */
  async #openScene(scene) {
    const revision = ++this.#revision;
    const draft = await this.#environment.api.template(scene);
    if (revision !== this.#revision) return;
    this.#selection = null;
    this.#replace(draft, null, null);
    this.#frameWhenShown();
    this.#status(`Opened a copy of ${scene}. The recording itself is unchanged.`);
  }

  /**
   * @param {string} identifier A saved draft's identity.
   */
  async #loadDraft(identifier) {
    const revision = ++this.#revision;
    const record = await this.#environment.api.draft(identifier);
    if (revision !== this.#revision) return;
    this.#selection = null;
    this.#replace(record[DraftRecordKey.DOCUMENT], record[DraftRecordKey.IDENTIFIER], record[DraftRecordKey.DOCUMENT]);
    this.#frameWhenShown();
    this.#status(`Opened ${record[DraftRecordKey.DOCUMENT][DraftKey.NAME]}.`);
  }

  /**
   * @param {File} file A draft file.
   */
  async #importFile(file) {
    const revision = ++this.#revision;
    const draft = JSON.parse(await file.text());
    if (revision !== this.#revision) return;
    this.#selection = null;
    this.#replace(draft, null, null);
    const missing = this.#state.draft[DraftKey.INSTANCES].filter((instance) => !this.#state.resource(instance[InstanceKey.ASSET]));
    this.#status(missing.length ? `Imported; ${missing.length} instances place resources this catalog does not offer.` : 'Imported. Save it to keep a copy on this machine.', missing.length > 0);
  }

  /**
   * @param {boolean} copy Whether to save a new draft rather than replace the open one.
   */
  async #save(copy) {
    const revision = this.#revision;
    const draft = this.#state.draft;
    const record = await this.#environment.api.save(draft, copy ? null : this.#draftIdentifier);
    await this.#refreshDrafts();
    if (revision !== this.#revision) return;
    this.#draftIdentifier = record[DraftRecordKey.IDENTIFIER];
    if (JSON.stringify(this.#state.draft) === JSON.stringify(draft)) this.#replace(record[DraftRecordKey.DOCUMENT], this.#draftIdentifier, record[DraftRecordKey.DOCUMENT]);
    this.#status(`Saved ${draft[DraftKey.NAME]}. The models it places are unchanged.`);
  }

  /**
   * Offer the draft as a file.
   */
  #exportDraft() {
    const draft = this.#state.draft;
    const name = draft[DraftKey.NAME].replace(FILE_NAME_CHARACTERS, '_');
    this.#environment.download(new Blob([this.#state.exportText()], { type: EXPORT_MEDIA_TYPE }), `${name}${EXPORT_SUFFIX}`);
  }

  /**
   * Upload a scanned room and place it as a locked reference.
   * @param {File} file A point cloud file.
   * @param {number} metres The metres in one unit of the file.
   */
  async #upload(file, metres) {
    const format = file.name.split(SUFFIX_SEPARATOR).pop().toLowerCase();
    if (!Object.values(PointCloudFormat).includes(format)) throw new UnsupportedPointCloudFile(file.name);
    this.#status(`Checking and storing ${file.name}…`);
    const revision = this.#revision;
    const resource = await this.#environment.api.upload(file, format);
    const catalog = await this.#environment.api.catalog();
    this.#state.setResources(catalog[CatalogKey.RESOURCES]);
    this.#parts.library.show(catalog[CatalogKey.RESOURCES]);
    if (revision !== this.#revision) return;
    const name = file.name.slice(0, -(format.length + SUFFIX_SEPARATOR.length));
    const instance = this.#state.add(resource[ResourceKey.IDENTIFIER], { name, scale: [metres, metres, metres] });
    this.#select(new Selection(instance[InstanceKey.IDENTIFIER]));
    this.#status(`Placed ${name} as a locked reference. Unlock it in the inspector to align it.`);
  }

  /**
   * Start an empty draft.
   */
  #newDraft() {
    this.#revision += 1;
    this.#selection = null;
    this.#replace(DraftState.empty(), null, null);
    this.#status('New scene. Place resources from the library.');
  }

  /**
   * @param {Object} draft The draft to edit.
   * @param {string|null} identifier The identity of the saved draft it is, or null.
   * @param {Object|null} saved The draft as saved, or null for an unsaved draft.
   */
  #replace(draft, identifier, saved) {
    this.#draftIdentifier = identifier;
    this.#state.replace(draft);
    this.#savedText = saved === null ? null : JSON.stringify(this.#state.draft);
    this.#render(this.#state.draft);
  }

  /**
   * Refresh the list of saved drafts.
   */
  async #refreshDrafts() {
    const list = await this.#environment.api.drafts();
    this.#parts.menu.show(this.#scenes, list[DraftListKey.DRAFTS]);
  }

  /**
   * Restore the draft of the last visit, if one is kept; an unreadable one is
   * forgotten and reported.
   * @returns {Promise<void>} Resolves once restored or reported.
   */
  #restore() {
    return Promise.resolve()
      .then(() => {
        const kept = this.#recovery.restore();
        if (kept === null) return;
        this.#state.reset(kept.draft);
        this.#draftIdentifier = kept.identifier;
      })
      .catch((error) => {
        this.#recovery.forget();
        this.#status(`The draft of the last visit could not be restored: ${error.message}`, true);
      });
  }

  // %% selection and placement

  /**
   * @param {Selection|null} selection The instance or link to select, or null.
   */
  #select(selection) {
    this.#selection = selection && this.#state.instance(selection.instance) ? selection : null;
    if (this.#selection && this.#selection.link !== null && this.#mode === TransformMode.SCALE) this.#mode = TransformMode.MOVE;
    this.#view?.setMode(this.#mode);
    this.#view?.select(this.#selection);
    this.#renderSelection(this.#state.draft);
  }

  /**
   * @param {string} mode A `TransformMode` value.
   */
  #setMode(mode) {
    this.#mode = mode === TransformMode.SCALE && this.#selection?.link ? TransformMode.MOVE : mode;
    this.#view?.setMode(this.#mode);
    this.#renderSelection(this.#state.draft);
  }

  /**
   * @param {Selection} selection What was moved.
   * @param {{position: Array<number>, rotation: Array<number>, scale: Array<number>}} placement Its new placement.
   */
  #place(selection, placement) {
    this.#state.place(selection.instance, placement, selection.link);
    if (selection.link === null && this.#mode === TransformMode.SCALE) this.#state.setScale(selection.instance, placement.scale);
  }

  // %% rendering

  /**
   * @param {Object} draft The draft.
   */
  #render(draft) {
    const state = this.#state;
    this.#parts.header.show(draft[DraftKey.NAME], state.canUndo, state.canRedo, this.#savedText === JSON.stringify(draft));
    if (this.#selection && !state.instance(this.#selection.instance)) this.#selection = null;
    this.#view?.show(draft, (identifier) => state.resource(identifier));
    this.#renderSelection(draft);
    this.#recovery.keep(draft, this.#draftIdentifier);
  }

  /**
   * @param {Object} draft The draft.
   */
  #renderSelection(draft) {
    const state = this.#state;
    const selected = this.#selection?.instance ?? null;
    const instance = state.instance(selected);
    const resource = instance ? state.resource(instance[InstanceKey.ASSET]) : undefined;
    const structure = this.#view && selected ? this.#view.structure(selected) : { links: [], joints: [] };
    this.#parts.instances.show(draft, selected, (identifier) => state.resource(identifier));
    this.#parts.inspector.show(instance, resource, structure, this.#selection?.link ?? null);
    const locked = resource?.[ResourceKey.KIND] === ResourceKind.POINT_CLOUD && instance[InstanceKey.POINT_CLOUD]?.[AppearanceKey.LOCKED];
    this.#parts.toolbar.show(this.#mode, instance !== null && !locked);
  }

  /**
   * Look at every instance now, or once the 3D view has shown them.
   */
  #frameWhenShown() {
    this.#framePending = Boolean(this.#view?.isLoading());
    if (!this.#framePending) this.#view?.frameAll();
  }

  /**
   * @param {string} message What to tell the person.
   * @param {boolean=} failed Whether the message reports a failure.
   */
  #status(message, failed = false) {
    this.#readyMessage = null;
    if (failed) this.#pageStatus.failed(message);
    else if (this.#view?.isLoading()) {
      this.#readyMessage = message;
      this.#pageStatus.loading('Loading the models…');
    } else this.#pageStatus.ready(message);
  }

  /**
   * Run an action of the person, reporting a refusal or failure in the status line;
   * this is the page's one boundary where errors become messages.
   * @param {function(): (void|Promise<void>)} action The action.
   * @returns {Promise<void>} Resolves once the action finished or failed.
   */
  #attempt(action) {
    return Promise.resolve()
      .then(action)
      .catch((error) => this.#status(error.message ?? String(error), true));
  }

  /**
   * Undo and redo with Ctrl or Cmd and Z, outside form fields.
   * @param {KeyboardEvent} event A key press.
   */
  #shortcut(event) {
    if (!this.#state || FORM_CONTROLS.includes(event.target?.tagName)) return;
    if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== UNDO_KEY) return;
    event.preventDefault();
    if (event.shiftKey) this.#state.redo();
    else this.#state.undo();
  }

  // %% actions

  /**
   * @returns {MenuActions} What the menus ask of the page.
   */
  #menuActions() {
    return new MenuActions({
      rename: (name) => this.#attempt(() => this.#state.rename(name)),
      undo: () => this.#state?.undo(),
      redo: () => this.#state?.redo(),
      save: (copy) => this.#attempt(() => this.#save(copy)),
      newDraft: () => this.#attempt(() => this.#newDraft()),
      openScene: (scene) => this.#attempt(() => this.#openScene(scene)),
      loadDraft: (identifier) => this.#attempt(() => this.#loadDraft(identifier)),
      importFile: (file) => this.#attempt(() => this.#importFile(file)),
      exportDraft: () => this.#attempt(() => this.#exportDraft()),
      upload: (file, metres) => this.#attempt(() => this.#upload(file, metres)),
      setMode: (mode) => this.#setMode(mode),
      frameSelection: () => this.#view?.frameSelection(),
      frameAll: () => this.#view?.frameAll(),
    });
  }

  /**
   * @returns {InspectorActions} What the inspector asks of the page.
   */
  #inspectorActions() {
    const selected = () => this.#selection.instance;
    return new InspectorActions({
      rename: (name) => this.#attempt(() => this.#state.renameInstance(selected(), name)),
      describe: (description) => this.#attempt(() => this.#state.describeInstance(selected(), description)),
      duplicate: () => this.#attempt(() => this.#select(new Selection(this.#state.duplicate(selected())[InstanceKey.IDENTIFIER]))),
      remove: () =>
        this.#attempt(() => {
          this.#state.remove(selected());
          this.#select(null);
        }),
      chooseLink: (link) => this.#select(new Selection(selected(), link)),
      place: (position, rotation) => this.#attempt(() => this.#state.place(selected(), { position, rotation }, this.#selection.link)),
      scale: (scale) => this.#attempt(() => this.#state.setScale(selected(), scale)),
      setProportional: (proportional) => this.#view?.setProportional(proportional),
      setAppearance: (changes) => this.#attempt(() => this.#state.setAppearance(selected(), changes)),
      resetLink: () => this.#attempt(() => this.#state.resetLink(selected(), this.#selection.link)),
      setJoint: (joint, value) => this.#attempt(() => this.#state.setJoint(selected(), joint, value)),
      noticeUrl: (asset) => this.#environment.api.assetUrl(asset),
    });
  }

  /**
   * @returns {DraftViewListeners} What the 3D view reports.
   */
  #viewListeners() {
    return new DraftViewListeners(
      (selection) => this.#select(selection),
      (selection, placement) => this.#attempt(() => this.#place(selection, placement)),
      (identifier) => {
        if (identifier === this.#selection?.instance) this.#renderSelection(this.#state.draft);
        if (this.#view.isLoading()) return;
        if (this.#framePending) this.#frameWhenShown();
        if (this.#readyMessage !== null) this.#status(this.#readyMessage);
      },
      (error) => this.#status(error.message ?? String(error), true),
    );
  }
}
