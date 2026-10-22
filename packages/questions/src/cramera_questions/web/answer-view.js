/**
 * An answer to a query: the query read back as English, its rows as a table, and a
 * way to replay the moment a row is about.
 */

import { AnswerColumn, QueryAnswerKey, ReplayWindowKey, VerbalizationKey } from '../../protocol.js';

/**
 * The columns that describe a row rather than hold a value, shown first.
 */
const DESCRIBING_COLUMNS = Object.freeze([AnswerColumn.ENTITY, AnswerColumn.TYPE]);

/**
 * The headings of the describing columns.
 */
const DESCRIBING_HEADINGS = Object.freeze({ [AnswerColumn.ENTITY]: 'Entity', [AnswerColumn.TYPE]: 'Type' });

// %% view

export class AnswerView {
  /**
   * The answer's element.
   * @type {HTMLElement}
   */
  element;

  /**
   * Called with a row's replay window when a person asks to replay it.
   * @type {function(Object): void}
   */
  #onReplay;

  /**
   * @param {Document} document The page.
   * @param {function(Object): void} onReplay Called with a row's replay window.
   */
  constructor(document, onReplay) {
    this.element = document.createElement('div');
    this.element.className = 'answer';
    this.#onReplay = onReplay;
  }

  /**
   * @param {Object} answer A query answer.
   */
  show(answer) {
    if (answer[QueryAnswerKey.OK] === false) {
      this.message(answer[QueryAnswerKey.ERROR] ?? 'The query could not be answered.', true);
      return;
    }
    const document = this.element.ownerDocument;
    const parts = [];
    const wording = answer[QueryAnswerKey.VERBALIZATION]?.[VerbalizationKey.TEXT];
    if (wording) {
      const reading = document.createElement('p');
      reading.className = 'reading';
      reading.textContent = wording;
      parts.push(reading);
    }
    const rows = answer[QueryAnswerKey.ROWS] ?? [];
    const count = document.createElement('p');
    count.className = 'count';
    count.textContent = `${answer[QueryAnswerKey.COUNT] ?? rows.length} ${rows.length === 1 ? 'answer' : 'answers'}${answer[QueryAnswerKey.MORE] ? ', more than shown' : ''}`;
    parts.push(count);
    if (rows.length) parts.push(this.#table(rows, answer[QueryAnswerKey.REPLAY] ?? []));
    this.element.replaceChildren(...parts);
  }

  /**
   * @param {string} text What to say instead of an answer.
   * @param {boolean} failed Whether it reports a failure.
   */
  message(text, failed = false) {
    const message = this.element.ownerDocument.createElement('p');
    message.className = failed ? 'error' : 'empty';
    message.textContent = text;
    this.element.replaceChildren(message);
  }

  /**
   * @param {Array<Object>} rows The answer rows.
   * @param {Array<Object|null>} replay The replay window of each row.
   * @returns {HTMLElement} The rows as a table.
   */
  #table(rows, replay) {
    const document = this.element.ownerDocument;
    const valueColumns = [...new Set(rows.flatMap((row) => Object.keys(row)))].filter((column) => !DESCRIBING_COLUMNS.includes(column));
    const columns = [...DESCRIBING_COLUMNS.filter((column) => rows.some((row) => column in row)), ...valueColumns];
    const table = document.createElement('table');
    const head = document.createElement('tr');
    for (const column of [...columns, '']) {
      const cell = document.createElement('th');
      cell.textContent = DESCRIBING_HEADINGS[column] ?? column;
      head.append(cell);
    }
    table.append(head);
    rows.forEach((row, position) => {
      const line = document.createElement('tr');
      for (const column of columns) {
        const cell = document.createElement('td');
        cell.textContent = row[column] === undefined ? '' : String(row[column]);
        line.append(cell);
      }
      const action = document.createElement('td');
      const window = replay[position];
      if (window) {
        const button = document.createElement('button');
        button.textContent = 'Replay';
        button.title = `Frames ${window[ReplayWindowKey.START]} to ${window[ReplayWindowKey.END]}`;
        button.addEventListener('click', () => this.#onReplay(window));
        action.append(button);
      }
      line.append(action);
      table.append(line);
    });
    return table;
  }
}
