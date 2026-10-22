/**
 * Arithmetic on protocol poses, `[x, y, z, qx, qy, qz, qw]`, as the Workshop panel
 * moves spring targets with it.
 */

/**
 * Where a pose's quaternion starts.
 */
export const QUATERNION_START = 3;

/**
 * How many numbers a position has.
 */
const POSITION_LENGTH = 3;

// %% quaternions

/**
 * @param {Array<number>} first A quaternion, scalar last.
 * @param {Array<number>} second Another quaternion, scalar last.
 * @returns {Array<number>} The rotation `first` after `second`.
 */
export function multiply(first, second) {
  const [ax, ay, az, aw] = first;
  const [bx, by, bz, bw] = second;
  return [
    aw * bx + ax * bw + ay * bz - az * by,
    aw * by - ax * bz + ay * bw + az * bx,
    aw * bz + ax * by - ay * bx + az * bw,
    aw * bw - ax * bx - ay * by - az * bz,
  ];
}

/**
 * @param {number} axis 0, 1 or 2 for the world's x, y or z axis.
 * @param {number} angle The angle, in radians.
 * @returns {Array<number>} The rotation about that axis, scalar last.
 */
export function aboutAxis(axis, angle) {
  const rotation = [0, 0, 0, Math.cos(angle / 2)];
  rotation[axis] = Math.sin(angle / 2);
  return rotation;
}

/**
 * @param {Array<number>} quaternion A unit quaternion, scalar last.
 * @returns {Array<number>} The rotated local z axis.
 */
export function zAxis(quaternion) {
  const [x, y, z, w] = quaternion;
  return [2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y)];
}

// %% poses

/**
 * @param {Array<number>} pose A pose.
 * @param {number} axis 0, 1 or 2 for the world's x, y or z axis.
 * @param {number} angle The angle, in radians.
 * @returns {Array<number>} The pose turned about the world axis through its position.
 */
export function rotated(pose, axis, angle) {
  return [...pose.slice(0, POSITION_LENGTH), ...multiply(aboutAxis(axis, angle), pose.slice(QUATERNION_START))];
}

/**
 * @param {Array<number>} pose A pose.
 * @param {Array<number>} offset A translation.
 * @param {number} decimals The decimals the shifted position keeps.
 * @returns {Array<number>} The pose shifted by the offset.
 */
export function shifted(pose, offset, decimals) {
  return pose.map((value, index) => (index < POSITION_LENGTH ? Number((value + offset[index]).toFixed(decimals)) : value));
}

/**
 * @param {Array<number>} actual A measured pose.
 * @param {Array<number>} desired A target pose.
 * @returns {{distance: number, angle: number}} How far apart the positions are, in
 *   metres, and the orientations, in radians.
 */
export function separation(actual, desired) {
  const distance = Math.hypot(...actual.slice(0, POSITION_LENGTH).map((value, axis) => value - desired[axis]));
  const dot = Math.abs(actual.slice(QUATERNION_START).reduce((sum, value, index) => sum + value * desired[index + QUATERNION_START], 0));
  return { distance, angle: 2 * Math.acos(Math.min(1, dot)) };
}
