/**
 * The instances of the draft, in the order they were placed; clicking one selects it.
 */

import { DraftKey, InstanceKey, ResourceKey } from '../../../protocol.js';
import { BuilderAction, Elements } from './elements.js';

/**
 * The tag shown for an instance whose resource the catalog does not offer.
 */
export const MISSING_RESOURCE = 'missing';

// %% list

export class InstanceList {
  /**
   * Builds the listed rows and owns their listeners, replaced on every listing.
   * @type {Elements}
   */
  #rows;

  /**
   * Called with the identity of a clicked instance.
   * @type {function(string): void}
   */
  #onSelect;

  /**
   * How many instances the draft holds.
   * @type {HTMLElement}
   */
  #count;

  /**
   * The listed instances.
   * @type {HTMLElement}
   */
  #list;

  /**
   * The list's element.
   * @type {HTMLElement}
   */
  element;

  /**
   * @param {Elements} elements Builds the list's frame.
   * @param {function(string): void} onSelect Called with the identity of a clicked instance.
   */
  constructor(elements, onSelect) {
    this.#rows = new Elements(elements.document);
    this.#onSelect = onSelect;
    this.element = elements.create('section', 'builder-section instances');
    const heading = elements.create('div', 'section-heading');
    this.#count = elements.create('span', 'muted', '0');
    heading.append(elements.create('h2', '', 'Instances'), this.#count);
    this.#list = elements.create('div', 'instance-list');
    this.element.append(heading, this.#list);
  }

  /**
   * @param {Object} draft The draft.
   * @param {string|null} selected The selected instance's identity.
   * @param {function(string): (Object|undefined)} resource The catalog's resource of an identifier.
   */
  show(draft, selected, resource) {
    this.#rows.dispose();
    const instances = draft[DraftKey.INSTANCES];
    this.#count.textContent = String(instances.length);
    const rows = instances.map((instance) => {
      const identifier = instance[InstanceKey.IDENTIFIER];
      const row = this.#rows.button('', BuilderAction.SELECT, () => this.#onSelect(identifier));
      row.className = 'instance-row';
      row.setAttribute('aria-selected', String(identifier === selected));
      if (instance[InstanceKey.DESCRIPTION]) row.title = instance[InstanceKey.DESCRIPTION];
      const category = resource(instance[InstanceKey.ASSET])?.[ResourceKey.CATEGORY] ?? MISSING_RESOURCE;
      row.append(this.#rows.create('span', 'instance-tag', category), this.#rows.create('span', 'instance-name', instance[InstanceKey.NAME]));
      return row;
    });
    if (rows.length === 0) rows.push(this.#rows.create('p', 'muted', 'Place a resource or open a scene to start.'));
    this.#list.replaceChildren(...rows);
  }

  /**
   * Remove the listeners of the listed rows.
   */
  dispose() {
    this.#rows.dispose();
  }
}
