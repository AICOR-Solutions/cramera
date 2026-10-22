/**
 * The builder's menus: the header with the draft's name, history and saving, the
 * drafts section to start, open, import and export drafts and to upload a scanned
 * room, and the view's toolbar.
 */

import { DraftSummaryKey, IndexEntryKey, PointCloudFormat } from '../../../protocol.js';
import { BuilderAction } from './elements.js';
import { TransformMode } from './draft-view.js';

/**
 * The units a scanned room may be measured in, by the metres in one unit.
 */
export const SourceUnit = Object.freeze({ METRES: 1, CENTIMETRES: 0.01, MILLIMETRES: 0.001 });

/**
 * The text of each source unit.
 */
const UNIT_LABELS = Object.freeze({
  [SourceUnit.METRES]: 'Metres',
  [SourceUnit.CENTIMETRES]: 'Centimetres',
  [SourceUnit.MILLIMETRES]: 'Millimetres',
});

/**
 * The text of each transform mode.
 */
const MODE_LABELS = Object.freeze({
  [TransformMode.MOVE]: 'Move',
  [TransformMode.ROTATE]: 'Rotate',
  [TransformMode.SCALE]: 'Scale',
});

/**
 * The selects' choice of nothing.
 */
const NOTHING = '';

/**
 * The file types the draft import accepts.
 */
const DRAFT_FILES = '.json,application/json';

// %% actions

/**
 * What the menus ask of the page.
 */
export class MenuActions {
  /**
   * @param {Object} callbacks The callbacks, by name: `rename(name)`, `undo()`,
   *   `redo()`, `save(copy)`, `newDraft()`, `openScene(scene)`, `loadDraft(identifier)`,
   *   `importFile(file)`, `exportDraft()`, `upload(file, metres)`, `setMode(mode)`,
   *   `frameSelection()` and `frameAll()`.
   */
  constructor(callbacks) {
    /**
     * Renames the draft.
     * @type {function(string): void}
     */
    this.rename = callbacks.rename;
    /**
     * Undoes the last step.
     * @type {function(): void}
     */
    this.undo = callbacks.undo;
    /**
     * Redoes the last undone step.
     * @type {function(): void}
     */
    this.redo = callbacks.redo;
    /**
     * Saves the draft, as a new draft when given true.
     * @type {function(boolean): void}
     */
    this.save = callbacks.save;
    /**
     * Starts an empty draft.
     * @type {function(): void}
     */
    this.newDraft = callbacks.newDraft;
    /**
     * Starts a draft from a scene.
     * @type {function(string): void}
     */
    this.openScene = callbacks.openScene;
    /**
     * Opens a saved draft.
     * @type {function(string): void}
     */
    this.loadDraft = callbacks.loadDraft;
    /**
     * Opens a draft file.
     * @type {function(File): void}
     */
    this.importFile = callbacks.importFile;
    /**
     * Writes the draft to a file.
     * @type {function(): void}
     */
    this.exportDraft = callbacks.exportDraft;
    /**
     * Uploads a point cloud measured in a unit of the given metres and places it.
     * @type {function(File, number): void}
     */
    this.upload = callbacks.upload;
    /**
     * Chooses what the handles change.
     * @type {function(string): void}
     */
    this.setMode = callbacks.setMode;
    /**
     * Looks at the selection.
     * @type {function(): void}
     */
    this.frameSelection = callbacks.frameSelection;
    /**
     * Looks at every instance.
     * @type {function(): void}
     */
    this.frameAll = callbacks.frameAll;
  }
}

// %% header

export class BuilderHeader {
  /**
   * The draft's name.
   * @type {HTMLInputElement}
   */
  #name;

  /**
   * Whether the draft is saved.
   * @type {HTMLElement}
   */
  #saved;

  /**
   * The undo button.
   * @type {HTMLButtonElement}
   */
  #undo;

  /**
   * The redo button.
   * @type {HTMLButtonElement}
   */
  #redo;

  /**
   * The header's element.
   * @type {HTMLElement}
   */
  element;

