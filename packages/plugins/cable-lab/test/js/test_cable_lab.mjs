import { test } from 'node:test';
import assert from 'node:assert/strict';

import { PanelHost } from '../../../panels/panel-host.js';
import {
  CableConfigurationKey,
  CableLabKey,
  ErrorKey,
  GripperAction,
  GripperCommandKey,
  PluginName,
  SimulationLifecycle,
} from '../../../protocol.js';
import { LINK_TEXT, register } from '../index.js';
import { CableLabClient } from '../lab/cable-client.js';
import { ConfigurationForm, NUMBER_FIELDS, OTHER_FRICTION } from '../lab/configuration-form.js';
import { ElementId, GRASP_TEXT, LIFECYCLE_TEXT, LabPage, POLL_MILLISECONDS } from '../lab/lab-page.js';
import {
  BUTTON_ACTIONS,
  FORM_FIELDS,
  FakeClient,
  FakeForm,
  FakeLabDocument,
  FakeStatus,
  FakeTimers,
  FakeView,
  PAGE,
  RUNNING_STATE,
} from './fakes.mjs';
import { FakeDocument } from './support/fake-document.mjs';

/**
 * The page over fake routes.
 */
class PageSetup {
  constructor(withView = true) {
    this.document = new FakeLabDocument();
    this.client = new FakeClient();
    this.view = withView ? new FakeView() : null;
    this.timers = new FakeTimers();
    this.status = new FakeStatus();
    this.page = new LabPage(this.document, this.client, this.view, this.timers, this.status);
  }

  element(id) {
    return this.document.getElementById(id);
  }
}

// %% markup

test('every field of the form is named by a configuration key', () => {
  const keys = Object.values(CableConfigurationKey);
  assert.ok(FORM_FIELDS.length > 0);
  for (const name of FORM_FIELDS) assert.ok(keys.includes(name), name);
});

test('every element the page script uses is in the markup', () => {
  for (const id of Object.values(ElementId)) assert.ok(PAGE.includes(`id="${id}"`), id);
});

test('every gripper button sends a gripper action', () => {
  const actions = Object.values(GripperAction);
  for (const action of BUTTON_ACTIONS) assert.ok(actions.includes(action), action);
});

// %% form

test('the form reads numbers, the sliding friction and the anchor', () => {
  const form = new ConfigurationForm(new FakeForm(new FakeDocument()));
  const configuration = form.read();
  for (const key of NUMBER_FIELDS) assert.equal(typeof configuration[key], 'number');
  assert.deepEqual(configuration[CableConfigurationKey.FRICTION].slice(1), [...OTHER_FRICTION]);
  assert.equal(configuration[CableConfigurationKey.ANCHORED], true);
});

test('a configuration shown in the form reads back the same', () => {
  const form = new ConfigurationForm(new FakeForm(new FakeDocument()));
  const shown = {
    [CableConfigurationKey.SEGMENT_COUNT]: 12,
    [CableConfigurationKey.FRICTION]: [0.4, ...OTHER_FRICTION],
    [CableConfigurationKey.ANCHORED]: false,
  };
  form.apply(shown);
  const read = form.read();
  for (const [key, value] of Object.entries(shown)) assert.deepEqual(read[key], value);
});

test('a preset puts the defaults back with the chosen anchor', () => {
  const form = new ConfigurationForm(new FakeForm(new FakeDocument()));
  const defaults = form.read();
  form.apply({ [CableConfigurationKey.SEGMENT_COUNT]: 50 });
  form.preset(false);
  assert.equal(form.read()[CableConfigurationKey.SEGMENT_COUNT], defaults[CableConfigurationKey.SEGMENT_COUNT]);
  assert.equal(form.read()[CableConfigurationKey.ANCHORED], false);
  assert.match(form.lengthText(), new RegExp(String(defaults[CableConfigurationKey.SEGMENT_COUNT])));
});

// %% page

test('a running state shows its readings and offers the gripper', () => {
  const setup = new PageSetup();
  setup.page.show(RUNNING_STATE);
  const grasp = RUNNING_STATE[CableLabKey.GRASP];
  assert.equal(setup.element(ElementId.STATUS).textContent, LIFECYCLE_TEXT[SimulationLifecycle.RUNNING]);
  assert.equal(setup.element(ElementId.GRASP).textContent, GRASP_TEXT[grasp[CableLabKey.STATE]]);
  assert.equal(setup.element(ElementId.CONTACTS).textContent, String(grasp[CableLabKey.CONTACT_COUNT]));
  assert.ok(setup.document.buttons.every((button) => !button.disabled));
  assert.equal(setup.element(ElementId.EMPTY).hidden, true);
  assert.deepEqual(setup.view.shown, [RUNNING_STATE]);
  assert.deepEqual(setup.status.reports.at(-1), ['ready', LIFECYCLE_TEXT[SimulationLifecycle.RUNNING]]);
});

