/**
 * The cable lab's configuration form, read as a cable configuration document.
 */

import { CableConfigurationKey } from '../../../protocol.js';

/**
 * The form fields that are plain numbers, by configuration key.
 */
export const NUMBER_FIELDS = Object.freeze([
  CableConfigurationKey.SEGMENT_COUNT,
  CableConfigurationKey.SEGMENT_LENGTH,
  CableConfigurationKey.RADIUS,
  CableConfigurationKey.MASS,
  CableConfigurationKey.BEND,
  CableConfigurationKey.TWIST,
]);

/**
 * The torsional and rolling friction the form keeps while the sliding friction changes.
 */
export const OTHER_FRICTION = Object.freeze([0.005, 0.0001]);

/**
 * The decimals the sliding friction and the cable's length are shown with.
 */
const SHOWN_DECIMALS = 2;

// %% form

export class ConfigurationForm {
  /**
   * The form.
   * @type {HTMLFormElement}
   */
  form;

  /**
   * @param {HTMLFormElement} form The form whose fields are named by configuration key.
   */
  constructor(form) {
    this.form = form;
  }

  /**
   * @returns {Object} The cable configuration the form describes.
   */
  read() {
    const elements = this.form.elements;
    const configuration = {};
    for (const key of NUMBER_FIELDS) configuration[key] = Number(elements[key].value);
    configuration[CableConfigurationKey.FRICTION] = [Number(elements[CableConfigurationKey.FRICTION].value), ...OTHER_FRICTION];
    configuration[CableConfigurationKey.ANCHORED] = elements[CableConfigurationKey.ANCHORED].checked;
    return configuration;
  }

  /**
   * Show a configuration in the form.
   * @param {Object} configuration A cable configuration; absent keys keep their fields.
   */
  apply(configuration) {
    const elements = this.form.elements;
    for (const key of NUMBER_FIELDS) {
      if (Number.isFinite(configuration[key])) elements[key].value = String(configuration[key]);
    }
    const friction = configuration[CableConfigurationKey.FRICTION];
    if (Array.isArray(friction)) elements[CableConfigurationKey.FRICTION].value = String(friction[0]);
    if (typeof configuration[CableConfigurationKey.ANCHORED] === 'boolean') {
      elements[CableConfigurationKey.ANCHORED].checked = configuration[CableConfigurationKey.ANCHORED];
    }
  }

  /**
   * @returns {string} The sliding friction as shown next to its slider.
   */
  frictionText() {
    return this.read()[CableConfigurationKey.FRICTION][0].toFixed(SHOWN_DECIMALS);
  }

  /**
   * @returns {string} The cable's length and element count.
   */
  lengthText() {
    const configuration = this.read();
    const count = configuration[CableConfigurationKey.SEGMENT_COUNT];
    const length = count * configuration[CableConfigurationKey.SEGMENT_LENGTH];
    return `${length.toFixed(SHOWN_DECIMALS)} m cable · ${count} elements`;
  }

  /**
   * Put the form back to its defaults, with the first point pinned or loose.
   * @param {boolean} anchored Whether the first point is pinned.
   */
  preset(anchored) {
    this.form.reset();
    this.form.elements[CableConfigurationKey.ANCHORED].checked = anchored;
  }
}
