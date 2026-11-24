/**
 * The images of what the robot's perception saw, as a validation and a scan carry them.
 */

import { InlineImageKey } from '../../../protocol.js';
import { IMAGE_SOURCES } from '../../../panels/perception-panel.js';

/**
 * @param {Object} elements Creates the page's elements.
 * @param {Array<Object>} images `InlineImage`s.
 * @returns {Array<HTMLElement>} A figure for each image, captioned with its title and source.
 */
export function seenImageFigures(elements, images) {
  return images.map((seen) => {
    const figure = elements.create('figure', 'seen-image');
    const image = elements.create('img');
    image.src = seen[InlineImageKey.URL];
    image.alt = seen[InlineImageKey.TITLE];
    const source = IMAGE_SOURCES[seen[InlineImageKey.SOURCE]] ?? seen[InlineImageKey.SOURCE];
    figure.append(image, elements.create('figcaption', '', `${seen[InlineImageKey.TITLE]} (${source})`));
    return figure;
  });
}
