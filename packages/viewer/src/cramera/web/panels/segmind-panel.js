/**
 * The Segmind panel: what segmind's detectors saw during the run, in the order it
 * happened. Each event says when it happened, what sort of event it is and which objects
 * it is about; choosing it lights those objects up in the 3D view and, in a recording,
 * shows its moment. The event the playback passed last is marked, and the sorts of
 * event can be shown or hidden here and on the timeline together, which marks each
 * event shown at its frame.
 */

import { DetectedEventKey, DetectedEventKind, DetectedEventsKey, SceneKey, ViewerEvent } from '../protocol.js';
import { EventMark, formatSeconds } from '../playback/timeline-view.js';
import { SidePanel } from './panel-host.js';

/**
 * What the panel says while the shown scene lists no event.
 */
export const NO_EVENTS = 'Segmind detected nothing in this scene. Record a run with segmind watching (cramera-onboard --detect-events, or CRAMERA_DETECT_EVENTS=1 for a live run) and what it saw appears here.';

/**
 * What the panel says about where the events come from.
 */
export const EVENT_SOURCES = 'Events segmind’s detectors saw while the run was recorded. Choose one to light its objects up and show its moment.';

/**
 * What the button says that lights up each event as the playback passes it.
 */
export const FOLLOW_TEXT = 'Light up events during playback';

/**
 * The words the panel names each sort of event with, in the order the sorts are listed.
 */
export const KIND_LABELS = Object.freeze({
  [DetectedEventKind.PICK_AND_PLACE]: 'Pick and place',
  [DetectedEventKind.GRASP]: 'Grasp',
  [DetectedEventKind.SUPPORT]: 'Support',
  [DetectedEventKind.CONTAINMENT]: 'Containment',
  [DetectedEventKind.CONTACT]: 'Contact',
  [DetectedEventKind.MOTION]: 'Motion',
  [DetectedEventKind.OTHER]: 'Other',
});

/**
 * The state of an event of a recording, relative to the frame shown.
 */
export const EventMoment = Object.freeze({
  /** It happened before the event the playback passed last. */
  PAST: 'past',
  /** It is the event the playback passed last, or happened at the same frame. */
  CURRENT: 'current',
  /** The playback has not reached it yet. */
  FUTURE: 'future',
  /** It is placed on no frame. */
  UNPLACED: 'unplaced',
});

/**
 * Separates the words of a class name.
 */
const WORD_BOUNDARY = /(?<=[a-z0-9])(?=[A-Z])/g;

/**
 * The suffix every segmind event class name ends with.
 */
const EVENT_SUFFIX = 'Event';

/**
 * Finds the time of day in an ISO 8601 date and time.
 */
const TIME_OF_DAY = /T(\d{2}:\d{2}:\d{2})/;

// %% events

/**
 * @param {string} eventType An event's class name, such as `LossOfSupportEvent`.
 * @returns {string} The class name as words: `Loss of support`.
 */
export function eventLabel(eventType) {
  const words = eventType.replace(new RegExp(`${EVENT_SUFFIX}$`), '').split(WORD_BOUNDARY);
  return words.map((word, position) => (position ? word.toLowerCase() : word)).join(' ');
}

/**
 * @param {string} bodyName A body's full name, such as `kitchen/milk`.
 * @returns {string} The name without the prefixes it is filed under: `milk`.
 */
export function shortName(bodyName) {
  return bodyName.split('/').pop();
}

/**
 * @param {string} timestamp An ISO 8601 date and time.
 * @returns {string} Its time of day, such as `14:02:31`, or the timestamp itself when it
 *   names none.
 */
export function clockTime(timestamp) {
  return TIME_OF_DAY.exec(timestamp)?.[1] ?? timestamp;
}

/**
 * One event segmind detected.
 */
export class SegmindEvent {
  /**
   * @param {Object} parts The event's parts: `name`, `type` (its class name), `label`
   *   (that name as words), `kind` (a `DetectedEventKind` value), `frame` (or null),
   *   `timestamp`, `tracked` and `withObject` (body names, the second or null) and `keys`
   *   (what lights up).
   */
  constructor(parts) {
    Object.assign(this, parts);
  }
}

/**
 * @param {Array<Object>} described Events as a scene description or a live publisher
 *   lists them.
 * @returns {Array<SegmindEvent>} The events in the order they were listed.
 */
