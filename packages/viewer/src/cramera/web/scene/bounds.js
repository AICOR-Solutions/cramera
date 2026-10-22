/**
 * Axis-aligned boxes in the scene frame (z up, metres).
 */

// %% errors

/**
 * A box whose corners are not two points of three finite numbers.
 */
export class InvalidBounds extends Error {
  /**
   * @param {*} value The value that was read as a box.
   */
  constructor(value) {
    super(`${JSON.stringify(value)} is not a box of two corners.`);
    /**
     * The value that was read.
     * @type {*}
     */
    this.value = value;
  }
}

// %% points

/**
 * @param {*} value A value.
 * @returns {boolean} Whether it is a point: three finite numbers.
 */
export function isPoint(value) {
  return Array.isArray(value) && value.length === 3 && value.every(Number.isFinite);
}

// %% bounds

export class Bounds {
  /**
   * @param {Array<number>} min The corner with the smallest coordinates.
   * @param {Array<number>} max The corner with the largest coordinates.
   */
  constructor(min, max) {
    /**
     * The corner with the smallest coordinates.
     * @type {Array<number>}
     */
    this.min = min;
    /**
     * The corner with the largest coordinates.
     * @type {Array<number>}
     */
    this.max = max;
  }

  /**
   * @param {*} corners A protocol box, `[[min], [max]]`.
   * @returns {Bounds} The box.
   * @throws {InvalidBounds} When the value is no such box.
   */
  static of(corners) {
    if (!Array.isArray(corners) || corners.length !== 2 || !corners.every(isPoint)) throw new InvalidBounds(corners);
    return new Bounds(corners[0].slice(), corners[1].slice());
  }

  /**
   * @returns {Array<number>} The box's extent along each axis.
   */
  size() {
    return this.max.map((value, axis) => value - this.min[axis]);
  }

  /**
   * @returns {Array<number>} The middle of the box.
   */
  center() {
    return this.max.map((value, axis) => (value + this.min[axis]) / 2);
  }

  /**
   * @returns {Array<Array<number>>} The eight corners.
   */
  corners() {
    const corners = [];
    for (const x of [this.min[0], this.max[0]]) for (const y of [this.min[1], this.max[1]]) for (const z of [this.min[2], this.max[2]]) corners.push([x, y, z]);
    return corners;
  }
}
