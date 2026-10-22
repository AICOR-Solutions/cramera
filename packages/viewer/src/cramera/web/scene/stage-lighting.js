/**
 * The lights of a converted stage, from its `lighting.json`.
 *
 * The panels light the scene through an environment map: a room the size of the scene
 * with a glowing quad per panel. One shadow-casting key light carries the strongest
 * direct light: the sun, unless the panels light the floor more strongly, as under a
 * ceiling that never sees the sun. All intensities are divided by one reference
 * luminance, the lit ceiling's or else the dome's, so the scene's exposure alone sets
 * its brightness, as in an auto-exposed render of the stage.
 */

import { LightingKey, LightKey } from '../protocol.js';
import { Bounds, isPoint } from './bounds.js';
import { blackBody } from './color-temperature.js';

/**
 * The colour of a light that states neither a colour nor a colour temperature.
 */
const WHITE = Object.freeze([1, 1, 1]);

/**
 * The room of a stage that has neither shadow bounds nor panels, in metres.
 */
const FALLBACK_ROOM = Object.freeze([[-5, -5, 0], [5, 5, 3]]);

/**
 * The height of the ground a room without bounds stands on.
 */
const GROUND = 0;

/**
 * Metres between the highest panel and the room's ceiling, so the quads stay visible.
 */
export const PANEL_GAP = 0.01;

/**
 * Metres below a panel's centre that its fixture and the ceiling around it reach.
 */
export const FIXTURE_DEPTH = 0.1;

/**
 * Metres below the highest panel that a panel still counts as part of the ceiling.
 */
export const CEILING_DEPTH = 0.3;

/**
 * The share of light the room's floor, walls and ceiling tiles are assumed to reflect.
 */
export const Reflectance = Object.freeze({ FLOOR: 0.6, WALL: 0.7, CEILING: 0.8 });

/**
 * The share of the panels' light a key from the panels carries, matched to the floor
 * to wall brightness of path-traced renders of a panel-lit laboratory.
 */
export const KEY_SHARE = 0.25;

// %% description

/**
 * @param {*} value A value.
 * @returns {boolean} Whether it is a direction: a point with a length.
 */
function isDirection(value) {
  return isPoint(value) && value.some((component) => component !== 0);
}

/**
 * @param {*} value A value.
 * @returns {boolean} Whether it is a non-negative finite number.
 */
function isAmount(value) {
  return Number.isFinite(value) && value >= 0;
}

/**
 * @param {Object} light A light of `lighting.json`.
 * @returns {Array<number>} Its linear colour: the colour times the black body of its temperature.
 */
function colorOf(light) {
  const tint = isPoint(light[LightKey.COLOR]) ? light[LightKey.COLOR] : WHITE;
  const temperature = light[LightKey.COLOR_TEMPERATURE];
  const body = Number.isFinite(temperature) && temperature > 0 ? blackBody(temperature) : WHITE;
  return tint.map((channel, index) => Math.max(0, channel) * body[index]);
}

export class LightingDescription {
  /**
   * @param {Object|null} sun `{direction, intensity, color}`.
   * @param {Object|null} dome `{color, intensity}`.
   * @param {Array<Object>} panels `[{center, normal, width, height, intensity, color}]`.
   */
  constructor(sun, dome, panels) {
    /**
     * The sun, the way its light travels, or null.
     * @type {Object|null}
     */
    this.sun = sun;
    /**
     * The sky dome, or null.
     * @type {Object|null}
     */
    this.dome = dome;
    /**
     * The rectangle lights.
     * @type {Array<Object>}
     */
    this.panels = panels;
  }