  /**
   * @param {import('./elements.js').Elements} elements Builds the header.
   * @param {MenuActions} actions What the header asks of the page.
   * @param {string} viewerUrl The viewer's page.
   */
  constructor(elements, actions, viewerUrl) {
    this.element = elements.create('header', 'bar builder-bar');
    const brand = elements.create('a', 'brand', 'cramera');
    brand.href = viewerUrl;
    const title = elements.create('span', 'builder-title', 'Scene builder');
    this.#name = elements.input('text', BuilderAction.RENAME_DRAFT, () => actions.rename(this.#name.value.trim()));
    this.#name.setAttribute('aria-label', 'Scene name');
    this.#saved = elements.create('span', 'muted save-state');
    this.#undo = elements.button('Undo', BuilderAction.UNDO, () => actions.undo());
    this.#redo = elements.button('Redo', BuilderAction.REDO, () => actions.redo());
    const save = elements.button('Save draft', BuilderAction.SAVE, () => actions.save(false));
    save.classList.add('primary');
    const actionsRow = elements.create('div', 'button-row');
    actionsRow.append(this.#undo, this.#redo, elements.button('Save a copy', BuilderAction.SAVE_COPY, () => actions.save(true)), save);
    this.element.append(brand, title, this.#name, this.#saved, actionsRow);
  }

  /**
   * @param {string} name The draft's name.
   * @param {boolean} canUndo Whether a step can be undone.
   * @param {boolean} canRedo Whether an undone step can be redone.
   * @param {boolean} saved Whether the draft is saved as shown.
   */
  show(name, canUndo, canRedo, saved) {
    this.#name.value = name;
    this.#undo.disabled = !canUndo;
    this.#redo.disabled = !canRedo;
    this.#saved.textContent = saved ? 'Saved' : 'Unsaved changes';
  }
}

// %% drafts

export class DraftMenu {
  /**
   * Builds the menu.
   * @type {import('./elements.js').Elements}
   */
  #elements;

  /**
   * The scenes a draft can start from.
   * @type {HTMLSelectElement}
   */
  #scenes;

  /**
   * The saved drafts.
   * @type {HTMLSelectElement}
   */
  #drafts;

  /**
   * The menu's element.
   * @type {HTMLElement}
   */
  element;

  /**
   * @param {import('./elements.js').Elements} elements Builds the menu.
   * @param {MenuActions} actions What the menu asks of the page.
   */
  constructor(elements, actions) {
    this.#elements = elements;
    this.element = elements.create('section', 'builder-section drafts');
    this.#scenes = elements.select(BuilderAction.OPEN_SCENE, () => {
      if (this.#scenes.value !== NOTHING) actions.openScene(this.#scenes.value);
    });
    this.#drafts = elements.select(BuilderAction.LOAD_DRAFT, () => {
      if (this.#drafts.value !== NOTHING) actions.loadDraft(this.#drafts.value);
    });
    const draftFile = elements.input('file', BuilderAction.IMPORT, () => {
      if (draftFile.files[0]) actions.importFile(draftFile.files[0]);
      draftFile.value = '';
    });
    draftFile.accept = DRAFT_FILES;
    draftFile.hidden = true;
    const units = elements.select(BuilderAction.UPLOAD, () => {});
    elements.options(
      units,
      Object.values(SourceUnit).map((metres) => ({ value: String(metres), label: UNIT_LABELS[metres] })),
      String(SourceUnit.METRES),
    );
    const cloudFile = elements.input('file', BuilderAction.UPLOAD, () => {
      if (cloudFile.files[0]) actions.upload(cloudFile.files[0], Number(units.value));
      cloudFile.value = '';
    });
    cloudFile.accept = Object.values(PointCloudFormat).map((format) => `.${format}`).join(',');
    cloudFile.hidden = true;
    const draftButtons = elements.create('div', 'button-row');
    draftButtons.append(
      elements.button('New scene', BuilderAction.NEW, () => actions.newDraft()),
      elements.button('Import JSON', BuilderAction.IMPORT, () => draftFile.click()),
      elements.button('Export JSON', BuilderAction.EXPORT, () => actions.exportDraft()),
    );
    this.element.append(
      elements.create('h2', '', 'Drafts'),
      draftButtons,
      draftFile,
      elements.label('Start from a scene', this.#scenes),
      elements.label('Open a saved draft', this.#drafts),
      elements.create('h2', '', 'Scanned room'),
      elements.create('p', 'muted', 'A PLY or PCD point cloud, shown as a locked reference to arrange models over.'),
      elements.label('Measured in', units),
      elements.button('Load a point cloud', BuilderAction.UPLOAD, () => cloudFile.click()),
      cloudFile,
    );
  }

  /**
   * @param {Array<Object>} scenes The scenes a draft can start from, as the index lists them.
   * @param {Array<Object>} drafts The saved drafts' summaries.
   */
  show(scenes, drafts) {
    this.#elements.options(
      this.#scenes,
      [{ value: NOTHING, label: 'Choose a scene…' }, ...scenes.map((scene) => ({ value: scene[IndexEntryKey.NAME], label: scene[IndexEntryKey.NAME] }))],
      NOTHING,
    );
    this.#elements.options(
      this.#drafts,
      [{ value: NOTHING, label: 'Choose a draft…' }, ...drafts.map((draft) => ({ value: draft[DraftSummaryKey.IDENTIFIER], label: draft[DraftSummaryKey.NAME] }))],
      NOTHING,
    );
  }
}

// %% toolbar

export class ViewToolbar {
  /**
   * The mode buttons by `TransformMode` value.
   * @type {Map<string, HTMLButtonElement>}
   */
  #modes = new Map();

  /**
   * The toolbar's element.
   * @type {HTMLElement}
   */
  element;

  /**
   * @param {import('./elements.js').Elements} elements Builds the toolbar.
   * @param {MenuActions} actions What the toolbar asks of the page.
   */
  constructor(elements, actions) {
    this.element = elements.create('div', 'view-toolbar');
    const modes = elements.create('div', 'button-row');
    modes.setAttribute('role', 'group');
    modes.setAttribute('aria-label', 'Transform');
    for (const mode of Object.values(TransformMode)) {
      const button = elements.button(MODE_LABELS[mode], BuilderAction.MODE, () => actions.setMode(mode));
      button.dataset.mode = mode;
      this.#modes.set(mode, button);
      modes.append(button);
    }
    const framing = elements.create('div', 'button-row');
    framing.append(
      elements.button('Frame selected', BuilderAction.FRAME_SELECTION, () => actions.frameSelection()),
      elements.button('Frame all', BuilderAction.FRAME_ALL, () => actions.frameAll()),
    );
    this.element.append(modes, framing);
    this.show(TransformMode.MOVE, false);
  }

  /**
   * @param {string} mode The current `TransformMode` value.
   * @param {boolean} enabled Whether the selection can be transformed.
   */
  show(mode, enabled) {
    for (const [value, button] of this.#modes) {
      button.setAttribute('aria-pressed', String(value === mode));
      button.disabled = !enabled;
    }
  }
}
