/**
 * The top bar every page of the viewer shares: the AICOR logo, one link per page (the
 * scene page and the navigation entries the plugins declare), the build stamp and the
 * View menu with the colour theme.
 */

import {
  BuildKey,
  NavigationGroup,
  NavigationKey,
  PageStorageKey,
  PluginKey,
  Theme,
  ViewerInfoKey,
} from '../protocol.js';
import { withPanel } from '../core/scene-address.js';

/**
 * How many characters of a commit hash the build stamp shows.
 */
export const SHORT_COMMIT = 7;

/**
 * The logo's file below the viewer's root.
 */
const LOGO = '/images/aicor-logo.png';

/**
 * The status page below the viewer's root.
 */
const STATUS_PAGE = '/status.html';

/**
 * The identity of the scene page's own entry.
 */
export const SCENE_PAGE = 'scene';

/**
 * The text of the scene page's entry.
 */
const SCENE_TITLE = 'Scene';

/**
 * The texts of the theme choice.
 */
const THEME_TITLES = Object.freeze({ [Theme.DARK]: 'Dark', [Theme.LIGHT]: 'Light' });

// %% theme

/**
 * The colour theme of a page: dark unless a person chose light; the choice is kept in
 * the browser's local storage where the browser allows it.
 */
export class ThemeSetting {
  /**
   * The page's root element, which carries the theme.
   * @type {HTMLElement}
   */
  #root;

  /**
   * The browser's local storage, or null where the page has none.
   * @type {Storage|null}
   */
  #storage;

  /**
   * @param {HTMLElement} root The page's root element.
   * @param {Storage|null} storage The browser's local storage, or null.
   */
  constructor(root, storage) {
    this.#root = root;
    this.#storage = storage;
  }

  /**
   * @returns {string} The chosen `Theme` value, dark when none was chosen or storage
   *   cannot be read.
   */
  get theme() {
    const stored = this.#stored();
    return Object.values(Theme).includes(stored) ? stored : Theme.DARK;
  }

  /**
   * Show the chosen theme.
   */
  apply() {
    this.#root.dataset.theme = this.theme;
  }

  /**
   * Choose a theme, show it and remember it.
   * @param {string} theme A `Theme` value.
   */
  choose(theme) {
    try {
      this.#storage?.setItem(PageStorageKey.THEME, theme);
    } catch {
      // Storage refused (private window, blocked site data): the choice lasts this page.
    }
    this.#root.dataset.theme = theme;
  }

  /**
   * @returns {string|null} The stored theme, or null.
   */
  #stored() {
    try {
      return this.#storage?.getItem(PageStorageKey.THEME) ?? null;
    } catch {
      return null;
    }
  }
}

/**
 * @param {Window} window The page's window.
 * @returns {Storage|null} Its local storage, or null where the browser refuses it.
 */
