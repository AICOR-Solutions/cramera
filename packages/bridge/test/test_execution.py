"""
How a plan's motions are executed: the execution each executor kind names, the world a
physical execution sets up, and the execution a generated demo's command chooses.
"""

from __future__ import annotations

import json

import pytest

from cramera.locations import DataLocations
from cramera_bridge.exceptions import ExecutionNotRunning
from cramera_bridge.execution import (
    EXECUTIONS,
    KinematicExecution,
    PhysicalExecution,
    PlanExecution,
)
from cramera_bridge.plans.command import PlanDemoCommand
from cramera_bridge.plans.demo import PlannedTaskDemo
from cramera_bridge.plans.world import PlannedGraspableFromAbove
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.plan_builder import DemoDocument, DemoOption, PlanDocument
from cramera_protocol.robot_profile import ExecutorKind
from cramera_protocol.viewer import EnvironmentVariable
from cramph.context import StatechartContext
from krrood_spatial_math.spatial_types import HomogeneousTransformationMatrix
from semantic_digital_twin.datastructures.definitions import StaticJointState
from semantic_digital_twin.robots.tracy import Tracy
from semantic_digital_twin.specifications.connections import (
    Connection6DoFSpecification,
)
from semantic_digital_twin.specifications.kinematic_structure_entities import (
    BodySpecification,
)
from semantic_digital_twin.specifications.robots import RobotSpecification
from semantic_digital_twin.datastructures.prefixed_name import PrefixedName
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.contact import ContactParameters
from semantic_digital_twin.world_description.geometry import Scale
from semantic_digital_twin.world_description.world_entity import Body

needs_tracy = pytest.mark.skipif(
    not Tracy.is_description_installed(),
    reason="iai_tracy_description is not installed",
)

PARKED_TRACY_PLAN = {
    "formatVersion": "1.3",
    "name": "tracy_parks",
    "task": "Park the arms",
    "selectedRobot": "robot_1",
    "robots": [
        {
            "id": "robot_1",
            "model": "tracy",
            "label": "Tracy",
            "pose": [0, 0, 0, 0, 0, 0, 1],
            "steps": [
                {"id": "step_1", "action": "park_arms", "values": {"arms": "both"}}
            ],
        }
    ],
}
"""
A plan in which Tracy parks its arms.
"""


@pytest.fixture
def locations(tmp_path, monkeypatch) -> DataLocations:
    """
    :return: Data locations below the test's directory, which demos read from the
        environment.
    """
    monkeypatch.setenv(EnvironmentVariable.DATA, str(tmp_path / "data"))
    return DataLocations(data=tmp_path / "data", shared_scenes=None)


@pytest.fixture
def tracy_with_a_block() -> World:
    """
    :return: A world of Tracy and a free block taken from above on its table.
    """
    world = World()
    with world.modify_world():
        world.add_kinematic_structure_entity(Body(name=PrefixedName("floor")))
    RobotSpecification(Tracy).spawn(world)
    block = BodySpecification.box(
        "block",
        Scale(0.05, 0.05, 0.05),
        connection_specification=Connection6DoFSpecification(),
    ).spawn(
        world,
        parent_T_self=HomogeneousTransformationMatrix.from_xyz_rpy(0.55, 0.15, 0.906),
    )
    with world.modify_world():
        world.add_semantic_annotation(PlannedGraspableFromAbove(root=block))
    return world


# %% executions


@pytest.mark.parametrize("kind", list(ExecutorKind))
def test_each_executor_kind_names_its_execution(kind):
    assert type(PlanExecution.of_kind(kind)) is EXECUTIONS[kind]


def test_a_task_is_executed_kinematically_unless_asked_otherwise():
    assert PlanExecution.of_kind(ExecutorKind.KINEMATIC) == KinematicExecution()


def test_a_physical_execution_gives_no_executor_before_its_physics_runs():
    with pytest.raises(ExecutionNotRunning):
        PhysicalExecution().executor(
            StatechartContext.with_extensions(World(), []), False, []
        )


@needs_tracy
def test_physics_starts_with_the_arms_parked_and_free_objects_held_by_friction(
    tracy_with_a_block,
):
    world = tracy_with_a_block
    PhysicalExecution().prepare(world)
    [tracy] = world.get_semantic_annotations_by_type(Tracy)
    for arm in tracy.all_arms:
        parked = arm.get_joint_state_by_type(StaticJointState.PARK)
        for connection, position in zip(parked.connections, parked.target_values):
            assert connection.position == pytest.approx(position)
    [block] = world.get_semantic_annotations_by_type(PlannedGraspableFromAbove)
    [geometry] = block.root.collision
    contact = geometry.get_simulator_property_of_type(ContactParameters)
    assert contact == ContactParameters.create_for_grasped_object()


# %% the generated demo's command


@pytest.mark.parametrize(
    "arguments, execution_type",
    [
        ([], KinematicExecution),
        ([DemoOption.EXECUTOR, ExecutorKind.PHYSICS], PhysicalExecution),
    ],
)
def test_the_demo_command_executes_as_it_is_told(
    monkeypatch, arguments, execution_type
):
    chosen = []
    monkeypatch.setattr(PlannedTaskDemo, "run", lambda demo: chosen.append(demo))
    PlanDemoCommand(DemoDocument(plan=PlanDocument.from_json(PARKED_TRACY_PLAN))).main(
        [DemoOption.PORT, "0", *arguments]
    )
    assert type(chosen[0].execution) is execution_type


@needs_tracy
def test_a_plan_is_performed_in_physics_and_its_recording_saved(locations):
    command = PlanDemoCommand.of_text(json.dumps({"plan": PARKED_TRACY_PLAN}))
    saved = command.main([DemoOption.PORT, "0", DemoOption.EXECUTOR, "physics"])
    assert (locations.local_scenes / saved.scene / BundleFile.SCENE).is_file()
