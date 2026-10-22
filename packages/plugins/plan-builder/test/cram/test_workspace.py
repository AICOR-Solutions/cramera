"""
The installed CRAM workspace as the catalog reads it.
"""

from __future__ import annotations

import pytest

from coraplex.datastructures.enums import Arms
from cramera_plan_builder.cram.workspace import (
    InstalledWorkspace,
    RobotAnnotation,
    RobotAnnotations,
    SurfaceAnnotations,
)
from cramera_plan_builder.exceptions import UnknownWorkspaceClass
from cramera_plan_builder.workspace import WorkspaceLoader
from cramera_protocol.bundle.files import MeshFormat
from cramera_protocol.plan_builder import StepKind
from semantic_digital_twin.datastructures.definitions import TorsoState
from semantic_digital_twin.robots.minimal_robot import MinimalRobot
from semantic_digital_twin.robots.pr2 import PR2
from semantic_digital_twin.robots.stretch import Stretch
from semantic_digital_twin.robots.tiago import TiagoMujoco
from semantic_digital_twin.robots.tracy import Tracy
from semantic_digital_twin.semantic_annotations.mixins import HasCaseAsRootBody
from semantic_digital_twin.semantic_annotations.semantic_annotations import Table


@pytest.fixture(scope="module")
def workspace() -> InstalledWorkspace:
    """
    :return: The workspace this interpreter imports.
    """
    return InstalledWorkspace()


def test_the_loader_reads_the_installed_workspace():
    assert isinstance(WorkspaceLoader().workspace(), InstalledWorkspace)


def test_a_mobile_robot_with_two_arms_and_a_torso_takes_every_step():
    pr2 = RobotAnnotation(PR2)
    assert pr2.steps() == list(StepKind)
    assert pr2.arms() == [arm.name for arm in Arms]


def test_a_robot_without_a_mobile_base_neither_drives_nor_transports():
    steps = RobotAnnotation(Tracy).steps()
    assert StepKind.NAVIGATE not in steps and StepKind.TRANSPORT not in steps
    assert StepKind.PICK_UP in steps


def test_a_robot_with_one_arm_offers_the_choice_coraplex_resolves_to_it():
    assert RobotAnnotation(Stretch).arms() == [Arms.BOTH.name]


def test_robots_without_a_model_description_are_not_offered():
    names = [annotation.__name__ for annotation in RobotAnnotations().annotations()]
    assert PR2.__name__ in names
    assert MinimalRobot.__name__ not in names
    assert TiagoMujoco.__name__ not in names
    assert names == sorted(names)


def test_the_catalog_robots_are_the_offered_annotations(workspace):
    assert [robot.name for robot in workspace.robots()] == [
        annotation.__name__ for annotation in RobotAnnotations().annotations()
    ]


def test_the_object_models_are_the_meshes_beside_coraplex(workspace):
    identifiers = [model.identifier for model in workspace.objects()]
    assert "milk.stl" in identifiers
    assert not any(
        identifier.endswith(MeshFormat.MATERIAL_LIBRARY) for identifier in identifiers
    )
    assert (
        workspace.object_file("milk.stl")
        == (workspace.object_directory() / "milk.stl").resolve()
    )


def test_the_torso_states_are_the_native_ones(workspace):
    assert workspace.torso_states() == [state.name for state in TorsoState]


def test_the_surfaces_are_concrete_annotations_without_the_mixins(workspace):
    surfaces = workspace.surface_types()
    assert Table.__name__ in surfaces
    assert HasCaseAsRootBody.__name__ not in surfaces
    assert SurfaceAnnotations().named(Table.__name__) is Table


def test_an_unknown_class_name_is_refused():
    with pytest.raises(UnknownWorkspaceClass):
        RobotAnnotations().named("R2D2")
