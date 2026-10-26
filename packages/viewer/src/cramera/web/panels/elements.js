/**
 * Building the elements of a panel: HTML elements with their classes and text, and SVG
 * drawings.
 */

/**
 * The namespace of SVG elements.
 */
export const SVG_NAMESPACE = 'http://www.w3.org/2000/svg';

/**
 * @param {Document} document The page.
 * @param {string} tag The element's tag.
 * @param {string} className Its classes; empty for none.
 * @param {string|number|null} text Its text; null for none.
 * @param {Array<HTMLElement|string>} children Its children and texts, after the text.
 * @returns {HTMLElement} The element.
 */
export function element(document, tag, className = '', text = null, children = []) {
  const built = document.createElement(tag);
  if (className) built.className = className;
  if (text !== null) built.textContent = String(text);
  if (children.length) built.append(...children);
  return built;
}

/**
 * @param {Document} document The page.
 * @param {string} tag The SVG element's tag.
 * @param {Object<string, string|number>} attributes Its attributes.
 * @param {Array<Element>} children Its children.
 * @returns {Element} The SVG element.
 */
export function svgElement(document, tag, attributes = {}, children = []) {
  const built = document.createElementNS(SVG_NAMESPACE, tag);
  for (const [name, value] of Object.entries(attributes)) built.setAttribute(name, value);
  if (children.length) built.append(...children);
  return built;
}