  /**
   * @param {Object} document The content of `lighting.json`.
   * @returns {LightingDescription} Its usable lights; lights with missing or invalid
   *   values are left out.
   */
  static of(document) {
    const sun = document[LightingKey.SUN];
    const dome = document[LightingKey.DOME];
    const usableSun = sun && isDirection(sun[LightKey.DIRECTION]) && isAmount(sun[LightKey.INTENSITY]);
    const usableDome = dome && isAmount(dome[LightKey.INTENSITY]);
    const panels = (document[LightingKey.PANELS] ?? []).filter(
      (panel) =>
        isPoint(panel[LightKey.CENTER]) &&
        isDirection(panel[LightKey.NORMAL]) &&
        isAmount(panel[LightKey.INTENSITY]) &&
        panel[LightKey.WIDTH] > 0 &&
        panel[LightKey.HEIGHT] > 0,
    );
    return new LightingDescription(
      usableSun ? { direction: sun[LightKey.DIRECTION].slice(), intensity: sun[LightKey.INTENSITY], color: colorOf(sun) } : null,
      usableDome ? { color: colorOf({ [LightKey.COLOR]: dome[LightKey.COLOR] }), intensity: dome[LightKey.INTENSITY] } : null,
      panels.map((panel) => ({
        center: panel[LightKey.CENTER].slice(),
        normal: panel[LightKey.NORMAL].slice(),
        width: panel[LightKey.WIDTH],
        height: panel[LightKey.HEIGHT],
        intensity: panel[LightKey.INTENSITY],
        color: colorOf(panel),
      })),
    );
  }

  /**
   * @returns {boolean} Whether no usable light is described.
   */
  get empty() {
    return !this.sun && !this.dome && this.panels.length === 0;
  }
}

// %% room

/**
 * @param {Array<Object>} panels Panels of a description.
 * @returns {number} Their luminous intensity along the normal: luminance times area, summed.
 */
export function intensityOf(panels) {
  return panels.reduce((sum, panel) => sum + panel.intensity * panel.width * panel.height, 0);
}

export class LightingRoom {
  /**
   * @param {LightingDescription} lighting The stage's lights.
   * @param {Bounds|null} bounds The scene's shadow bounds, which the room spans.
   */
  constructor(lighting, bounds) {
    /**
     * The stage's lights.
     * @type {LightingDescription}
     */
    this.lighting = lighting;
    /**
     * The scene's shadow bounds, or null.
     * @type {Bounds|null}
     */
    this.bounds = bounds;
    /**
     * The room box: the bounds' floor and walls, closed just above the highest panel.
     * @type {Bounds}
     */
    this.room = LightingRoom.roomOf(lighting, bounds);
    const size = this.room.size();
    const floorArea = size[0] * size[1];
    /**
     * The panels' luminous intensity spread over the floor: the lit ceiling's mean luminance.
     * @type {number}
     */
    this.ceilingLuminance = floorArea > 0 ? intensityOf(lighting.panels) / floorArea : 0;
    /**
     * The luminance shown at 1.
     * @type {number}
     */
    this.referenceLuminance = LightingRoom.referenceOf(lighting, this.ceilingLuminance);
  }

  /**
   * @param {LightingDescription} lighting The stage's lights.
   * @param {Bounds|null} bounds The scene's shadow bounds.
   * @returns {Bounds} The room: the bounds closed above the highest panel; without
   *   bounds the panels' footprint standing on the ground.
   */
  static roomOf(lighting, bounds) {
    const panels = lighting.panels;
    if (panels.length === 0) return bounds ?? Bounds.of(FALLBACK_ROOM);
    const ceiling = Math.max(...panels.map((panel) => panel.center[2])) + PANEL_GAP;
    if (bounds) return new Bounds(bounds.min.slice(), [bounds.max[0], bounds.max[1], ceiling]);
    const reach = (panel) => Math.max(panel.width, panel.height) / 2;
    const lowest = (axis) => Math.min(...panels.map((panel) => panel.center[axis] - reach(panel)));
    const highest = (axis) => Math.max(...panels.map((panel) => panel.center[axis] + reach(panel)));
    return new Bounds([lowest(0), lowest(1), GROUND], [highest(0), highest(1), ceiling]);
  }

  /**
   * @param {LightingDescription} lighting The stage's lights.
   * @param {number} ceilingLuminance The lit ceiling's mean luminance.
   * @returns {number} The luminance shown at 1: the ceiling's, else the dome's, else
   *   the sun's reflected by white.
   */
  static referenceOf(lighting, ceilingLuminance) {
    if (ceilingLuminance > 0) return ceilingLuminance;
    if (lighting.dome?.intensity > 0) return lighting.dome.intensity;
    if (lighting.sun?.intensity > 0) return lighting.sun.intensity / Math.PI;
    return 1;
  }

  /**
   * @returns {number} The luminance from above relative to the reference: the lit
   *   ceiling, else the open sky.
   */
  overheadLuminance() {
    if (this.lighting.panels.length) return this.ceilingLuminance / this.referenceLuminance;
    return this.lighting.dome ? this.lighting.dome.intensity / this.referenceLuminance : 0;
  }

