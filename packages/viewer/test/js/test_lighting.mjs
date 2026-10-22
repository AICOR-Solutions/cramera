import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import * as THREE from 'three';

import { Bounds, InvalidBounds, isPoint } from '../../src/cramera/web/scene/bounds.js';
import { blackBody, LOCUS_RANGE } from '../../src/cramera/web/scene/color-temperature.js';
import { DirectionWithoutLength, SHADOW_MARGIN, ShadowFit } from '../../src/cramera/web/scene/shadow-fit.js';
import {
  CEILING_DEPTH,
  FIXTURE_DEPTH,
  KEY_SHARE,
  LightingDescription,
  LightingRoom,
  PANEL_GAP,
  Reflectance,
  intensityOf,
} from '../../src/cramera/web/scene/stage-lighting.js';
import { LightKey, LightingKey, RenderingKey, SceneKey } from '../../src/cramera/web/protocol.js';

const TOLERANCE = 1e-9;
const LIGHTING = JSON.parse(readFileSync(new URL('./dataset/viewer_lighting.json', import.meta.url), 'utf8'));
const SCENE = JSON.parse(readFileSync(new URL('./dataset/viewer_scene.json', import.meta.url), 'utf8'));
const BOUNDS = Bounds.of(SCENE[SceneKey.RENDERING][RenderingKey.SHADOW_BOUNDS]);

function near(actual, expected, tolerance = TOLERANCE) {
  assert.ok(Math.abs(actual - expected) < tolerance, `${actual} is not ${expected}`);
}

function nearAll(actual, expected, tolerance = TOLERANCE) {
  assert.equal(actual.length, expected.length);
  actual.forEach((value, index) => near(value, expected[index], tolerance));
}

function luminance(color) {
  return 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2];
}

function room(document = LIGHTING, bounds = BOUNDS) {
  return new LightingRoom(LightingDescription.of(document), bounds);
}

// %% bounds

test('bounds are two corners and know their size, centre and corners', () => {
  assert.deepEqual(BOUNDS.size(), [9.6, 4.8, 3]);
  assert.deepEqual(BOUNDS.center(), [0, 0, 1.5]);
  assert.equal(BOUNDS.corners().length, 8);
  assert.throws(() => Bounds.of([[0, 0, 0]]), InvalidBounds);
  assert.equal(isPoint([0, 0, Number.NaN]), false);
});

// %% colour temperature

test('a black body has the luminance of white at every temperature of the locus', () => {
  for (const kelvin of [2000, 3000, 4000, 5200, 6500, 9000]) near(luminance(blackBody(kelvin)), 1, 0.05);
});

test('a lower colour temperature is redder and a higher one bluer', () => {
  const warm = blackBody(3000);
  const cool = blackBody(9000);
  assert.ok(warm[0] > warm[2]);
  assert.ok(cool[2] > cool[0]);
});

test('temperatures beyond the fitted locus keep the colour at its end and no channel is negative', () => {
  assert.deepEqual(blackBody(LOCUS_RANGE[0] - 500), blackBody(LOCUS_RANGE[0]));
  assert.deepEqual(blackBody(LOCUS_RANGE[1] + 5000), blackBody(LOCUS_RANGE[1]));
  for (let kelvin = 1000; kelvin < 30000; kelvin += 700) assert.ok(blackBody(kelvin).every((channel) => channel >= 0));
});

// %% description

test('unusable lights are left out and an empty description is empty', () => {
  const description = LightingDescription.of({
    [LightingKey.SUN]: { [LightKey.DIRECTION]: [0, 0, 0], [LightKey.INTENSITY]: 1 },
    [LightingKey.PANELS]: [{ [LightKey.CENTER]: [0, 0, 3], [LightKey.NORMAL]: [0, 0, -1], [LightKey.WIDTH]: 0, [LightKey.HEIGHT]: 1, [LightKey.INTENSITY]: 1 }],
  });
  assert.equal(description.sun, null);
  assert.deepEqual(description.panels, []);
  assert.equal(description.empty, true);
  assert.equal(LightingDescription.of(LIGHTING).empty, false);
});

