/**
 * The ontology page: the classes of the CRAM workspace as cram_owlviz shows them,
 * embedded below the viewer's top bar. The page's fragment names the class shown, so
 * other pages, such as the scene graph, link to a class of the ontology.
 */

/**
 * The ontology browser's start page.
 */
export const ONTOLOGY_BROWSER_URL = 'https://sorynaryon.github.io/cram_owlviz/';

/**
 * The window the ontology page opens in when another page links to one of its classes,
 * so that each further link shows its class in the same window.
 */
export const ONTOLOGY_WINDOW = 'cramera-ontology';

/**
 * The features the embedded browser may use: its "Copy IRI" and "Copy link" buttons
 * write to the clipboard.
 */
const FRAME_PERMISSIONS = 'clipboard-write';

/**
 * The classes the page's elements carry.
 */
const PageClass = Object.freeze({
  BAR: 'ontology-bar',
  FRAME: 'ontology-frame',
});

// %% classes

/**
 * @param {string} classPath A class as a scene names it, by its module and name,
 *   `module.Class`.
 * @returns {string} The entity the ontology browser shows the class as: its name below
 *   the prefix of its top-level package, `package:Class`.
 */
export function ontologyEntityOf(classPath) {
  const [topPackage] = classPath.split('.');
  return `${topPackage}:${classPath.slice(classPath.lastIndexOf('.') + 1)}`;
}

/**
 * @param {string} page The ontology page's URL.
 * @param {string} classPath A class as a scene names it, `module.Class`.
 * @returns {string} The ontology page showing the class.
 */
export function ontologyAddress(page, classPath) {
  const address = new URL(page);
  address.hash = ontologyEntityOf(classPath);
  return address.href;
}

/**
 * @param {string} fragment The ontology page's fragment, with its `#`, or ''.
 * @returns {string} The ontology browser showing the entity the fragment names, or its
 *   start page for none.
 */
export function browserAddress(fragment) {
  return `${ONTOLOGY_BROWSER_URL}${fragment}`;
}

// %% page

export class OntologyPage {
  /**
   * The embedded ontology browser.
   * @type {HTMLIFrameElement}
   */
  frame;

  /**
   * The link opening the ontology browser in a tab of its own.
   * @type {HTMLAnchorElement}
   */
  link;

  /**
   * Show the ontology browser in a page element at the entity the page's fragment
   * names, with a link that opens it in a tab of its own; a new fragment shows its
   * entity.
   * @param {HTMLElement} root The page element.
   * @param {{location: {hash: string}, addEventListener: Function}} window The page's
   *   window.
   */
  constructor(root, window) {
    const document = root.ownerDocument;
    const bar = document.createElement('p');
    bar.className = PageClass.BAR;
    this.link = document.createElement('a');
    this.link.target = '_blank';
    this.link.rel = 'noopener noreferrer';
    this.link.textContent = 'Open in a tab of its own';
    bar.append('The classes of the CRAM workspace, browsed with cram_owlviz. ', this.link);
    this.frame = document.createElement('iframe');
    this.frame.className = PageClass.FRAME;
    this.frame.title = 'CRAM ontology browser';
    this.frame.referrerPolicy = 'no-referrer';
    this.frame.setAttribute('allow', FRAME_PERMISSIONS);
    this.show(window.location.hash);
    window.addEventListener('hashchange', () => this.show(window.location.hash));
    root.replaceChildren(bar, this.frame);
  }

  /**
   * @param {string} fragment The page's fragment, with its `#`, naming the entity to
   *   show, or '' for the browser's start page.
   */
  show(fragment) {
    this.frame.src = browserAddress(fragment);
    this.link.href = browserAddress(fragment);
  }
}
