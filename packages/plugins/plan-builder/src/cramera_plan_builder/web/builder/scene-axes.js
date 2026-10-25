/**
 * The builder's map of the world's axes: a labelled triad at the origin, where poses are
 * measured from, and a compass in a corner of the view that turns with the camera, so
 * the person always sees which way x, y and z point.
 */

import * as THREE from 'three';

/**
 * The world's axes: their names, directions and colours, red x, green y, blue z as the
 * viewer's frame axes draw them.
 */
export const WORLD_AXES = Object.freeze([
  Object.freeze({ name: 'x', direction: Object.freeze([1, 0, 0]), color: 0xef4444 }),
  Object.freeze({ name: 'y', direction: Object.freeze([0, 1, 0]), color: 0x22c55e }),
  Object.freeze({ name: 'z', direction: Object.freeze([0, 0, 1]), color: 0x3b82f6 }),
]);

/**
 * The sizes of the triad at the origin, in metres.
 */
const OriginSize = Object.freeze({ LENGTH: 1, RADIUS: 0.008, HEAD_LENGTH: 0.08, HEAD_RADIUS: 0.03, LABEL_GAP: 0.12 });

/**
 * The height of the origin's axis labels as a share of the view's height; they keep
 * their size on the screen however far the camera is.
 */
const LABEL_SCREEN_HEIGHT = 0.045;

/**
 * The compass: its size and its gap to the view's bottom left corner in CSS pixels, and
 * the sizes of its triad in its own units.
 */
const Compass = Object.freeze({
  SIZE: 128,
  MARGIN: 8,
  LENGTH: 1,
  RADIUS: 0.05,
  HEAD_LENGTH: 0.28,
  HEAD_RADIUS: 0.13,
  LABEL_GAP: 0.25,
  LABEL_SIZE: 0.75,
  EXTENT: 1.5,
});

/**
 * How an axis label is drawn: the canvas's side and font in pixels.
 */
const AxisLabel = Object.freeze({ SIDE: 64, FONT: '700 44px system-ui, sans-serif' });

/**
 * Segments of the round parts.
 */
const SEGMENTS = 16;

/**
 * The name the origin's triad is known by in the scene.
 */
export const ORIGIN_AXES_NAME = 'world-axes';

// %% triads

/**
 * @param {Document} document A document to draw the labels on.
 * @param {{length: number, radius: number, headLength: number, headRadius: number,
 *   labelGap: number, label: function(THREE.Sprite): void}} size The triad's sizes,
 *   and how a label is scaled.
 * @returns {THREE.Group} Three arrows from the origin along x, y and z, each with its
 *   name at its tip; they look the same under every light and ignore tone mapping.
 */
export function axisTriad(document, size) {
  const group = new THREE.Group();
  for (const axis of WORLD_AXES) {
    const material = new THREE.MeshBasicMaterial({ color: axis.color, toneMapped: false });
    const shaftLength = size.length - size.headLength;
    const shaft = new THREE.Mesh(new THREE.CylinderGeometry(size.radius, size.radius, shaftLength, SEGMENTS), material);
    shaft.position.y = shaftLength / 2;
    const head = new THREE.Mesh(new THREE.ConeGeometry(size.headRadius, size.headLength, SEGMENTS), material);
    head.position.y = shaftLength + size.headLength / 2;
    const arrow = new THREE.Group();
    arrow.name = axis.name;
    arrow.add(shaft, head);
    // the cylinder and the cone stand along y; turn them onto the axis
    arrow.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), new THREE.Vector3(...axis.direction));
    const label = axisLabel(document, axis);
    size.label(label);
    label.position.set(...axis.direction).multiplyScalar(size.length + size.labelGap);
    group.add(arrow, label);
  }
  return group;
}

/**
 * @param {Document} document A document to draw the label on.
 * @param {{name: string, color: number}} axis An axis of `WORLD_AXES`.
 * @returns {THREE.Sprite} The axis's name in its colour, facing the camera and drawn
 *   over everything else.
 */
