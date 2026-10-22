/**
 * The status page: which build is published, how its viewer looks, which scenes it has.
 */

import { ViewerApi } from '../core/viewer-api.js';
import { BuildKey, IndexEntryKey, IndexKey, PageReportKey, PluginKey, ViewerInfoKey } from '../protocol.js';
import { SCENE_PARAMETER } from '../core/scene-address.js';

/**
 * The report the build wrote next to its screenshot.
 */
const SHOT_REPORT = 'status/viewer.json';

// %% page

export class StatusPage {
  /**
   * The page.
   * @type {Document}
   */
  #document;

  /**
   * The viewer's routes.
   * @type {ViewerApi}
   */
  #api;

  /**
   * @param {Document} document The page.
   * @param {ViewerApi} api The viewer's routes.
   */
  constructor(document, api) {
    this.#document = document;
    this.#api = api;
  }

  /**
   * Fill the page from the viewer's information, the scenes index and the screenshot report.
   * @param {function(string): Promise<Object|null>} readReport Reads the screenshot
   *   report, or null when the build wrote none.
   * @returns {Promise<void>} Settles once the page is filled.
   */
  async show(readReport) {
    const [info, index, report] = await Promise.all([this.#api.info(), this.#api.scenes(), readReport(SHOT_REPORT)]);
    this.#showBuild(info);
    this.#showScenes(index);
    this.#showReport(report);
  }

  /**
   * @param {Object} info The viewer's information.
   */
  #showBuild(info) {
    const build = info[ViewerInfoKey.BUILD];
    const facts = [['Version', info[ViewerInfoKey.VERSION]], ['Protocol', info[ViewerInfoKey.PROTOCOL_VERSION]]];
    if (build) {
      facts.push(['Commit', this.#commitLink(build)]);
      facts.push(['Built', new Date(build[BuildKey.BUILT_AT]).toLocaleString()]);
    } else facts.push(['Build', 'served from an installation, not a published build']);
    const plugins = (info[ViewerInfoKey.PLUGINS] ?? []).map((plugin) => `${plugin[PluginKey.NAME]} ${plugin[PluginKey.VERSION]}`);
    facts.push(['Plugins', plugins.length ? plugins.join(', ') : 'none']);
    const list = this.#document.getElementById('build-facts');
    list.replaceChildren(...facts.filter(([, value]) => value !== undefined && value !== null).flatMap(([term, value]) => this.#fact(term, value)));
  }

  /**
   * @param {Object} build The build stamp.
   * @returns {Node} The commit, linked to the repository when the build names it.
   */
  #commitLink(build) {
    const commit = build[BuildKey.COMMIT];
    const source = build[BuildKey.SOURCE];
    if (!source) return this.#document.createTextNode(commit);
    const link = this.#document.createElement('a');
    link.href = `${source}/commit/${commit}`;
    link.textContent = commit.slice(0, 12);
    return link;
  }

  /**
   * @param {string} term The fact's name.
   * @param {string|Node} value The fact's value.
   * @returns {Array<HTMLElement>} The term and its description.
   */
  #fact(term, value) {
    const name = this.#document.createElement('dt');
    name.textContent = term;
    const content = this.#document.createElement('dd');
    content.append(value);
    return [name, content];
  }

  /**
   * @param {Object} index The scenes index.
   */
  #showScenes(index) {
    const items = (index[IndexKey.SCENES] ?? []).map((entry) => {
      const item = this.#document.createElement('li');
      const link = this.#document.createElement('a');
      link.href = `./?${SCENE_PARAMETER}=${encodeURIComponent(entry[IndexEntryKey.NAME])}`;
      link.textContent = entry[IndexEntryKey.NAME];
      const labels = this.#document.createElement('span');
      labels.textContent = ` ${[entry[IndexEntryKey.ROBOT], entry[IndexEntryKey.ENVIRONMENT], entry[IndexEntryKey.TASK]].filter(Boolean).join(' · ')}`;
      item.append(link, labels);
      return item;
    });
    this.#document.getElementById('scene-list').replaceChildren(...items);
  }

  /**
   * @param {Object|null} report The screenshot report, or null.
   */
  #showReport(report) {
    const caption = this.#document.getElementById('shot-caption');
    if (!report) {
      caption.textContent = 'This build has no screenshot.';
      this.#document.getElementById('shot').hidden = true;
      return;
    }
    caption.textContent = `Taken by the build in headless ${report[PageReportKey.BROWSER]}. The page reported: ${report[PageReportKey.STATUS]}.`;
  }
}