export function segmindEvents(described) {
  return described.map((event) => new SegmindEvent({
    name: event[DetectedEventKey.NAME],
    type: event[DetectedEventKey.EVENT_TYPE],
    label: eventLabel(event[DetectedEventKey.EVENT_TYPE]),
    kind: event[DetectedEventKey.KIND] ?? DetectedEventKind.OTHER,
    frame: event[DetectedEventKey.FRAME] ?? null,
    timestamp: event[DetectedEventKey.TIMESTAMP],
    tracked: event[DetectedEventKey.TRACKED_OBJECT] ?? null,
    withObject: event[DetectedEventKey.WITH_OBJECT] ?? null,
    keys: event[DetectedEventKey.KEYS] ?? [],
  }));
}

/**
 * @param {Array<SegmindEvent>} events Events of a recording.
 * @param {number} frame The frame shown.
 * @returns {Array<string>} The moment of each event relative to the frame.
 */
export function eventMoments(events, frame) {
  const reached = events.map((event) => event.frame).filter((placed) => placed !== null && placed <= frame);
  const latest = reached.length ? Math.max(...reached) : null;
  return events.map((event) => {
    if (event.frame === null) return EventMoment.UNPLACED;
    if (event.frame > frame) return EventMoment.FUTURE;
    return event.frame === latest ? EventMoment.CURRENT : EventMoment.PAST;
  });
}

// %% panel

export class SegmindPanel {
  /**
   * The panel.
   * @type {SidePanel}
   */
  panel;

  /**
   * The events shown, in the order they happened.
   * @type {Array<SegmindEvent>}
   */
  events = [];

  /**
   * The sorts of event hidden.
   * @type {Set<string>}
   */
  hidden = new Set();

  /**
   * The bus the panel lights objects up and requests frames on.
   * @type {import('../core/event-bus.js').EventBus}
   */
  #bus;

  /**
   * Called with the marks of the events shown whenever they change, so the timeline
   * shows them.
   * @type {function(Array<EventMark>): void}
   */
  #onMarks;

  /**
   * The names of the shown scene's objects, by key.
   * @type {Map<string, string>}
   */
  #names = new Map();

  /**
   * How many frames make one second of the shown recording, or null while the events
   * come from a live run.
   * @type {number|null}
   */
  #framesPerSecond = null;

  /**
   * The frame shown.
   * @type {number}
   */
  #frame = 0;

  /**
   * The frame of the event the playback passed last, so its objects light up once.
   * @type {number|null}
   */
  #litFrame = null;

  /**
   * What the live events shown were, so an unchanged answer is not shown again.
   * @type {string|null}
   */
  #liveSignature = null;

  /**
   * Whether the objects of each event light up as the playback passes it.
   * @type {boolean}
   */
  #following = false;

  /**
   * Switches lighting up each event as the playback passes it on and off.
   * @type {HTMLButtonElement}
   */
  #follow;

  /**
   * How many events of each sort there are, each switching its sort on and off; with
   * the light-up button it stays at the top of the panel while the list scrolls.
   * @type {HTMLElement}
   */
  #kinds;

  /**
   * The list of events.
   * @type {HTMLElement}
   */
  #list;