test('a light shows its colour times the black body of its temperature, white without either', () => {
  const description = LightingDescription.of(LIGHTING);
  nearAll(description.sun.color, blackBody(LIGHTING[LightingKey.SUN][LightKey.COLOR_TEMPERATURE]));
  nearAll(description.dome.color, LIGHTING[LightingKey.DOME][LightKey.COLOR]);
  const plain = LightingDescription.of({ [LightingKey.DOME]: { [LightKey.INTENSITY]: 1 } });
  assert.deepEqual(plain.dome.color, [1, 1, 1]);
});

// %% room

test('the reference luminance is the ceiling, else the dome, else the sun on white', () => {
  const lit = room();
  const size = lit.room.size();
  near(lit.referenceLuminance, intensityOf(lit.lighting.panels) / (size[0] * size[1]));
  const domeOnly = room({ [LightingKey.DOME]: LIGHTING[LightingKey.DOME] });
  near(domeOnly.referenceLuminance, LIGHTING[LightingKey.DOME][LightKey.INTENSITY]);
  const sunOnly = room({ [LightingKey.SUN]: LIGHTING[LightingKey.SUN] });
  near(sunOnly.referenceLuminance, LIGHTING[LightingKey.SUN][LightKey.INTENSITY] / Math.PI);
  near(room({}).referenceLuminance, 1);
});

test('the room spans the bounds and closes just above the highest panel', () => {
  const lit = room();
  const highest = Math.max(...LIGHTING[LightingKey.PANELS].map((panel) => panel[LightKey.CENTER][2]));
  assert.deepEqual(lit.room.min, BOUNDS.min);
  near(lit.room.max[2], highest + PANEL_GAP);
  assert.deepEqual(lit.probe(), lit.room.center());
});

test('without bounds the room covers every panel and stands on the ground', () => {
  const lit = room(LIGHTING, null);
  for (const panel of lit.lighting.panels) {
    assert.ok(lit.room.min[0] <= panel.center[0] - panel.width / 2);
    assert.ok(lit.room.max[0] >= panel.center[0] + panel.width / 2);
  }
  assert.equal(lit.room.min[2], 0);
});

test('panels that outshine the sun light the room from above with their share', () => {
  const lit = room({ ...LIGHTING, [LightingKey.SUN]: { ...LIGHTING[LightingKey.SUN], [LightKey.INTENSITY]: 10 } });
  const key = lit.keyLight();
  nearAll(key.direction, [0, 0, -1]);
  near(key.intensity, KEY_SHARE * lit.ceilingLuminance / lit.referenceLuminance);
  nearAll(key.color, lit.lightColor());
});

test('a sun that outshines the panels is the key light, in its colour', () => {
  const bright = { ...LIGHTING, [LightingKey.SUN]: { ...LIGHTING[LightingKey.SUN], [LightKey.INTENSITY]: 1e9 } };
  const lit = room(bright);
  const key = lit.keyLight();
  assert.deepEqual(key.direction, bright[LightingKey.SUN][LightKey.DIRECTION]);
  assert.equal(key.shadowBounds, BOUNDS);
  near(key.intensity, 1e9 / Math.PI / lit.referenceLuminance);
});

test('panels facing each other give no direction, and no sun and no panels give no key', () => {
  const facing = {
    [LightingKey.PANELS]: [
      { [LightKey.CENTER]: [0, 0, 3], [LightKey.NORMAL]: [0, 0, -1], [LightKey.WIDTH]: 1, [LightKey.HEIGHT]: 1, [LightKey.INTENSITY]: 10 },
      { [LightKey.CENTER]: [0, 0, 0], [LightKey.NORMAL]: [0, 0, 1], [LightKey.WIDTH]: 1, [LightKey.HEIGHT]: 1, [LightKey.INTENSITY]: 10 },
    ],
  };
  assert.equal(room(facing).panelDirection(), null);
  assert.equal(room(facing).keyLight(), null);
  assert.equal(room({ [LightingKey.DOME]: LIGHTING[LightingKey.DOME] }).keyLight(), null);
});

