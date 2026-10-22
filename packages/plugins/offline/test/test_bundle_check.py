"""
Following every reference of a bundle and reporting those that cannot be followed.
"""

from __future__ import annotations

import os

import pytest

from cramera_offline.bundle_check import BundleCheck
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.offline import AssetProblem, AssetProblemKind

# %% complete bundles


def test_a_complete_bundle_has_no_problems_and_lists_every_file(complete_bundle):
    report = BundleCheck(complete_bundle).report()
    on_disk = sorted(
        os.path.relpath(os.path.join(directory, name), complete_bundle)
        for directory, _, names in os.walk(complete_bundle)
        for name in names
    )
    assert report.is_complete()
    assert report.bundle == complete_bundle.name
    assert report.checked_files == on_disk


def test_a_check_can_be_repeated(complete_bundle):
    check = BundleCheck(complete_bundle)
    assert check.report() == check.report()


# %% problems


@pytest.mark.parametrize(
    "kind, source, reference",
    [
        (AssetProblemKind.DECLARED_MISSING, BundleFile.SCENE, "meshes/lost.stl"),
        (AssetProblemKind.EXTERNAL, BundleFile.SCENE, "https://example.com/cup.stl"),
        (AssetProblemKind.EXTERNAL, BundleFile.SCENE, "C:\\meshes\\cup.stl"),
        (AssetProblemKind.EXTERNAL, "robot.urdf", "package://robot/meshes/base.stl"),
        (AssetProblemKind.EXTERNAL, "robot.urdf", "/opt/robot/meshes/shoulder.stl"),
        (AssetProblemKind.OUTSIDE_BUNDLE, "robot.urdf", "../outside.stl"),
        (AssetProblemKind.MISSING, "robot.urdf", "meshes/missing.dae"),
        (AssetProblemKind.INVALID_REFERENCE, "robot.urdf", ""),
        (
            AssetProblemKind.EXTERNAL,
            "meshes/materials/external_texture.mtl",
            "https://example.com/paint.png",
        ),
        (AssetProblemKind.INVALID_REFERENCE, "meshes/empty_library.obj", "mtllib"),
    ],
)
def test_a_reference_that_cannot_be_followed_is_reported(
    broken_bundle, kind, source, reference
):
    problems = BundleCheck(broken_bundle).report().problems
    assert AssetProblem(kind=kind, source=source, reference=reference) in problems


@pytest.mark.parametrize(
    "source", ["broken.urdf", "meshes/invalid_header.glb", "meshes/not_json.gltf"]
)
def test_a_damaged_file_is_reported_with_the_reason(broken_bundle, source):
    problems = BundleCheck(broken_bundle).report().problems
    unreadable = [problem for problem in problems if problem.source == source]
    assert [problem.kind for problem in unreadable] == [AssetProblemKind.UNREADABLE]
    assert unreadable[0].detail


def test_a_symbolic_link_out_of_the_bundle_is_reported(complete_bundle, tmp_path):
    outside = tmp_path / "outside.svg"
    outside.write_text("<svg/>", encoding="utf-8")
    texture = complete_bundle / "textures" / "paint coat.svg"
    texture.unlink()
    texture.symlink_to(outside)
    problems = BundleCheck(complete_bundle).report().problems
    assert {problem.kind for problem in problems} == {AssetProblemKind.OUTSIDE_BUNDLE}


def test_embedded_content_is_only_accepted_from_gltf_files(complete_bundle):
    urdf = complete_bundle / "robot.urdf"
    urdf.write_text(
        urdf.read_text(encoding="utf-8").replace(
            "meshes/part.dae", "data:model/stl;base64,AAAA"
        ),
        encoding="utf-8",
    )
    problems = BundleCheck(complete_bundle).report().problems
    assert [problem.kind for problem in problems] == [AssetProblemKind.EXTERNAL]


# %% scene description


def test_a_bundle_without_a_scene_description_is_reported(tmp_path):
    report = BundleCheck(tmp_path).report()
    assert report.problems == [
        AssetProblem(
            kind=AssetProblemKind.MISSING,
            source=BundleFile.SCENE.value,
            reference=BundleFile.SCENE.value,
        )
    ]
    assert report.checked_files == []


@pytest.mark.parametrize("bundle", ["unreadable_scene", "invalid_scene"])
def test_an_unusable_scene_description_is_reported(recorded_scenes, bundle):
    report = BundleCheck(recorded_scenes / bundle).report()
    assert [problem.kind for problem in report.problems] == [
        AssetProblemKind.UNREADABLE
    ]
    assert report.checked_files == []
