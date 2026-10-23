/**
 * The ontology page: the classes of the CRAM workspace as cram_owlviz shows them,
 * embedded below the viewer's top bar.
 */

/**
 * The ontology browser's start page.
 */
export const ONTOLOGY_BROWSER_URL = 'https://sorynaryon.github.io/cram_owlviz/';

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

// %% page

export class OntologyPage {
  /**
   * The embedded ontology browser.
   * @type {HTMLIFrameElement}
   */
  frame;

  /**
   * Show the ontology browser in a page element, with a link that opens it in a tab of
   * its own.
   * @param {HTMLElement} root The page element.
   */
  constructor(root) {
    const document = root.ownerDocument;
    const bar = document.createElement('p');
    bar.className = PageClass.BAR;
    const link = document.createElement('a');
    link.href = ONTOLOGY_BROWSER_URL;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'Open in a tab of its own';
    bar.append('The classes of the CRAM workspace, browsed with cram_owlviz. ', link);
    this.frame = document.createElement('iframe');
    this.frame.className = PageClass.FRAME;
    this.frame.title = 'CRAM ontology browser';
    this.frame.referrerPolicy = 'no-referrer';
    this.frame.setAttribute('allow', FRAME_PERMISSIONS);
    this.frame.src = ONTOLOGY_BROWSER_URL;
    root.replaceChildren(bar, this.frame);
  }
}
