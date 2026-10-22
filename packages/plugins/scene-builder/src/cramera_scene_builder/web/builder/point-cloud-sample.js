/**
 * The display sample of a point cloud, as the server sends it, shown as points.
 *
 * The sample's bytes are two little-endian unsigned 32-bit integers, the number of
 * points and 1 when colours follow, then the x, y and z of every point and, if
 * coloured, the sRGB red, green and blue of every point, as little-endian 32-bit floats.
 */

import * as THREE from 'three';

import { AppearanceKey } from '../../../protocol.js';

/**
 * The layout of a sample's start: two unsigned 32-bit integers.
 */
export const SampleHeader = Object.freeze({ COUNT_OFFSET: 0, COLORED_OFFSET: 4, LENGTH: 8 });

/**
 * The size of one value of a sample in bytes.
 */
const VALUE_SIZE = 4;

/**
 * The number of values of one position or colour.
 */
const COMPONENTS = 3;

/**
 * The geometry attributes the points are drawn from.
 */
const PointAttribute = Object.freeze({ POSITION: 'position', COLOR: 'color' });

/**
 * Whether the sample's values are little-endian.
 */
const LITTLE_ENDIAN = true;

// %% errors

/**
 * Bytes that are not a sample of the length its header declares.
 */
export class MalformedSample extends Error {
  /**
   * @param {number} length The number of bytes received.
   * @param {number} expected The number of bytes the header declares.
   */
  constructor(length, expected) {
    super(`A point cloud sample of ${length} bytes, where its header declares ${expected}.`);
    /**
     * The number of bytes received.
     * @type {number}
     */
    this.length = length;
    /**
     * The number of bytes the header declares.
     * @type {number}
     */
    this.expected = expected;
  }
}

// %% sample

export class PointCloudSample {
  /**
   * @param {Float32Array} positions The x, y and z of every point.
   * @param {Float32Array|null} colors The sRGB red, green and blue of every point, or null.
   */
  constructor(positions, colors) {
    /**
     * The x, y and z of every point.
     * @type {Float32Array}
     */
    this.positions = positions;
    /**
     * The sRGB red, green and blue of every point, or null for a colourless cloud.
     * @type {Float32Array|null}
     */
    this.colors = colors;
  }

  /**
   * @param {ArrayBuffer} buffer A sample's bytes.
   * @returns {PointCloudSample} The sample.
   * @throws {MalformedSample} When the bytes do not hold what the header declares.
   */
  static fromBytes(buffer) {
    if (buffer.byteLength < SampleHeader.LENGTH) throw new MalformedSample(buffer.byteLength, SampleHeader.LENGTH);
    const view = new DataView(buffer);
    const count = view.getUint32(SampleHeader.COUNT_OFFSET, LITTLE_ENDIAN);
    const colored = view.getUint32(SampleHeader.COLORED_OFFSET, LITTLE_ENDIAN) === 1;
    const values = count * COMPONENTS * (colored ? 2 : 1);
    const expected = SampleHeader.LENGTH + values * VALUE_SIZE;
    if (buffer.byteLength !== expected) throw new MalformedSample(buffer.byteLength, expected);
    const read = (start) => {
      const array = new Float32Array(count * COMPONENTS);
      for (let index = 0; index < array.length; index += 1) {
        array[index] = view.getFloat32(SampleHeader.LENGTH + (start + index) * VALUE_SIZE, LITTLE_ENDIAN);
      }
      return array;
    };
    return new PointCloudSample(read(0), colored ? read(count * COMPONENTS) : null);
  }

  /**
   * @returns {number} How many points the sample holds.
   */
  get pointCount() {
    return this.positions.length / COMPONENTS;
  }

  /**
   * @param {Object} appearance How the reference is shown, by `AppearanceKey`.
   * @returns {THREE.Points} The sample's points, in the file's coordinates.
   */
  points(appearance) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute(PointAttribute.POSITION, new THREE.BufferAttribute(this.positions, COMPONENTS));
    if (this.colors) geometry.setAttribute(PointAttribute.COLOR, new THREE.BufferAttribute(this.#linearColors(), COMPONENTS));
    const material = new THREE.PointsMaterial({ vertexColors: Boolean(this.colors), transparent: true, depthWrite: false });
    const points = new THREE.Points(geometry, material);
    PointCloudSample.show(points, appearance);
    return points;
  }

  /**
   * @param {THREE.Points} points A sample's points.
   * @param {Object} appearance How the reference is shown, by `AppearanceKey`.
   */
  static show(points, appearance) {
    points.visible = appearance[AppearanceKey.VISIBLE];
    points.material.size = appearance[AppearanceKey.POINT_SIZE];
    points.material.opacity = appearance[AppearanceKey.OPACITY];
  }

  /**
   * @returns {Float32Array} The colours in the renderer's linear working colour space.
   */
  #linearColors() {
    const linear = new Float32Array(this.colors.length);
    const color = new THREE.Color();
    for (let index = 0; index < linear.length; index += COMPONENTS) {
      color.setRGB(this.colors[index], this.colors[index + 1], this.colors[index + 2], THREE.SRGBColorSpace);
      linear.set([color.r, color.g, color.b], index);
    }
    return linear;
  }
}