test('an idle lab offers building but not the gripper', () => {
  const setup = new PageSetup();
  setup.page.show({ [CableLabKey.LIFECYCLE]: SimulationLifecycle.IDLE });
  assert.ok(setup.document.buttons.every((button) => button.disabled));
  assert.equal(setup.element(ElementId.START).disabled, false);
  assert.equal(setup.element(ElementId.RESET).disabled, true);
});

test('building sends the form\'s configuration', async () => {
  const setup = new PageSetup();
  setup.view.needsFraming = false;
  setup.element(ElementId.FORM).dispatch('submit');
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(setup.client.requests, [['start', setup.page.form.read()]]);
  assert.equal(setup.view.needsFraming, true);
  assert.equal(setup.page.state[CableLabKey.LIFECYCLE], SimulationLifecycle.RUNNING);
});

test('a gripper button sends its action', async () => {
  const setup = new PageSetup();
  setup.document.buttons[0].dispatch('click');
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(setup.client.requests, [['command', { [GripperCommandKey.ACTION]: BUTTON_ACTIONS[0] }]]);
});

test('reset and stop send their requests', async () => {
  const setup = new PageSetup();
  await setup.page.perform(() => setup.client.reset());
  setup.element(ElementId.STOP).dispatch('click');
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(setup.client.requests.map((request) => request[0]), ['reset', 'stop']);
});

test('a refused change shows the reason', async () => {
  const setup = new PageSetup();
  const reason = 'Build and start a cable first.';
  setup.client.failure = Object.assign(new Error(reason), { reason });
  await setup.page.perform(() => setup.client.command({}));
  assert.equal(setup.element(ElementId.ERROR).textContent, reason);
  assert.equal(setup.element(ElementId.ERROR).hidden, false);
});

test('polling shows the state and reads again later', async () => {
  const setup = new PageSetup();
  setup.client.current = RUNNING_STATE;
  await setup.page.poll();
  assert.equal(setup.page.state, RUNNING_STATE);
  assert.deepEqual([...setup.timers.pending.values()].map((timer) => timer.milliseconds), [POLL_MILLISECONDS]);
  setup.page.close();
  assert.equal(setup.timers.pending.size, 0);
});

test('an unreachable lab is reported as a failed page', async () => {
  const setup = new PageSetup();
  setup.client.failure = new Error('connection refused');
  await setup.page.poll();
  assert.equal(setup.status.reports.at(-1)[0], 'failed');
});

test('without WebGL the page says so and still shows the readings', () => {
  const setup = new PageSetup(false);
  setup.page.show(RUNNING_STATE);
  assert.equal(setup.element(ElementId.WARNING).hidden, false);
});

test('the semantic points switch reaches the view', () => {
  const setup = new PageSetup();
  setup.element(ElementId.POINTS).dispatch('change', { target: { checked: true } });
  assert.equal(setup.view.pointsShown, true);
});

// %% client and panel

test('the client posts to the plugin\'s routes below the viewer', async () => {
  const requests = [];
  const fetch = async (url, init) => {
    requests.push({ url, init });
    return { ok: true, json: async () => RUNNING_STATE };
  };
  const client = new CableLabClient(fetch, 'http://127.0.0.1:8711/viewer/');
  const command = { [GripperCommandKey.ACTION]: GripperAction.PINCH };
  await client.command(command);
  await client.state();
  assert.equal(requests[0].url, `http://127.0.0.1:8711/viewer/api/plugins/${PluginName.CABLE_LAB}/command`);
  assert.deepEqual(JSON.parse(requests[0].init.body), command);
  assert.match(requests[1].url, /\/state$/);
});

test('the client reports the reason of a refused request', async () => {
  const reason = 'Build and start a cable first.';
  const fetch = async () => ({ ok: false, status: 409, headers: new Map([['Content-Type', 'application/json']]), json: async () => ({ [ErrorKey.ERROR]: reason }) });
  const client = new CableLabClient(fetch, 'http://127.0.0.1/');
  await assert.rejects(client.stop(), (error) => error.reason === reason && error.status === 409);
});

test('the panel links to the lab page', () => {
  const document = new FakeDocument();
  const panels = new PanelHost(document.createElement('aside'));
  const panel = register({ panels }, document, 'http://127.0.0.1/plugins/cable-lab/cable-lab.html');
  assert.deepEqual(panels.identifiers(), [PluginName.CABLE_LAB]);
  const link = panel.element.findAll((child) => child.tagName === 'A')[0];
  assert.equal(link.textContent, LINK_TEXT);
});
