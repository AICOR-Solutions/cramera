/**
 * The images of what the robot's perception saw, as a validation and a scan of the scene
 * carry them: each shown whole, captioned with what drew it and where it comes from.
 */

import { InlineImageKey } from '../../../protocol.js';
import { IMAGE_SOURCES } from '../../../panels/perception-panel.js';

/**
 * The class of each image's figure.
 */
export const SEEN_IMAGE_CLASS = 'seen-image';

/**
 * @param {Object} elements Creates the page's elements.
 * @param {Array<Object>} images `InlineImage`s.
 * @returns {Array<HTMLElement>} A figure for each image, captioned with the title and
 *   the source of the image.
 */
export function seenImageFigures(elements, images) {
  return images.map((seen) => {
    const figure = elements.create('figure', SEEN_IMAGE_CLASS);
    const image = elements.create('img');
    image.src = seen[InlineImageKey.URL];
    image.alt = seen[InlineImageKey.TITLE];
    const source = IMAGE_SOURCES[seen[InlineImageKey.SOURCE]] ?? seen[InlineImageKey.SOURCE];
    figure.append(image, elements.create('figcaption', '', `${seen[InlineImageKey.TITLE]} (${source})`));
    return figure;
  });
}