export function localStorageOf(window) {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

// %% navigation

/**
 * One link of the top bar.
 */
export class PageLink {
  /**
   * @param {string} identity The page's identity: `SCENE_PAGE` or a plugin's name.
   * @param {string} title The link's text.
   * @param {string} href Where it leads.
   * @param {string|null} panel The panel it shows on the scene page, or null for a page.
   */
  constructor(identity, title, href, panel) {
    /**
     * The page's identity.
     * @type {string}
     */
    this.identity = identity;
    /**
     * The link's text.
     * @type {string}
     */
    this.title = title;
    /**
     * Where it leads.
     * @type {string}
     */
    this.href = href;
    /**
     * The panel it shows on the scene page, or null for a page of its own.
     * @type {string|null}
     */
    this.panel = panel;
  }
}

/**
 * @param {Object} info The viewer's information.
 * @param {function(string): string} url The URL of a viewer route.
 * @returns {Array<PageLink>} The scene page's link, then one per plugin entry, ordered
 *   by group and title.
 */
export function pageLinksOf(info, url) {
  const groups = Object.values(NavigationGroup);
  const viewer = url('/');
  const entries = (info[ViewerInfoKey.PLUGINS] ?? [])
    .filter((plugin) => plugin[PluginKey.NAVIGATION])
    .map((plugin) => ({ name: plugin[PluginKey.NAME], entry: plugin[PluginKey.NAVIGATION] }))
    .sort((first, second) =>
      groups.indexOf(first.entry[NavigationKey.GROUP]) - groups.indexOf(second.entry[NavigationKey.GROUP])
      || first.entry[NavigationKey.TITLE].localeCompare(second.entry[NavigationKey.TITLE]));
  return [
    new PageLink(SCENE_PAGE, SCENE_TITLE, viewer, null),
    ...entries.map(({ name, entry }) => {
      const page = entry[NavigationKey.PAGE];
      return page
        ? new PageLink(name, entry[NavigationKey.TITLE], url(page), null)
        : new PageLink(name, entry[NavigationKey.TITLE], withPanel(viewer, name).href, name);
    }),
  ];
}

/**
 * @param {Object} info The viewer's information.
 * @returns {string} The viewer's version, with the commit and time of a published build.
 */
export function versionOf(info) {
  const build = info[ViewerInfoKey.BUILD];
  const stamp = build ? ` · ${build[BuildKey.COMMIT].slice(0, SHORT_COMMIT)} · ${build[BuildKey.BUILT_AT]}` : '';
  return `v${info[ViewerInfoKey.VERSION] ?? '?'}${stamp}`;
}

// %% header

export class SiteHeader {
  /**
   * The header element.
   * @type {HTMLElement}
   */
  #root;

  /**
   * The URL of a viewer route.
   * @type {function(string): string}
   */
  #url;

  /**
   * The identity of the page the header is on.
   * @type {string}
   */
  #current;

  /**
   * Shows a plugin's panel on this page instead of following its link, or null on a
   * page without the scene's panels.
   * @type {function(string): void|null}
   */
  #showPanel;

  /**
   * The links.
   * @type {HTMLElement}
   */
  #navigation;

  /**
   * The build stamp.
   * @type {HTMLAnchorElement}
   */
  #version;

  /**
   * @param {HTMLElement} root The header element.
   * @param {function(string): string} url The URL of a viewer route.
   * @param {ThemeSetting} theme The page's theme.
   * @param {string} current The identity of the page the header is on.
   * @param {function(string): void|null} showPanel Shows a plugin's panel on this page,
   *   or null on a page without the scene's panels.
   */
  constructor(root, url, theme, current, showPanel = null) {
    const document = root.ownerDocument;
    this.#root = root;
    this.#url = url;
    this.#current = current;
    this.#showPanel = showPanel;
    const brand = document.createElement('a');
    brand.className = 'brand';
    brand.href = url('/');
    brand.setAttribute('aria-label', 'cramera home');
    const logo = document.createElement('img');
    logo.className = 'logo';
    logo.src = url(LOGO);
    logo.alt = 'AICOR — Artificial Intelligence Powered Cognition-Enabled Robotics';
    brand.append(logo);
    this.#navigation = document.createElement('nav');
    this.#navigation.className = 'page-tabs';
    this.#navigation.setAttribute('aria-label', 'Pages');
    const actions = document.createElement('div');
    actions.className = 'topbar-actions';
    this.#version = document.createElement('a');
    this.#version.className = 'version';
    this.#version.id = 'viewer-version';
    this.#version.href = url(STATUS_PAGE);
    this.#version.title = 'Which build this is';
    actions.append(this.#version, this.#viewMenu(theme));
    root.replaceChildren(brand, this.#navigation, actions);
  }

  /**
   * Show the pages and the build the viewer's information names.
   * @param {Object} info The viewer's information.
   * @returns {Array<PageLink>} The links shown.
   */
  show(info) {
    const document = this.#root.ownerDocument;
    const links = pageLinksOf(info, this.#url);
    this.#navigation.replaceChildren(
      ...links.map((link) => {
        const anchor = document.createElement('a');
        anchor.href = link.href;
        anchor.textContent = link.title;
        anchor.dataset.page = link.identity;
        if (link.identity === this.#current) anchor.setAttribute('aria-current', 'page');
        if (link.panel && this.#showPanel) {
          anchor.addEventListener('click', (event) => {
            event.preventDefault();
            this.#showPanel(link.panel);
          });
        }
        return anchor;
      }),
    );
    this.#version.textContent = versionOf(info);
    return links;
  }

  /**
   * @param {ThemeSetting} theme The page's theme.
   * @returns {HTMLElement} The View button and its menu.
   */
  #viewMenu(theme) {
    const document = this.#root.ownerDocument;
    const menu = document.createElement('div');
    menu.className = 'view-menu';
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.textContent = '⊞ View';
    toggle.setAttribute('aria-expanded', 'false');
    const list = document.createElement('div');
    list.className = 'view-menu-list';
    list.hidden = true;
    const label = document.createElement('label');
    const caption = document.createElement('span');
    caption.textContent = 'Theme';
    const choice = document.createElement('select');
    choice.setAttribute('aria-label', 'Theme');
    for (const [value, title] of Object.entries(THEME_TITLES)) {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = title;
      choice.append(option);
    }
    choice.value = theme.theme;
    choice.addEventListener('change', () => theme.choose(choice.value));
    label.append(caption, choice);
    list.append(label);
    toggle.addEventListener('click', () => {
      list.hidden = !list.hidden;
      toggle.setAttribute('aria-expanded', String(!list.hidden));
    });
    menu.append(toggle, list);
    return menu;
  }
}