  /**
   * @param {Document} document The page.
   * @param {import('../core/event-bus.js').EventBus} bus The bus the panel lights objects
   *   up and requests frames on.
   * @param {function(Array<EventMark>): void} onMarks Called with the marks of the
   *   events shown whenever they change.
   */
  constructor(document, bus, onMarks = () => {}) {
    this.#bus = bus;
    this.#onMarks = onMarks;
    this.panel = new SidePanel('segmind', 'Segmind', document.createElement('section'));
    this.panel.element.classList.add('segmind');
    const sources = document.createElement('p');
    sources.className = 'muted';
    sources.textContent = EVENT_SOURCES;
    this.#kinds = document.createElement('div');
    this.#kinds.className = 'segmind-kinds';
    this.#kinds.setAttribute('role', 'group');
    this.#kinds.setAttribute('aria-label', 'Sorts of event shown');
    this.#follow = document.createElement('button');
    this.#follow.type = 'button';
    this.#follow.className = 'segmind-follow';
    this.#follow.textContent = FOLLOW_TEXT;
    this.#follow.title = 'Light up the objects of each event as the playback passes it';
    this.#follow.setAttribute('aria-pressed', 'false');
    this.#follow.addEventListener('click', () => this.setFollowing(!this.#following));
    const controls = document.createElement('div');
    controls.className = 'segmind-controls';
    controls.append(this.#kinds, this.#follow);
    this.#list = document.createElement('ol');
    this.#list.className = 'segmind-events';
    this.panel.element.append(sources, controls, this.#list);
    bus.subscribe(ViewerEvent.FRAME_CHANGED, (frame) => this.setFrame(frame));
    this.showEvents([]);
  }

  /**
   * @param {import('../scene/scene-loader.js').LoadedScene} scene The shown scene.
   */
  show(scene) {
    this.#names = new Map(scene.objects.named().map(({ key, name }) => [key, name]));
    this.#framesPerSecond = scene.frames.framesPerSecond;
    this.#frame = 0;
    this.#liveSignature = null;
    this.showEvents(segmindEvents(scene.description[SceneKey.DETECTED_EVENTS] ?? []));
  }

  /**
   * @param {Object} detected The live publisher's events, a `DetectedEvents` document;
   *   the same events as before change nothing.
   */
  showLive(detected) {
    const events = segmindEvents(detected[DetectedEventsKey.EVENTS] ?? []);
    const signature = events.map((event) => `${event.timestamp} ${event.name}`).join('\n');
    if (this.#framesPerSecond === null && signature === this.#liveSignature) return;
    this.#framesPerSecond = null;
    this.#liveSignature = signature;
    this.showEvents(events);
  }

  /**
   * @param {Array<SegmindEvent>} events The events to show.
   */
  showEvents(events) {
    this.events = events;
    this.#litFrame = null;
    this.#follow.hidden = this.#framesPerSecond === null || !events.length;
    this.#renderKinds();
    this.#renderList();
    this.setFrame(this.#frame);
    this.#onMarks(this.marks());
  }

  /**
   * @returns {Array<SegmindEvent>} The events of the sorts not hidden.
   */
  shown() {
    return this.events.filter((event) => !this.hidden.has(event.kind));
  }

  /**
   * @returns {Array<EventMark>} A timeline mark for every event shown that is placed on a
   *   frame of the shown recording; none for a live run.
   */
  marks() {
    if (this.#framesPerSecond === null) return [];
    return this.shown()
      .filter((event) => event.frame !== null)
      .map((event) => new EventMark(event.frame, event.kind, `${this.timeOf(event)} ${event.label}: ${this.objectsOf(event)}`));
  }

  /**
   * Show or hide a sort of event, here and on the timeline.
   * @param {string} kind A `DetectedEventKind` value.
   * @param {boolean} shown Whether events of that sort are shown.
   */
  setKindShown(kind, shown) {
    if (shown) this.hidden.delete(kind);
    else this.hidden.add(kind);
    this.#renderKinds();
    for (const entry of this.#list.children) {
      if (entry.dataset.kind) entry.hidden = this.hidden.has(entry.dataset.kind);
    }
    this.#onMarks(this.marks());
  }

  /**
   * @returns {boolean} Whether the objects of each event light up as the playback
   *   passes it.
   */
  get following() {
    return this.#following;
  }

  /**
   * Switch lighting up each event as the playback passes it on, which lights up the
   * event passed last at once, or off, which puts out what it lit up.
   * @param {boolean} following Whether the objects of each event light up as the
   *   playback passes it.
   */
  setFollowing(following) {
    const lit = this.#litFrame !== null;
    this.#following = following;
    this.#follow.setAttribute('aria-pressed', String(following));
    this.#litFrame = null;
    if (!following && lit) this.#bus.publish(ViewerEvent.ENTITY_HIGHLIGHTED, []);
    this.setFrame(this.#frame);
  }

  /**
   * Mark the events the playback passed and, when asked to, light up the objects of the
   * event it passed last and bring that event into view.
   * @param {number} frame The frame shown.
   */
  setFrame(frame) {
    this.#frame = frame;
    if (this.#framesPerSecond === null) return;
    const moments = eventMoments(this.events, frame);
    const entries = [...this.#list.children].filter((entry) => entry.dataset.kind);
    entries.forEach((entry, position) => { entry.dataset.moment = moments[position]; });
    if (!this.#following) return;
    const current = this.events
      .map((event, position) => ({ event, entry: entries[position] }))
      .filter(({ event }, position) => moments[position] === EventMoment.CURRENT && !this.hidden.has(event.kind));
    const frameOfCurrent = current.length ? current[0].event.frame : null;
    if (frameOfCurrent === this.#litFrame) return;
    this.#litFrame = frameOfCurrent;
    if (!current.length) return;
    this.#bus.publish(ViewerEvent.ENTITY_HIGHLIGHTED, [...new Set(current.flatMap(({ event }) => event.keys))]);
    current[0].entry.scrollIntoView({ block: 'nearest' });
  }

  /**
   * Light up an event's objects and, in a recording, show its moment.
   * @param {SegmindEvent} event An event shown.
   */
  choose(event) {
    this.#bus.publish(ViewerEvent.ENTITY_HIGHLIGHTED, event.keys);
    if (this.#framesPerSecond !== null && event.frame !== null) this.#bus.publish(ViewerEvent.FRAME_REQUESTED, event.frame);
  }

  /**
   * @param {SegmindEvent} event An event.
   * @returns {string} When it happened: the time into the recording, or the time of day
   *   for a live run or an event placed on no frame.
   */
  timeOf(event) {
    if (this.#framesPerSecond && event.frame !== null) return formatSeconds(event.frame / this.#framesPerSecond);
    return clockTime(event.timestamp);
  }

  /**
   * @param {SegmindEvent} event An event.
   * @returns {string} The objects it is about, by the names the scene shows them under
   *   without their prefixes.
   */
  objectsOf(event) {
    const [trackedKey, withKey] = event.keys;
    const names = [];
    if (event.tracked) names.push(shortName(this.#names.get(trackedKey) ?? event.tracked));
    if (event.withObject) names.push(shortName(this.#names.get(withKey) ?? event.withObject));
    return names.join(' · ');
  }

  /**
   * Show a switch for every sort of event the scene lists, with how many there are.
   */
  #renderKinds() {
    const document = this.panel.element.ownerDocument;
    const counts = new Map();
    for (const event of this.events) counts.set(event.kind, (counts.get(event.kind) ?? 0) + 1);
    const buttons = Object.keys(KIND_LABELS)
      .filter((kind) => counts.has(kind))
      .map((kind) => {
        const shown = !this.hidden.has(kind);
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'segmind-kind';
        button.dataset.kind = kind;
        button.setAttribute('aria-pressed', String(shown));
        button.title = shown ? `Hide ${KIND_LABELS[kind].toLowerCase()} events` : `Show ${KIND_LABELS[kind].toLowerCase()} events`;
        button.textContent = `${KIND_LABELS[kind]} ${counts.get(kind)}`;
        button.addEventListener('click', () => this.setKindShown(kind, this.hidden.has(kind)));
        return button;
      });
    this.#kinds.replaceChildren(...buttons);
    this.#kinds.hidden = !buttons.length;
  }

  /**
   * Show an entry for every event, or the note that there is none.
   */
  #renderList() {
    const document = this.panel.element.ownerDocument;
    if (!this.events.length) {
      const empty = document.createElement('li');
      empty.className = 'empty';
      empty.textContent = NO_EVENTS;
      this.#list.replaceChildren(empty);
      return;
    }
    this.#list.replaceChildren(...this.events.map((event) => this.#entry(document, event)));
  }

  /**
   * @param {Document} document The page.
   * @param {SegmindEvent} event An event.
   * @returns {HTMLElement} The event's entry.
   */
  #entry(document, event) {
    const entry = document.createElement('li');
    entry.className = 'segmind-event';
    entry.dataset.kind = event.kind;
    entry.hidden = this.hidden.has(event.kind);
    const button = document.createElement('button');
    button.type = 'button';
    const bodies = [event.tracked, event.withObject].filter(Boolean).join(' and ');
    button.title = `${event.type} of ${bodies}: light them up${this.#framesPerSecond !== null && event.frame !== null ? ' and show the moment' : ''}`;
    button.addEventListener('click', () => this.choose(event));
    const time = this.#text(document, 'span', 'segmind-time', this.timeOf(event));
    const label = this.#text(document, 'strong', 'segmind-label', event.label);
    const objects = this.#text(document, 'span', 'segmind-objects', this.objectsOf(event));
    button.append(time, label, objects);
    entry.append(button);
    return entry;
  }

  /**
   * @param {Document} document The page.
   * @param {string} tag The element's tag.
   * @param {string} className Its classes.
   * @param {string} text Its text.
   * @returns {HTMLElement} The element.
   */
  #text(document, tag, className, text) {
    const element = document.createElement(tag);
    element.className = className;
    element.textContent = text;
    return element;
  }
}