function axisLabel(document, axis) {
  const canvas = document.createElement('canvas');
  canvas.width = AxisLabel.SIDE;
  canvas.height = AxisLabel.SIDE;
  const context = canvas.getContext('2d');
  context.font = AxisLabel.FONT;
  context.fillStyle = `#${new THREE.Color(axis.color).getHexString()}`;
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillText(axis.name, AxisLabel.SIDE / 2, AxisLabel.SIDE / 2);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, depthTest: false, transparent: true, toneMapped: false }));
  sprite.name = `${axis.name}-label`;
  sprite.renderOrder = 1;
  return sprite;
}

// %% map

export class SceneAxes {
  /**
   * The triad at the origin.
   * @type {THREE.Group}
   */
  origin;

  /**
   * The compass's own scene.
   * @type {THREE.Scene}
   */
  #compassScene = new THREE.Scene();

  /**
   * Looks at the compass from the side the view's camera looks at the world.
   * @type {THREE.OrthographicCamera}
   */
  #compassCamera = new THREE.OrthographicCamera(-Compass.EXTENT, Compass.EXTENT, Compass.EXTENT, -Compass.EXTENT, 0.1, 10);

  /**
   * The 3D view.
   * @type {import('../../../scene/scene-view.js').SceneView}
   */
  #view;

  /**
   * Stops drawing the compass after the view's frames.
   * @type {function(): void}
   */
  #stopDrawing;

  /**
   * Put the triad at the view's origin and the compass in its bottom left corner.
   * @param {import('../../../scene/scene-view.js').SceneView} view The 3D view.
   * @param {Document} document A document to draw the labels on.
   */
  constructor(view, document) {
    this.#view = view;
    this.origin = axisTriad(document, {
      length: OriginSize.LENGTH,
      radius: OriginSize.RADIUS,
      headLength: OriginSize.HEAD_LENGTH,
      headRadius: OriginSize.HEAD_RADIUS,
      labelGap: OriginSize.LABEL_GAP,
      label: (sprite) => {
        sprite.material.sizeAttenuation = false;
        sprite.scale.set(LABEL_SCREEN_HEIGHT, LABEL_SCREEN_HEIGHT, 1);
      },
    });
    this.origin.name = ORIGIN_AXES_NAME;
    // a robot starts at the origin; the map shows through it as the handles do
    this.origin.traverse((child) => {
      if (!child.isMesh) return;
      child.material.depthTest = false;
      child.renderOrder = 1;
    });
    view.scene.add(this.origin);
    this.#compassScene.add(
      axisTriad(document, {
        length: Compass.LENGTH,
        radius: Compass.RADIUS,
        headLength: Compass.HEAD_LENGTH,
        headRadius: Compass.HEAD_RADIUS,
        labelGap: Compass.LABEL_GAP,
        label: (sprite) => sprite.scale.set(Compass.LABEL_SIZE, Compass.LABEL_SIZE, 1),
      }),
    );
    this.#compassCamera.up.set(0, 0, 1);
    this.#stopDrawing = view.onRender(() => this.#drawCompass());
    view.requestRender();
  }

  /**
   * Stop drawing the compass and release the triads.
   */
  dispose() {
    this.#stopDrawing();
    this.origin.removeFromParent();
    for (const group of [this.origin, this.#compassScene]) {
      group.traverse((child) => {
        child.geometry?.dispose();
        child.material?.map?.dispose();
        child.material?.dispose();
      });
    }
  }

  /**
   * Turn the compass as the view's camera and draw it over the view's corner.
   */
  #drawCompass() {
    const camera = this.#view.camera;
    this.#compassCamera.quaternion.copy(camera.quaternion);
    this.#compassCamera.position.set(0, 0, 5).applyQuaternion(camera.quaternion);
    const renderer = this.#view.renderer;
    const { width, height } = this.#view.size;
    const autoClear = renderer.autoClear;
    renderer.autoClear = false;
    renderer.clearDepth();
    renderer.setScissorTest(true);
    renderer.setScissor(Compass.MARGIN, Compass.MARGIN, Compass.SIZE, Compass.SIZE);
    renderer.setViewport(Compass.MARGIN, Compass.MARGIN, Compass.SIZE, Compass.SIZE);
    renderer.render(this.#compassScene, this.#compassCamera);
    renderer.setViewport(0, 0, width, height);
    renderer.setScissor(0, 0, width, height);
    renderer.setScissorTest(false);
    renderer.autoClear = autoClear;
  }
}