  /**
   * @returns {Array<number>|null} The panels' colour mixed by their output, or null
   *   when they emit none.
   */
  panelColor() {
    const total = intensityOf(this.lighting.panels);
    if (!(total > 0)) return null;
    return [0, 1, 2].map((channel) =>
      this.lighting.panels.reduce((sum, panel) => sum + (panel.color[channel] * intensityOf([panel])) / total, 0),
    );
  }

  /**
   * @returns {Array<number>} The colour of the light filling the room.
   */
  lightColor() {
    return this.panelColor() ?? (this.lighting.dome ? this.lighting.dome.color.slice() : WHITE.slice());
  }

  /**
   * @returns {Array<number>|null} The way the panels' light travels, their normals
   *   averaged by output, or null when they cancel out.
   */
  panelDirection() {
    const sum = [0, 0, 0];
    for (const panel of this.lighting.panels) {
      const length = Math.hypot(...panel.normal);
      const output = intensityOf([panel]);
      panel.normal.forEach((component, axis) => { sum[axis] += (component / length) * output; });
    }
    const length = Math.hypot(...sum);
    return length > 0 ? sum.map((component) => component / length) : null;
  }

  /**
   * @returns {Array<number>} The point the environment is seen from: the room's centre.
   */
  probe() {
    return this.room.center();
  }

  /**
   * The shadow-casting key light: from the panels when their light on the floor
   * outshines the sun's, else along the sun, else none. A key of intensity 1 lights
   * white as a luminance of 1 shows.
   * @returns {{direction: Array<number>, color: Array<number>, intensity: number, shadowBounds: Bounds|null}|null}
   *   The key light, or null.
   */
  keyLight() {
    const sun = this.lighting.sun;
    const direction = this.panelDirection();
    const ceilingIrradiance = Math.PI * this.ceilingLuminance;
    if (direction && ceilingIrradiance > 0 && !(sun && sun.intensity > ceilingIrradiance)) {
      return {
        direction,
        color: this.lightColor(),
        intensity: (KEY_SHARE * this.ceilingLuminance) / this.referenceLuminance,
        shadowBounds: this.belowPanels(),
      };
    }
    if (!sun) return null;
    return {
      direction: sun.direction.slice(),
      color: sun.color.slice(),
      intensity: sun.intensity / Math.PI / this.referenceLuminance,
      shadowBounds: this.bounds,
    };
  }

  /**
   * @returns {Bounds} The space whose objects shade what the panels light: the bounds,
   *   else the room, cut below the fixtures of the ceiling's lowest panel.
   */
  belowPanels() {
    const region = this.bounds ?? this.room;
    const heights = this.lighting.panels.map((panel) => panel.center[2]);
    const highest = Math.max(...heights);
    const lowest = Math.min(...heights.filter((height) => height >= highest - CEILING_DEPTH));
    const top = Math.min(region.max[2], lowest - FIXTURE_DEPTH);
    if (top <= region.min[2]) return region;
    return new Bounds(region.min.slice(), [region.max[0], region.max[1], top]);
  }

  /**
   * The colour of each room face, lit once by the ceiling: the floor reflects the
   * light from above, the ceiling tiles reflect the floor, the walls see half of each.
   * @returns {{floor: Array<number>, ceiling: Array<number>, wall: Array<number>}} Linear colours.
   */
  faceColors() {
    const light = this.lightColor();
    const overhead = this.overheadLuminance();
    const floor = Reflectance.FLOOR * overhead;
    const wall = (Reflectance.WALL * (overhead + floor)) / 2;
    const tint = (luminance) => light.map((channel) => channel * luminance);
    let ceiling = [0, 0, 0];
    if (this.lighting.panels.length) ceiling = tint(Reflectance.CEILING * floor);
    else if (this.lighting.dome) ceiling = this.lighting.dome.color.map((channel) => channel * overhead);
    return { floor: tint(floor), ceiling, wall: tint(wall) };
  }

  /**
   * @param {Object} panel A panel of the description.
   * @returns {Array<number>} The panel's linear colour relative to the reference luminance.
   */
  panelRadiance(panel) {
    return panel.color.map((channel) => (channel * panel.intensity) / this.referenceLuminance);
  }
}
