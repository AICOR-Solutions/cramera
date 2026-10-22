/**
 * The colour of a black body at a temperature, as USD lights tint their colour.
 */

/**
 * The coolest and warmest temperature the Planckian-locus fit covers, in kelvin.
 */
export const LOCUS_RANGE = Object.freeze([1667, 25000]);

// %% black body

/**
 * @param {number} kelvin A colour temperature.
 * @returns {Array<number>} The CIE 1931 chromaticity `[x, y]` of a black body at that
 *   temperature, by Kim et al.'s cubic fit of the Planckian locus.
 */
export function planckianChromaticity(kelvin) {
  const t = Math.min(LOCUS_RANGE[1], Math.max(LOCUS_RANGE[0], kelvin));
  const x =
    t <= 4000
      ? -0.2661239e9 / (t * t * t) - 0.2343589e6 / (t * t) + 0.8776956e3 / t + 0.17991
      : -3.0258469e9 / (t * t * t) + 2.1070379e6 / (t * t) + 0.2226347e3 / t + 0.24039;
  let y;
  if (t <= 2222) y = -1.1063814 * x * x * x - 1.3481102 * x * x + 2.18555832 * x - 0.20219683;
  else if (t <= 4000) y = -0.9549476 * x * x * x - 1.37418593 * x * x + 2.09137015 * x - 0.16748867;
  else y = 3.081758 * x * x * x - 5.8733867 * x * x + 3.75112997 * x - 0.37001483;
  return [x, y];
}

/**
 * @param {number} kelvin A colour temperature.
 * @returns {Array<number>} The linear sRGB (D65) colour of a black body at that
 *   temperature, at a luminance of 1.
 */
export function blackBody(kelvin) {
  const [x, y] = planckianChromaticity(kelvin);
  const X = x / y;
  const Z = (1 - x - y) / y;
  return [
    3.2404542 * X - 1.5371385 - 0.4985314 * Z,
    -0.969266 * X + 1.8760108 + 0.041556 * Z,
    0.0556434 * X - 0.2040259 + 1.0572252 * Z,
  ].map((channel) => Math.max(0, channel));
}
