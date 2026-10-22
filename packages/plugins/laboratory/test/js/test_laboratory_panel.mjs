import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  BenchKey,
  CameraKey,
  ContactPhysicsKey,
  LaboratoryCatalogKey,
  LaboratoryChoiceKey,
  LaboratoryName,
  LaboratoryRoute,
  LaboratorySceneKey,
  SimulationAnswerKey,
  SimulationState,
  SnapshotKey,
  TargetRequestKey,
  TaskRunKey,
  TaskRunState,
  ViewerRoute,
} from 'cramera-viewer/protocol.js';

import { LaboratoryClient } from '../../src/cramera_laboratory/web/laboratory-client.js';
import { LOOK_OFFSET, LaboratoryPanel, MOVE_STEP, Text } from '../../src/cramera_laboratory/web/laboratory-panel.js';
import { FakeApi, FakeFetch, readDataset } from './fakes.mjs';
import { FakeDocument } from './support/fake-document.mjs';

const routeUrl = (route) => `http://viewer${ViewerRoute.PLUGIN_API}${LaboratoryName.PLUGIN}/${route}`;
const SCENE = 'aicor_medical_lab_contact_physics';
const CATALOG = {
  [LaboratoryCatalogKey.LABORATORIES]: [
    { name: 'aicor_medical_lab', title: 'AICOR Laboratory', installed: false, instruments: 0 },
    { name: 'aicor_medical_lab_large', title: 'AICOR Laboratory', installed: true, instruments: 15 },
  ],
  [LaboratoryCatalogKey.PHYSICS_AVAILABLE]: true,
};

function setUp() {
  const network = new FakeFetch();
  const shown = [];
  const looks = [];
  const panel = new LaboratoryPanel(
    new FakeDocument(),
    new LaboratoryClient((url, options) => network.fetch(url, options), new FakeApi()),
    (name) => shown.push(name),
    (position, target) => looks.push({ position, target }),
  );
  return { network, shown, looks, panel };
}

const buttons = (element, text) => element.findAll((child) => child.tagName === 'BUTTON' && child.textContent === text);
const answer = () => ({ [SimulationAnswerKey.STATE]: SimulationState.RUNNING, [SimulationAnswerKey.SCENE]: SCENE, [SimulationAnswerKey.SNAPSHOT]: readDataset('snapshot.json') });

test('each laboratory can be opened and simulated', async () => {
  const { panel, network, shown } = setUp();
  panel.showLaboratories(CATALOG);
  network.answer(routeUrl(LaboratoryRoute.INSTALL), 200, { scene: 'aicor_medical_lab' });
  buttons(panel.laboratories, Text.OPEN)[0].click();
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(network.requests[0].body, { [LaboratoryChoiceKey.LABORATORY]: 'aicor_medical_lab' });
  assert.deepEqual(shown, ['aicor_medical_lab']);
  network.answer(routeUrl(LaboratoryRoute.START), 200, answer());
  buttons(panel.laboratories, Text.SIMULATE)[1].click();
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(shown, ['aicor_medical_lab', SCENE]);
});

test('without MuJoCo the simulation cannot be started', () => {
  const { panel } = setUp();
  panel.showLaboratories({ ...CATALOG, [LaboratoryCatalogKey.PHYSICS_AVAILABLE]: false });
  assert.ok(buttons(panel.laboratories, Text.SIMULATE).every((button) => button.disabled));
  assert.ok(panel.laboratories.innerText.includes(Text.NO_PHYSICS));
});

test('the simulation shows a section per instrument it measures', () => {
  const { panel } = setUp();
  const controls = readDataset('controls.json');
  panel.showAnswer(answer(), controls, { [LaboratorySceneKey.INSTRUMENTS]: { instruments: [{ id: 'vortex_mixer', joints: [{ name: 'j' }] }] } });
  const headings = panel.simulation.findAll((child) => child.tagName === 'H3').map((heading) => heading.textContent);
  assert.deepEqual(headings, [Text.VIEW, Text.OBJECT, Text.SCALE, Text.CENTRIFUGE, Text.REFRIGERATOR, Text.DRAWER, Text.DISPENSER, Text.INSTRUMENT_COLLECTION]);
  assert.ok(panel.status.textContent.startsWith(SimulationState.RUNNING));
  assert.deepEqual(panel.objectChoice.children.map((option) => option.value), controls[ContactPhysicsKey.OBJECTS]);
});

