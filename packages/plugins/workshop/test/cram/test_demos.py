"""
The workshop's PR2 demos: their recordings' names, their context, their plans and
measurements, and the rights a saved recording carries.

Running a demo's plan is not tested here: a run takes minutes. ``cramera-workshop
insertion`` and ``assembly`` perform them.
"""

from __future__ import annotations

import json

import pytest

from cramera_cram.exceptions import TaskFailed
from cramera_protocol.bundle.acceptance import AcceptanceMetrics
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.workshop import AssetRights
from cramera_workshop.acceptance import (
    AssemblyStage,
    ContentsMeasurement,
    DemoMeasurement,
    Requirement,
)
from cramera_workshop.bundle import WorkshopFile
from cramera_workshop.robot.contents import ContentsMeasurements
from cramera_workshop.robot.demos import (
    ContentsDocument,
    ExecutionObservation,
    WorkshopDemoName,
)
from cramera_workshop.robot.gaze import AnchoredToolCenterPointMotion
from cramera_workshop.robot.transport import (
    MoveHeldObjectAction,
    RetrieveScrewBoxAction,
)
from semantic_digital_twin.datastructures.definitions import StaticJointState

# %% names and context


def test_the_recording_is_named_after_bundle_robot_and_task(assembly_demo, bundle):
    assert assembly_demo.scene_name() == "_".join(
        (bundle.scene.name, WorkshopDemoName.ROBOT, WorkshopDemoName.ASSEMBLY)
    )
    assert assembly_demo.environment_name == bundle.scene.environment_name
    assert assembly_demo.presentation is not None


def test_the_context_follows_the_tool_with_the_head(assembly_context):
    assert assembly_context.alternative_motion_mappings == [
        AnchoredToolCenterPointMotion
    ]


def test_the_arms_start_parked(assembly_context):
    robot = assembly_context.robot
    park = robot.left_arm.get_joint_state_by_type(StaticJointState.PARK)
    for connection, position in park.items():
        assert float(connection.position) == pytest.approx(position)


# %% plans


def test_the_assembly_has_every_stage(assembly_demo, assembly_context):
    actions = assembly_demo.plan_actions(assembly_context)
    assert len(actions) == len(AssemblyStage)
    assert isinstance(actions[0], RetrieveScrewBoxAction)


def test_the_insertion_ends_with_the_screw_at_the_pilot_hole(insertion_demo):
    context = insertion_demo.build_context(insertion_demo.build_world())
    plan = insertion_demo.build_plan(context)
    actions = insertion_demo.actions
    assert isinstance(actions[-1], MoveHeldObjectAction)
    assert actions[-1].keep_shaft_roll
    assert insertion_demo.contents.active
    assert insertion_demo.contents in plan.node_callbacks
    assert insertion_demo.observation in plan.node_callbacks
    with pytest.raises(TaskFailed) as failed:
        insertion_demo.measure(context)
    assert Requirement.ACTIONS_SUCCEEDED.value in failed.value.reason


# %% measurements


def test_the_contents_are_written_by_measurement_name():
    measurements = ContentsMeasurements(escaped_contents=("screw_3",))
    written = ContentsDocument(measurements).json()
    assert set(written) == {name.value for name in ContentsMeasurement}
    assert written[ContentsMeasurement.ESCAPED_CONTENTS] == ["screw_3"]
    assert json.loads(json.dumps(written)) == written


def test_the_observation_counts_ticks_and_keeps_the_smallest_distance(
    assembly_context,
):
    assembly_context.world.collision_manager.update_collision_matrix()
    observation = ExecutionObservation(context=assembly_context)
    observation.on_motion_tick(None)
    first = observation.minimum_distance
    observation.on_motion_tick(None)
    assert observation.ticks == 2
    assert observation.minimum_distance == first


def test_a_demo_that_missed_requirements_names_them(assembly_demo):
    with pytest.raises(TaskFailed) as failed:
        assembly_demo.require(
            {},
            {Requirement.BOX_ON_BENCH: False, Requirement.NO_PENETRATION: True},
        )
    assert failed.value.reason == Requirement.BOX_ON_BENCH.value
    metrics = assembly_demo.require({DemoMeasurement.CONTROL_TICKS: 3}, {})
    assert metrics.measurements == {DemoMeasurement.CONTROL_TICKS: 3}


# %% saving


def test_a_saved_recording_carries_the_rights_and_notices(
    assembly_demo, bundle, tmp_path
):
    saved = tmp_path / assembly_demo.scene_name()
    saved.mkdir()
    scene = SceneDescription(name=saved.name)
    (saved / BundleFile.SCENE).write_text(json.dumps(scene.to_json()), encoding="utf-8")
    metrics = AcceptanceMetrics(measurements={DemoMeasurement.CONTROL_TICKS: 1})
    assembly_demo.complete(saved, metrics)
    written = SceneDescription.from_json(
        json.loads((saved / BundleFile.SCENE).read_text(encoding="utf-8"))
    )
    assert AssetRights.of_scene(written.extensions) == bundle.asset_rights
    rights = bundle.asset_rights
    for name in (rights.license_file, rights.notice_file, WorkshopFile.RIGHTS):
        assert (saved / name).read_bytes() == bundle.file(name).read_bytes()
    assert (
        AcceptanceMetrics.from_json(
            json.loads((saved / BundleFile.ACCEPTANCE_METRICS).read_text())
        )
        == metrics
    )
