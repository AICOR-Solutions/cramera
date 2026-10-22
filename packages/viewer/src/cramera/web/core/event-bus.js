/**
 * The event bus the parts of the application talk through.
 *
 * Event names are the members of `ViewerEvent` in `protocol.js`, so plugins and
 * built-in parts use the same names.
 */

// %% bus

export class EventBus {
  /**
   * The listeners of each event name.
   * @type {Map<string, Set<function(*): void>>}
   */
  #listeners = new Map();

  /**
   * Call `listener` with the payload of every later `event`.
   * @param {string} event A `ViewerEvent` value.
   * @param {function(*): void} listener Called with the payload.
   * @returns {function(): void} Removes the listener again.
   */
  subscribe(event, listener) {
    if (!this.#listeners.has(event)) this.#listeners.set(event, new Set());
    this.#listeners.get(event).add(listener);
    return () => this.#listeners.get(event).delete(listener);
  }

  /**
   * Call every listener of `event` with `payload`, in subscription order.
   * @param {string} event A `ViewerEvent` value.
   * @param {*} payload What the event carries.
   */
  publish(event, payload) {
    for (const listener of [...(this.#listeners.get(event) ?? [])]) listener(payload);
  }

  /**
   * @param {string} event A `ViewerEvent` value.
   * @returns {number} How many listeners `event` has.
   */
  listenerCount(event) {
    return this.#listeners.get(event)?.size ?? 0;
  }
}