test('a move pulls the selected object from its current target', async () => {
  const { panel, network } = setUp();
  const shown = answer();
  panel.showAnswer(shown, readDataset('controls.json'));
  network.answer(routeUrl(LaboratoryRoute.TARGET), 200, shown);
  buttons(panel.simulation, Text.LIFT)[0].click();
  await new Promise((resolve) => setImmediate(resolve));
  const target = shown[SimulationAnswerKey.SNAPSHOT][SnapshotKey.TARGET];
  const sent = network.requests[0].body;
  assert.equal(sent[TargetRequestKey.KEY], target[TargetRequestKey.KEY]);
  assert.deepEqual(sent[TargetRequestKey.POSITION], target[TargetRequestKey.POSITION].map((value, axis) => value + (axis === 2 ? MOVE_STEP : 0)));
});

test('a refused command shows the laboratory’s reason', async () => {
  const { panel, network } = setUp();
  panel.showAnswer(answer(), readDataset('controls.json'));
  network.answer(routeUrl(LaboratoryRoute.TARE), 409, { error: 'Wait for the scale’s reading to settle.' });
  buttons(panel.simulation, Text.TARE)[0].click();
  await new Promise((resolve) => setImmediate(resolve));
  assert.ok(panel.message.textContent.startsWith('Wait'));
  assert.ok(panel.message.classList.contains('laboratory-error'));
});

test('the view section offers the bench cameras and a close look', () => {
  const { panel, looks } = setUp();
  const bench = readDataset('bench_cameras.json');
  panel.showAnswer(answer(), readDataset('controls.json'), { [LaboratorySceneKey.LABORATORY]: bench });
  const [name, camera] = Object.entries(bench[BenchKey.CAMERAS])[0];
  buttons(panel.simulation, name)[0].click();
  buttons(panel.simulation, Text.LOOK)[0].click();
  assert.deepEqual(looks[0], { position: camera[CameraKey.POSITION], target: camera[CameraKey.TARGET] });
  const object = readDataset('snapshot.json')[SnapshotKey.OBJECTS][panel.selectedObject()].slice(0, 3);
  assert.deepEqual(looks[1].target, object);
  assert.deepEqual(looks[1].position, object.map((value, axis) => value + LOOK_OFFSET[axis]));
});

test('the view section offers each workstation of the expanded laboratory', () => {
  const { panel, looks } = setUp();
  const station = { id: 'measurement', label: '04 \u00b7 Analysis', camera: { position: [2, 0.7, 1.9], target: [1, 2.4, 1.1] } };
  panel.showAnswer(answer(), readDataset('controls.json'), { [LaboratorySceneKey.INSTRUMENTS]: { instruments: [], stations: [station] } });
  buttons(panel.simulation, station.label)[0].click();
  assert.deepEqual(looks, [{ position: station.camera.position, target: station.camera.target }]);
});

test('hiding the simulation forgets its controls', () => {
  const { panel } = setUp();
  panel.showAnswer(answer(), readDataset('controls.json'));
  panel.hideSimulation();
  assert.equal(panel.objectChoice, null);
  assert.ok(panel.simulation.innerText.includes(Text.NOT_SHOWN));
});

test('the devices link to their URDFs', () => {
  const { panel } = setUp();
  panel.showDevices({ devices: [{ name: 'scale', title: 'AICOR scale', description: 'model.urdf', movingJoints: 0 }] });
  const [link] = panel.devices.findAll((child) => child.tagName === 'A');
  assert.equal(link.href, routeUrl(`${LaboratoryRoute.DEVICE_FILES}scale/model.urdf`));
});

test('the transfer demo runs, can be ended and opens its recording', async () => {
  const { panel, network, shown } = setUp();
  const scene = 'aicor_medical_lab_pr2_transfer';
  const followed = [];
  panel.showTransfer({ [TaskRunKey.STATE]: TaskRunState.IDLE, [TaskRunKey.SCENE]: scene }, () => followed.push(true));
  network.answer(routeUrl(LaboratoryRoute.TRANSFER_START), 200, { [TaskRunKey.STATE]: TaskRunState.RUNNING, [TaskRunKey.SCENE]: scene });
  buttons(panel.demos, Text.RUN)[0].click();
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(followed, [true]);
  assert.equal(buttons(panel.demos, Text.END_RUN).length, 1);
  panel.showTransfer({ [TaskRunKey.STATE]: TaskRunState.RECORDED, [TaskRunKey.SCENE]: scene }, () => null);
  buttons(panel.demos, Text.OPEN_RECORDING)[0].click();
  assert.deepEqual(shown, [scene]);
});

test('a failed transfer shows its output and may run again', () => {
  const { panel } = setUp();
  panel.showTransfer({ [TaskRunKey.STATE]: TaskRunState.FAILED, [TaskRunKey.SCENE]: 'x', [TaskRunKey.ERROR]: 'the vessel is still held' }, () => null);
  assert.ok(panel.demos.innerText.includes('the vessel is still held'));
  assert.equal(buttons(panel.demos, Text.RUN).length, 1);
});
