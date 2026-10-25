"""
The laboratory page starts with the real PR2 in its demo's initial pose.
"""

from xml.etree import ElementTree

import pytest

from cramera_bridge.documents import DocumentFile
from cramera_bridge.exceptions import SceneNameTaken
from cramera_bridge.laboratory.command import prepare_preview
from cramera_bridge.laboratory.preview import PREVIEW_NAME
from cramera_bridge.laboratory.transfer import ROBOT_START, VesselTransferDemo
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.bundle.trajectory import Trajectory


@pytest.fixture(scope="module")
def preview(laboratory_bundle, tmp_path_factory):
    directory = tmp_path_factory.mktemp("laboratory-preview")
    saved = prepare_preview(str(laboratory_bundle), str(directory))
    return directory / saved.scene


def test_preview_adds_real_robot_without_replacing_the_authored_lab(
    preview, laboratory_bundle
):
    scene = DocumentFile(preview / BundleFile.SCENE).read(SceneDescription)
    authored = DocumentFile(laboratory_bundle / BundleFile.SCENE).read(SceneDescription)
    assert scene.extensions == authored.extensions
    assert scene.objects == authored.objects
    assert [model for model in scene.models if not model.robot] == authored.models
    robot = next(model for model in scene.models if model.robot)
    assert scene.robot is not None
    assert scene.robot.label == "PR2"
    assert robot.pose.x == pytest.approx(ROBOT_START[0])
    assert robot.pose.y == pytest.approx(ROBOT_START[1])
    assert robot.links > 50
    assert not scene.missing_assets
    urdf = ElementTree.parse(preview / robot.urdf)
    meshes = urdf.findall(".//mesh")
    assert len(meshes) > 20
    assert all((preview / mesh.attrib["filename"]).is_file() for mesh in meshes)
    for notice in ("LICENSE.txt", "NOTICE.md", "rights.json"):
        assert (preview / notice).read_bytes() == (
            laboratory_bundle / notice
        ).read_bytes()
    manifests = list((preview / "asset-sources").glob("*/package.xml"))
    assert manifests
    assert any(ElementTree.parse(path).findtext("license") for path in manifests)


def test_preview_has_the_parked_arms_and_raised_torso(preview):
    trajectory = DocumentFile(preview / BundleFile.TRAJECTORY).read(Trajectory)
    assert trajectory.frame_count() == 1
    joints = trajectory.frames[0]
    torso = next(
        value for name, value in joints.items() if name.endswith("torso_lift_joint")
    )
    assert torso > 0.25
    assert any(
        abs(value) > 0.5
        for name, value in joints.items()
        if name.endswith("elbow_flex_joint")
    )


def test_a_cached_preview_does_not_rebuild_a_native_world(
    preview, laboratory_bundle, monkeypatch
):
    def unexpected_build(*args, **kwargs):
        raise AssertionError("A complete unchanged preview must be reused")

    monkeypatch.setattr(VesselTransferDemo, "at_the_bench", unexpected_build)
    saved = prepare_preview(str(laboratory_bundle), str(preview.parent))
    assert saved.scene == preview.name


def test_an_existing_user_scene_is_never_replaced_by_a_preview(
    laboratory_bundle, tmp_path, monkeypatch
):
    target = tmp_path / PREVIEW_NAME
    target.mkdir()
    original = target / BundleFile.SCENE
    original.write_text("user recording", encoding="utf-8")

    def unexpected_build(*args, **kwargs):
        raise AssertionError("An occupied name must be refused before building a world")

    monkeypatch.setattr(VesselTransferDemo, "at_the_bench", unexpected_build)
    with pytest.raises(SceneNameTaken):
        prepare_preview(str(laboratory_bundle), str(tmp_path))
    assert original.read_text(encoding="utf-8") == "user recording"
