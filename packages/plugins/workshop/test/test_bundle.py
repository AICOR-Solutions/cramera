"""
The workshop bundle: the packaged AICOR workshop, the one the viewer shows, its files
and its asset rights.
"""

from __future__ import annotations

import json
import shutil

import pytest

from cramera.exceptions import PathOutsideDirectory
from cramera.scenes import SceneCatalog, SceneDirectory, SceneSource
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.workshop import WorkshopSceneKey
from cramera_workshop.bundle import (
    RESOURCES,
    WorkshopBundle,
    WorkshopBundleName,
    WorkshopFile,
)
from cramera_workshop.exceptions import NotAWorkshopBundle

# %% packaged bundle


def test_the_packaged_bundle_describes_the_aicor_workshop(bundle):
    assert bundle.scene.name == WorkshopBundleName.AICOR_WORKSHOP
    assert bundle.directory == RESOURCES / WorkshopBundleName.AICOR_WORKSHOP


def test_the_licence_and_notice_the_rights_name_are_in_the_bundle(bundle):
    rights = bundle.asset_rights
    rights_file = json.loads(
        bundle.file(WorkshopFile.RIGHTS).read_text(encoding="utf-8")
    )
    assert rights.to_json() == rights_file
    assert bundle.file(rights.license_file).is_file()
    assert bundle.file(rights.notice_file).is_file()


def test_every_movable_body_has_a_urdf_in_the_bundle(bundle):
    movable = bundle.movable_objects()
    assert sorted(item.key for item in movable) == sorted(
        bundle.workshop.movable_keys()
    )
    assert all(bundle.file(item.urdf).is_file() for item in movable)


def test_the_semantics_name_a_handle_for_every_drawer(bundle):
    handles = bundle.semantics().handles
    assert all(drawer.handle in handles for drawer in bundle.workshop.drawers)


def test_a_file_outside_the_bundle_is_refused(bundle):
    with pytest.raises(PathOutsideDirectory):
        bundle.file("../aicor_workshop/../../plugin.py")


# %% shown bundle


def test_without_a_shown_workshop_the_packaged_one_is_used():
    assert WorkshopBundle.shown_or_packaged(SceneCatalog([])) == (
        WorkshopBundle.packaged()
    )


def test_the_workshop_the_viewer_shows_is_used(tmp_path, bundle):
    copied = tmp_path / bundle.directory.name
    shutil.copytree(bundle.directory, copied)
    catalog = SceneCatalog([SceneDirectory(tmp_path, SceneSource.SHARED)])
    assert WorkshopBundle.shown_or_packaged(catalog).directory == copied


def test_a_scene_without_a_workshop_is_refused(tmp_path, bundle):
    scene = json.loads((bundle.directory / BundleFile.SCENE).read_text())
    scene = {
        key: value for key, value in scene.items() if key != WorkshopSceneKey.WORKSHOP
    }
    (tmp_path / BundleFile.SCENE).write_text(json.dumps(scene), encoding="utf-8")
    with pytest.raises(NotAWorkshopBundle):
        WorkshopBundle.read(tmp_path)
