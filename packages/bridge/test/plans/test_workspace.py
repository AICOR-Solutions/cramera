"""
The installed CRAM workspace as the catalog reads it.
"""

from __future__ import annotations

import pytest

from cramera_bridge.plans.arms import Arms
from cramera_bridge.plans.workspace import (
    PlanWorkspace,
    RobotAnnotation,
    RobotAnnotations,
    SurfaceAnnotations,
)
from cramera_bridge.exceptions import UnknownWorkspaceClass
from cramera_bridge.names import ROBOT_NAMES
from cramera_protocol.bundle.files import MeshFormat
from semantic_digital_twin.datastructures.definitions import TorsoState
from semantic_digital_twin.robots.minimal_robot import MinimalRobot
from semantic_digital_twin.robots.pr2 import PR2
from semantic_digital_twin.robots.stretch import Stretch
from semantic_digital_twin.robots.tracy import Tracy
from semantic_digital_twin.semantic_annotations.mixins import HasCaseAsRootBody
from semantic_digital_twin.semantic_annotations.semantic_annotations import Table


@pytest.fixture(scope="module")
def workspace() -> PlanWorkspace:
    """
    :return: The workspace this interpreter imports.
    """
    return PlanWorkspace()


def test_a_robot_with_two_arms_and_a_torso_offers_every_choice():
    assert RobotAnnotation(PR2).choices() == {
        Arms.__name__: [arm.name for arm in Arms],
        TorsoState.__name__: [state.name for state in TorsoState],
    }


def test_a_robot_without_a_torso_offers_no_torso_state():
    assert RobotAnnotation(Tracy).choices()[TorsoState.__name__] == []


def test_a_robot_with_one_arm_offers_the_choice_coraplex_resolves_to_it():
    assert RobotAnnotation(Stretch).arms() == [Arms.BOTH.name]


def test_robots_without_a_model_description_are_not_offered():
    names = [annotation.__name__ for annotation in RobotAnnotations().annotations()]
    assert PR2.__name__ in names
    assert MinimalRobot.__name__ not in names
    assert names == sorted(names)


def test_the_catalog_robots_are_the_offered_annotations(workspace):
    assert [robot.name for robot in workspace.robots()] == [
        ROBOT_NAMES.identifier_of(annotation)
        for annotation in RobotAnnotations().annotations()
    ]
    assert [robot.label for robot in workspace.robots()] == [
        annotation.__name__ for annotation in RobotAnnotations().annotations()
    ]


def test_the_object_models_are_the_meshes_beside_coraplex(workspace):
    identifiers = [model.identifier for model in workspace.objects()]
    assert "milk.stl" in identifiers
    assert not any(
        identifier.endswith(MeshFormat.MATERIAL_LIBRARY) for identifier in identifiers
    )
    assert (workspace.object_directory() / "milk.stl").is_file()


def test_the_catalog_robots_name_their_choices(workspace):
    pr2 = next(
        robot
        for robot in workspace.robots()
        if robot.name == ROBOT_NAMES.identifier_of(PR2)
    )
    assert pr2.choices == RobotAnnotation(PR2).choices()


def test_the_catalog_lists_the_discovered_actions(workspace):
    assert workspace.action_catalog() == workspace.discovered_actions.catalog()


def test_the_surfaces_are_concrete_annotations_without_the_mixins(workspace):
    surfaces = workspace.surface_types()
    assert Table.__name__ in surfaces
    assert HasCaseAsRootBody.__name__ not in surfaces
    assert SurfaceAnnotations().named(Table.__name__) is Table


def test_an_unknown_class_name_is_refused():
    with pytest.raises(UnknownWorkspaceClass):
        RobotAnnotations().named("R2D2")
