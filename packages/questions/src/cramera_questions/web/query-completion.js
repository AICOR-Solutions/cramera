/**
 * Hints while a query is written: the names a query of the chosen scope may use (its
 * ready-made variables, the query language's factories and every workspace class), the
 * members after a dot, and the fields a match pattern such as `a(Arm)(` may constrain.
 * Arrow keys choose a hint, Tab or Enter takes it, Escape closes the list and
 * Ctrl+Space opens it on an empty word.
 */

/**
 * The most hints the list shows at once.
 */
export const HINT_LIMIT = 14;

/**
 * The order kinds of names are offered in when they match equally well.
 */
const KIND_ORDER = Object.freeze({ variable: 0, factory: 1, entity_type: 2, field: 3, member: 3, class: 4 });

/**
 * What a hint's badge says for each kind.
 */
const KIND_BADGE = Object.freeze({ variable: 'var', factory: 'fn', entity_type: 'type', class: 'class', field: 'field', member: 'attr' });

/**
 * The word being written, and what it follows.
 */
const WORD_BEFORE_CURSOR = /([A-Za-z_][\w]*)?$/;
const MEMBER_BEFORE_CURSOR = /([A-Za-z_][\w]*)\.([A-Za-z_]\w*)?$/;
const PATTERN_FIELD_BEFORE_CURSOR = /\b(?:a|an|the|every_is|none_is|entity|variable)\(\s*([A-Z]\w*)\s*\)\(\s*(?:[\w]+\s*=\s*[^,()]*(?:\([^()]*\))*[^,()]*,\s*)*([A-Za-z_]\w*)?$/;

export class QueryCompletion {
  /**
   * The list of hints.
   * @type {HTMLUListElement}
   */
  element;

  /** @type {HTMLTextAreaElement} */
  #input;

  /**
   * Fetches the names a query may use: `vocabulary()` and `members(name)`.
   * @type {{vocabulary: function(): Promise<Array<Object>>, members: function(string): Promise<Array<Object>>}}
   */
  #source;

  /** @type {Array<Object>|null} */
  #vocabulary = null;

  /** @type {Map<string, Promise<Array<Object>>>} */
  #members = new Map();

  /** @type {Array<{entry: Object, start: number, insert: string}>} */
  #shown = [];

  #chosen = 0;

  /** The newest request, so an older answer never replaces a newer list. */
  #request = 0;

  /**
   * @param {HTMLTextAreaElement} input The query box.
   * @param {Function} onRun Runs the query (Ctrl+Enter).
   */
  constructor(input, onRun) {
    this.#input = input;
    const document = input.ownerDocument;
    this.element = document.createElement('ul');
    this.element.className = 'query-hints';
    this.element.hidden = true;
    this.element.setAttribute('role', 'listbox');
    input.addEventListener('input', () => this.update());
    input.addEventListener('click', () => this.update());
    input.addEventListener('blur', () => setTimeout(() => this.close(), 150));
    input.addEventListener('keydown', (event) => this.#onKey(event, onRun));
  }

  /**
   * Ask a new source for names, as when another scene or scope is chosen.
   * @param {Object|null} source Where the names come from, or null to offer none.
   */
  useSource(source) {
    this.#source = source;
    this.#vocabulary = null;
    this.#members.clear();
    this.close();
    source?.vocabulary().then((entries) => {
      if (this.#source === source) this.#vocabulary = entries;
    }).catch(() => {});
  }

  /**
   * @returns {number} How many names the chosen scope offers, or 0 before they arrived.
   */
  get size() {
    return this.#vocabulary?.length ?? 0;
  }

  /**
   * Show the hints for the word before the cursor.
   * @param {boolean} evenWithoutWord Whether to list hints for an empty word.
   */
  async update(evenWithoutWord = false) {
    if (!this.#source) return;
    const request = ++this.#request;
    const text = this.#input.value.slice(0, this.#input.selectionStart);
    const hints = await this.#hintsFor(text, evenWithoutWord);
    if (request !== this.#request) return;
    this.#show(hints);
  }

  close() {
    this.element.hidden = true;
    this.#shown = [];
  }

  /**
   * @param {string} text The query up to the cursor.
   * @param {boolean} evenWithoutWord Whether an empty word gets hints.
   * @returns {Promise<Array<Object>>} The hints, each with the text it replaces.
   */
  async #hintsFor(text, evenWithoutWord) {
    const field = PATTERN_FIELD_BEFORE_CURSOR.exec(text);
    if (field) {
      const prefix = field[2] ?? '';
      const members = await this.#membersOf(field[1]);
      return this.#ranked(members, prefix).map((entry) => ({ entry, start: text.length - prefix.length, insert: `${entry.name}=` }));
    }
    const member = MEMBER_BEFORE_CURSOR.exec(text);
    if (member) {
      const prefix = member[2] ?? '';
      const owner = this.#ownerName(text.slice(0, text.length - prefix.length - 1), member[1]);
      const members = await this.#membersOf(owner);
      return this.#ranked(members, prefix).map((entry) => ({ entry, start: text.length - prefix.length, insert: entry.name }));
    }
    const prefix = WORD_BEFORE_CURSOR.exec(text)[1] ?? '';
    if (!prefix && !evenWithoutWord) return [];
    return this.#ranked(this.#vocabulary ?? [], prefix).map((entry) => ({ entry, start: text.length - prefix.length, insert: entry.name }));
  }

  /**
   * The name whose members follow a dot: a pattern's class when the dot follows a
   * pattern such as `a(Arm)`, else the word before the dot.
   * @param {string} before The query up to the dot.
   * @param {string} word The word before the dot.
   * @returns {string} The name to ask the members of.
   */
  #ownerName(before, word) {
    const pattern = /\b(?:a|an|the|entity|variable)\(\s*([A-Z]\w*)\s*\)$/.exec(before);
    return pattern ? pattern[1] : word;
  }

  /**
   * @param {string} name A variable's or class's name.
   * @returns {Promise<Array<Object>>} Its members.
   */
  #membersOf(name) {
    if (!this.#members.has(name)) {
      this.#members.set(name, this.#source.members(name).catch(() => []));
    }
    return this.#members.get(name);
  }

  /**
   * @param {Array<Object>} entries Names on offer.
   * @param {string} prefix The word written so far.
   * @returns {Array<Object>} Those starting with it (any case), best first.
   */
  #ranked(entries, prefix) {
    const lower = prefix.toLowerCase();
    const matching = entries.filter((entry) => entry.name.toLowerCase().startsWith(lower) && entry.name !== prefix);
    const contained = lower.length >= 2 ? entries.filter((entry) => !entry.name.toLowerCase().startsWith(lower) && entry.name.toLowerCase().includes(lower)) : [];
    const order = (entry) => KIND_ORDER[entry.kind] ?? 5;
    const byKind = (a, b) => order(a) - order(b) || a.name.length - b.name.length || a.name.localeCompare(b.name);
    return [...matching.sort(byKind), ...contained.sort(byKind)].slice(0, HINT_LIMIT);
  }

  /**
   * @param {Array<Object>} hints The hints to list.
   */
  #show(hints) {
    this.#shown = hints;
    this.#chosen = 0;
    if (!hints.length) {
      this.close();
      return;
    }
    const document = this.element.ownerDocument;
    this.element.replaceChildren(
      ...hints.map((hint, index) => {
        const item = document.createElement('li');
        item.setAttribute('role', 'option');
        const badge = document.createElement('span');
        badge.className = `hint-kind kind-${hint.entry.kind}`;
        badge.textContent = KIND_BADGE[hint.entry.kind] ?? hint.entry.kind;
        const name = document.createElement('span');
        name.className = 'hint-name';
        name.textContent = hint.insert;
        const detail = document.createElement('span');
        detail.className = 'hint-detail';
        detail.textContent = hint.entry.detail || hint.entry.module || '';
        item.append(badge, name, detail);
        item.addEventListener('mousedown', (event) => {
          event.preventDefault();
          this.#take(index);
        });
        return item;
      }),
    );
    this.element.hidden = false;
    this.#highlight();
  }

  #highlight() {
    [...this.element.children].forEach((item, index) => item.classList.toggle('chosen', index === this.#chosen));
    this.element.children[this.#chosen]?.scrollIntoView({ block: 'nearest' });
  }

  /**
   * Replace the word before the cursor by a hint.
   * @param {number} index The hint's position in the list.
   */
  #take(index) {
    const hint = this.#shown[index];
    if (!hint) return;
    const input = this.#input;
    const end = input.selectionStart;
    input.value = input.value.slice(0, hint.start) + hint.insert + input.value.slice(end);
    const cursor = hint.start + hint.insert.length;
    input.setSelectionRange(cursor, cursor);
    this.close();
    input.focus();
    if (hint.insert.endsWith('=')) return;
    this.update();
  }

  /**
   * @param {KeyboardEvent} event A key pressed in the query box.
   * @param {Function} onRun Runs the query.
   */
  #onKey(event, onRun) {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      this.close();
      onRun();
      return;
    }
    if (event.key === ' ' && event.ctrlKey) {
      event.preventDefault();
      this.update(true);
      return;
    }
    if (this.element.hidden) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const step = event.key === 'ArrowDown' ? 1 : -1;
      this.#chosen = (this.#chosen + step + this.#shown.length) % this.#shown.length;
      this.#highlight();
    } else if (event.key === 'Tab' || event.key === 'Enter') {
      event.preventDefault();
      this.#take(this.#chosen);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      this.close();
    }
  }
}
