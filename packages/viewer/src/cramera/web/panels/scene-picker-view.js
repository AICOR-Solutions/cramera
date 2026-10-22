/**
 * The scene picker in the header: robot, environment and task.
 */

import { SceneChoice } from './scene-choice.js';

// %% view

export class ScenePickerView {
  /**
   * The picker's element.
   * @type {HTMLElement}
   */
  #root;

  /**
   * The choice the pickers show.
   * @type {SceneChoice}
   */
  #choice;

  /**
   * Called with the chosen bundle's name.
   * @type {function(string): void}
   */
  #onChoose;

  /**
   * @param {HTMLElement} root The picker's element.
   * @param {SceneChoice} choice The choice the pickers show and change.
   * @param {function(string): void} onChoose Called with the chosen bundle's name.
   */
  constructor(root, choice, onChoose) {
    this.#root = root;
    this.#choice = choice;
    this.#onChoose = onChoose;
    this.render();
  }

  /**
   * Show the pickers for the current choice.
   */
  render() {
    const pickers = [
      this.#picker('Robot', this.#choice.robots(), this.#choice.robot, (value) => this.#choice.chooseRobot(value)),
      this.#picker('Environment', this.#choice.environments(), this.#choice.environment, (value) => this.#choice.chooseEnvironment(value)),
      this.#picker('Task', this.#choice.tasks(), this.#choice.task, (value) => this.#choice.chooseTask(value)),
    ];
    this.#root.replaceChildren(...pickers);
  }

  /**
   * @param {string} label The picker's label.
   * @param {Array<string>} options The labels offered.
   * @param {string|null} selected The label chosen now.
   * @param {function(string): void} choose Changes the choice.
   * @returns {HTMLElement} The labelled picker.
   */
  #picker(label, options, selected, choose) {
    const document = this.#root.ownerDocument;
    const wrapper = document.createElement('label');
    wrapper.className = 'picker';
    const caption = document.createElement('span');
    caption.textContent = label;
    const select = document.createElement('select');
    for (const value of options) {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = value;
      select.append(option);
    }
    select.value = selected ?? '';
    select.disabled = options.length < 2;
    select.addEventListener('change', () => {
      choose(select.value);
      this.render();
      this.#onChoose(this.#choice.scene);
    });
    wrapper.append(caption, select);
    return wrapper;
  }
}
