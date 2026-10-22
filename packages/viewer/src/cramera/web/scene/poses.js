/**
 * Applying protocol poses, `[x, y, z, qx, qy, qz, qw]`, to scene objects.
 */

// %% poses

/**
 * @param {{position: {set: Function}, quaternion: {set: Function}}} object A scene object.
 * @param {Array<number>} pose Its pose relative to its parent.
 */
export function applyPose(object, pose) {
  object.position.set(pose[0], pose[1], pose[2]);
  object.quaternion.set(pose[3], pose[4], pose[5], pose[6]);
}
