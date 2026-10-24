import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import * as THREE from 'three';

import { CatalogKey, DraftKey, InstanceKey, LimitsKey, PrimitiveShape, ReservedResourceRoot, ResourceCategory, ResourceKey, ResourceKind } from 'cramera-viewer/protocol.js';
import { DraftCheck, InvalidDraft } from '../../src/cramera_scene_builder/web/builder/draft-check.js';
import { DraftState } from '../../src/cramera_scene_builder/web/builder/draft-state.js';
import { primitiveObject } from '../../src/cramera_scene_builder/web/builder/resource-loading.js';

const read = (name) => JSON.parse(readFileSync(new URL(`dataset/${name}`, import.meta.url), 'utf8'));
const catalog = read('catalog.json');
const box = `${ReservedResourceRoot.PRIMITIVES}/${PrimitiveShape.BOX}`;
const primitives = Object.values(PrimitiveShape).map((shape) => ({
  [ResourceKey.IDENTIFIER]: `${ReservedResourceRoot.PRIMITIVES}/${shape}`,
  [ResourceKey.NAME]: shape,
  [ResourceKey.KIND]: ResourceKind.PRIMITIVE,
  [ResourceKey.CATEGORY]: ResourceCategory.PRIMITIVE,
  [ResourceKey.NOTICES]: [],
}));
const check = () => new DraftCheck(catalog[CatalogKey.LIMITS], catalog[CatalogKey.DEFAULT_APPEARANCE]);

function state() {
  const created = new DraftState(check());
  created.setResources([...primitives, ...catalog[CatalogKey.RESOURCES]]);
  return created;
}

test('a primitive shape is placed like any resource, without notices', () => {
  const edited = state();
  const instance = edited.add(box, { scale: [1.2, 0.6, 0.9] });
  assert.equal(instance[InstanceKey.ASSET], box);
  assert.deepEqual(instance[InstanceKey.SCALE], [1.2, 0.6, 0.9]);
  assert.deepEqual(edited.draft[DraftKey.NOTICES], []);
});

test('a description is kept with its line breaks, and clearing it removes it', () => {
  const edited = state();
  const identifier = edited.add(box)[InstanceKey.IDENTIFIER];
  edited.describeInstance(identifier, 'The charging dock.\n\tThe robot backs into it.');
  assert.equal(edited.instance(identifier)[InstanceKey.DESCRIPTION], 'The charging dock.\n\tThe robot backs into it.');
  assert.equal(JSON.parse(edited.exportText())[DraftKey.INSTANCES][0][InstanceKey.DESCRIPTION], 'The charging dock.\n\tThe robot backs into it.');
  edited.describeInstance(identifier, '');
  assert.equal(InstanceKey.DESCRIPTION in edited.instance(identifier), false);
});

test('a description too long or with control characters is refused', () => {
  const edited = state();
  const identifier = edited.add(box)[InstanceKey.IDENTIFIER];
  const tooLong = 'x'.repeat(catalog[CatalogKey.LIMITS][LimitsKey.MAXIMUM_DESCRIPTION_LENGTH] + 1);
  for (const description of [tooLong, 'a bell \u0007']) {
    assert.throws(() => edited.describeInstance(identifier, description), InvalidDraft);
  }
  assert.equal(InstanceKey.DESCRIPTION in edited.instance(identifier), false);
});

test('every primitive shape is one metre across, z up, standing on its base', () => {
  for (const shape of Object.values(PrimitiveShape)) {
    const bounds = new THREE.Box3().setFromObject(primitiveObject(`${ReservedResourceRoot.PRIMITIVES}/${shape}`));
    assert.deepEqual(bounds.min.toArray().map((value) => +value.toFixed(3)), [-0.5, -0.5, 0], shape);
    assert.deepEqual(bounds.max.toArray().map((value) => +value.toFixed(3)), [0.5, 0.5, 1], shape);
  }
  assert.throws(() => primitiveObject(`${ReservedResourceRoot.PRIMITIVES}/torus`));
});
