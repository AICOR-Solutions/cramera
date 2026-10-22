/**
 * Choosing a bundle by robot, environment and task, the way the scene picker offers
 * them: only combinations that were recorded can be chosen.
 */

import { IndexEntryKey, IndexKey } from '../protocol.js';

/**
 * The label of a bundle without a robot.
 */
export const WITHOUT_ROBOT = '(no robot)';

/**
 * The label of a bundle without an environment.
 */
export const WITHOUT_ENVIRONMENT = '(bench only)';

// %% choice

export class SceneChoice {
  /**
   * The index entries.
   * @type {Array<Object>}
   */
  #entries;

  /**
   * The entry chosen now.
   * @type {Object|null}
   */
  #chosen = null;

  /**
   * @param {Object} index The scenes index.
   */
  constructor(index) {
    this.#entries = index[IndexKey.SCENES] ?? [];
    const preferred = index[IndexKey.DEFAULT];
    this.#chosen = this.#entries.find((entry) => entry[IndexEntryKey.NAME] === preferred) ?? this.#entries[0] ?? null;
  }

  /**
   * @returns {string|null} The chosen bundle's name, or null for an empty index.
   */
  get scene() {
    return this.#chosen?.[IndexEntryKey.NAME] ?? null;
  }

  /**
   * @returns {Array<string>} Every robot label, sorted.
   */
  robots() {
    return this.#distinct(this.#entries.map(robotOf));
  }

  /**
   * @returns {Array<string>} The environment labels recorded with the chosen robot.
   */
  environments() {
    return this.#distinct(this.#matching({ robot: this.robot }).map(environmentOf));
  }

  /**
   * @returns {Array<string>} The task labels recorded with the chosen robot and environment.
   */
  tasks() {
    return this.#distinct(this.#matching({ robot: this.robot, environment: this.environment }).map(taskOf));
  }

  /**
   * @returns {string|null} The chosen robot label.
   */
  get robot() {
    return this.#chosen ? robotOf(this.#chosen) : null;
  }

  /**
   * @returns {string|null} The chosen environment label.
   */
  get environment() {
    return this.#chosen ? environmentOf(this.#chosen) : null;
  }

  /**
   * @returns {string|null} The chosen task label.
   */
  get task() {
    return this.#chosen ? taskOf(this.#chosen) : null;
  }

  /**
   * Choose a bundle by name.
   * @param {string} name A bundle name.
   * @returns {boolean} Whether the index holds it.
   */
  chooseScene(name) {
    const entry = this.#entries.find((candidate) => candidate[IndexEntryKey.NAME] === name);
    if (entry) this.#chosen = entry;
    return Boolean(entry);
  }

  /**
   * Choose a robot; the environment and task stay when that robot was recorded with
   * them, else the first recorded ones are taken.
   * @param {string} robot A robot label.
   */
  chooseRobot(robot) {
    this.#choose({ robot, environment: this.environment, task: this.task }, { robot });
  }

  /**
   * Choose an environment for the chosen robot; the task stays when recorded.
   * @param {string} environment An environment label.
   */
  chooseEnvironment(environment) {
    this.#choose({ robot: this.robot, environment, task: this.task }, { robot: this.robot, environment });
  }

  /**
   * Choose a task for the chosen robot and environment.
   * @param {string} task A task label.
   */
  chooseTask(task) {
    this.#choose({ robot: this.robot, environment: this.environment, task }, { robot: this.robot, environment: this.environment });
  }

  /**
   * @param {Object} wanted The labels to match exactly.
   * @param {Object} fallback The labels to match when no entry matches `wanted`.
   */
  #choose(wanted, fallback) {
    this.#chosen = this.#matching(wanted)[0] ?? this.#matching(fallback)[0] ?? this.#chosen;
  }

  /**
   * @param {{robot?: string, environment?: string, task?: string}} labels The labels to match.
   * @returns {Array<Object>} The entries with all given labels.
   */
  #matching(labels) {
    return this.#entries.filter(
      (entry) =>
        (labels.robot === undefined || robotOf(entry) === labels.robot) &&
        (labels.environment === undefined || environmentOf(entry) === labels.environment) &&
        (labels.task === undefined || taskOf(entry) === labels.task),
    );
  }

  /**
   * @param {Array<string>} labels Labels with repetitions.
   * @returns {Array<string>} Each label once, sorted.
   */
  #distinct(labels) {
    return [...new Set(labels)].sort((first, second) => first.localeCompare(second));
  }
}

// %% labels

/**
 * @param {Object} entry An index entry.
 * @returns {string} Its robot label.
 */
function robotOf(entry) {
  return entry[IndexEntryKey.ROBOT] || WITHOUT_ROBOT;
}

/**
 * @param {Object} entry An index entry.
 * @returns {string} Its environment label.
 */
function environmentOf(entry) {
  return entry[IndexEntryKey.ENVIRONMENT] || WITHOUT_ENVIRONMENT;
}

/**
 * @param {Object} entry An index entry.
 * @returns {string} Its task label, the bundle name when it names no task.
 */
function taskOf(entry) {
  return entry[IndexEntryKey.TASK] || entry[IndexEntryKey.NAME];
}