test('the shadows of a key from the panels stop below the panels\' fixtures', () => {
  const lit = room();
  const lowestCeilingPanel = Math.min(...lit.lighting.panels.map((panel) => panel.center[2]));
  near(lit.belowPanels().max[2], Math.min(BOUNDS.max[2], lowestCeilingPanel - FIXTURE_DEPTH));
});

test('a panel hanging low in the room is not part of the ceiling', () => {
  const hanging = {
    [LightingKey.PANELS]: [
      ...LIGHTING[LightingKey.PANELS],
      { [LightKey.CENTER]: [0, 0, 1.2], [LightKey.NORMAL]: [0, 0, -1], [LightKey.WIDTH]: 0.4, [LightKey.HEIGHT]: 0.4, [LightKey.INTENSITY]: 100 },
    ],
  };
  const highest = Math.max(...LIGHTING[LightingKey.PANELS].map((panel) => panel[LightKey.CENTER][2]));
  assert.ok(room(hanging).belowPanels().max[2] > highest - CEILING_DEPTH - FIXTURE_DEPTH);
});

test('the floor reflects the ceiling, the ceiling tiles the floor, the walls half of each', () => {
  const lit = room();
  const faces = lit.faceColors();
  const light = lit.lightColor();
  const overhead = lit.overheadLuminance();
  const floor = Reflectance.FLOOR * overhead;
  nearAll(faces.floor, light.map((channel) => channel * floor));
  nearAll(faces.ceiling, light.map((channel) => channel * Reflectance.CEILING * floor));
  nearAll(faces.wall, light.map((channel) => channel * Reflectance.WALL * (overhead + floor) / 2));
});

test('without panels the ceiling is the dome\'s open sky', () => {
  const sky = room({ [LightingKey.DOME]: LIGHTING[LightingKey.DOME] });
  nearAll(sky.faceColors().ceiling, sky.lighting.dome.color.map((channel) => channel * sky.overheadLuminance()));
});

test('a panel glows in its colour at its luminance over the reference', () => {
  const lit = room();
  const panel = lit.lighting.panels[0];
  nearAll(lit.panelRadiance(panel), panel.color.map((channel) => channel * panel.intensity / lit.referenceLuminance));
});

// %% shadow fit

test('a light from straight above sees the footprint of the bounds plus the margin', () => {
  const frustum = new ShadowFit(BOUNDS, [0, 0, -1]).frustum();
  near(frustum.right - frustum.left, BOUNDS.size()[0] + 2 * SHADOW_MARGIN, 1e-6);
  near(frustum.top - frustum.bottom, BOUNDS.size()[1] + 2 * SHADOW_MARGIN, 1e-6);
  near(frustum.far - frustum.near, BOUNDS.size()[2] + 2 * SHADOW_MARGIN, 1e-6);
});

test('every corner lies inside the shadow camera of an oblique light, which shines on the centre', () => {
  const light = new THREE.DirectionalLight();
  new ShadowFit(BOUNDS, [0.35, -0.45, -0.82]).applyTo(light);
  const camera = light.shadow.camera;
  camera.position.copy(light.position);
  camera.lookAt(light.target.position);
  camera.updateMatrixWorld();
  for (const corner of BOUNDS.corners()) {
    const seen = new THREE.Vector3(...corner).applyMatrix4(camera.matrixWorldInverse);
    assert.ok(seen.x >= camera.left && seen.x <= camera.right && seen.y >= camera.bottom && seen.y <= camera.top);
    assert.ok(-seen.z >= camera.near && -seen.z <= camera.far);
  }
  nearAll(light.target.position.toArray(), BOUNDS.center());
});

test('a direction without length is refused', () => {
  assert.throws(() => new ShadowFit(BOUNDS, [0, 0, 0]), DirectionWithoutLength);
});
