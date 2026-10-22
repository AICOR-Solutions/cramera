/**
 * A copy of the draft being edited in the browser's storage, so a reload does not lose
 * unsaved work.
 */

import { DraftRecordKey } from '../../../protocol.js';

/**
 * The storage key of the copy.
 */
export const RECOVERY_KEY = 'cramera.scene-builder.recovery';

// %% recovery

export class DraftRecovery {
  /**
   * The browser's storage, `window.localStorage`.
   * @type {Storage}
   */
  #storage;

  /**
   * @param {Storage} storage The browser's storage.
   */
  constructor(storage) {
    this.#storage = storage;
  }

  /**
   * @param {Object} draft The draft being edited.
   * @param {string|null} identifier The identity of the saved draft it continues, or null.
   */
  keep(draft, identifier) {
    this.#storage.setItem(RECOVERY_KEY, JSON.stringify({ [DraftRecordKey.DOCUMENT]: draft, [DraftRecordKey.IDENTIFIER]: identifier }));
  }

  /**
   * @returns {{draft: Object, identifier: (string|null)}|null} The kept draft, or null
   *   when none is kept.
   */
  restore() {
    const text = this.#storage.getItem(RECOVERY_KEY);
    if (text === null) return null;
    const record = JSON.parse(text);
    const identifier = record[DraftRecordKey.IDENTIFIER];
    return { draft: record[DraftRecordKey.DOCUMENT], identifier: typeof identifier === 'string' ? identifier : null };
  }

  /**
   * Forget the kept draft, after it turned out unreadable.
   */
  forget() {
    this.#storage.removeItem(RECOVERY_KEY);
  }
}
