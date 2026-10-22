"""
The generated demo against the CRAM workspace: importing it, building the plan's world
and native actions, performing it, and staging its world for the viewer.
"""

from __future__ import annotations

import importlib.util
import json
import math
import signal
import socket
import sys
import time
from pathlib import Path

import pytest

from coraplex.datastructures.enums import Arms
from coraplex.robot_plans.actions.composite.transporting import TransportAction
from coraplex.robot_plans.actions.core.navigation import NavigateAction
from coraplex.robot_plans.actions.core.pick_up import PickUpAction
from coraplex.robot_plans.actions.core.placing import PlaceAction
from coraplex.robot_plans.actions.core.robot_body import (
    MoveTorsoAction,
    ParkArmsAction,
)
from cramera.locations import DataLocations
from cramera_cram.documents import DocumentFile
from cramera_cram.exceptions import TaskFailed
from cramera_cram.geometry import NumericPose
from cramera_plan_builder.cram.command import STOP_SIGNALS, PlanDemoCommand, StagedWorld
from cramera_plan_builder.cram.demo import (
    MEASUREMENT_SEPARATOR,
    PLACEMENT_ERROR,
    PLACEMENT_TOLERANCE,
    PlannedTaskDemo,
)
from cramera_plan_builder.cram.steps import StepActions
from cramera_plan_builder.cram.surfaces import SurfaceTargets
from cramera_plan_builder.demos import DemoDirectory, DemoOption, DemoTemplate
from cramera_plan_builder.exceptions import SurfaceNotInWorld
from cramera_plan_builder.runs import DemoRunner
from cramera_protocol.bundle.acceptance import AcceptanceMetrics
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.live import LIVE_HOST, LiveRoute
from cramera_protocol.plan_builder import (
    DemoDocument,
    PlanDocument,
    RunMode,
    RunState,
    StepConstraint,
    StepKind,
    StepSwitch,
)
from cramera_protocol.viewer import EnvironmentVariable
from semantic_digital_twin.api import BodySpecification
from semantic_digital_twin.robots.pr2 import PR2
from semantic_digital_twin.semantic_annotations.semantic_annotations import Table
from semantic_digital_twin.spatial_types import HomogeneousTransformationMatrix
from semantic_digital_twin.world_description.geometry import Scale

from ..dataset.given_workspace import DATASET
from ..dataset.live_reader import ObjectCatalogReader

PLAN_FILE = DATASET / "plans" / "pick_and_place.json"
"""
The plan the tests run: one PR2 picks the milk up and puts it down, another stands.
"""

TABLE_SIZE = Scale(1.0, 0.6, 0.75)
"""
The extent of the table the surface tests put the milk on, in metres.
"""

TABLE_POSITION = (2.0, 0.0)
"""
Where the table stands on the floor, in metres.
"""

STAGE_WAIT = 300.0
"""
How long the staging test waits for the staged world, in seconds.
"""

STAGE_POLL_INTERVAL = 0.5
"""
How often the staging test asks the staged world, in seconds.
"""


@pytest.fixture
def document() -> DemoDocument:
    """
    :return: The test plan on an empty floor.
    """
    return DemoDocument(
        plan=PlanDocument.from_json(json.loads(PLAN_FILE.read_text("utf-8")))
    )


@pytest.fixture
def locations(tmp_path, monkeypatch) -> DataLocations:
    """
    :return: Data locations below the test's directory, which demos read from the
        environment.
    """
    monkeypatch.setenv(EnvironmentVariable.DATA, str(tmp_path / "data"))
    return DataLocations(data=tmp_path / "data", shared_scenes=None)


@pytest.fixture
def demo(document, locations) -> PlannedTaskDemo:
    """
    :return: The test plan's demo.
    """
    return PlannedTaskDemo.of_document(document, port=0)


@pytest.fixture
def built(demo):
    """
    :return: The test plan's world and the context of its performing robot.
    """
    world = demo.build_world()
    return world, demo.build_context(world)


def free_port() -> int:
    """
    :return: A port no process listens on right now.
    """
    with socket.socket() as probe:
        probe.bind((LIVE_HOST, 0))
        return probe.getsockname()[1]


# %% the generated file


def test_the_generated_demo_imports_and_carries_its_plan(tmp_path, document):
    saved = DemoDirectory(tmp_path).write(DemoTemplate().render(document))
    specification = importlib.util.spec_from_file_location(
        document.plan.name, saved.path
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    assert module.PlanDemoCommand is PlanDemoCommand
    assert PlanDemoCommand.of_text(module.DEMO).document == document


# %% world and actions


def test_every_robot_stands_under_its_namespace(document, built):
    world, context = built
    robots = world.get_semantic_annotations_by_type(PR2)
    assert sorted(robot.root.name.prefix for robot in robots) == [
        robot.identifier for robot in document.plan.robots
    ]
    assert context.robot.root.name.prefix == document.plan.selected_robot


def test_the_objects_start_where_the_plan_puts_them(document, demo, built):
    world, _ = built
    milk = document.plan.objects[0]
    position = NumericPose.of_entity(world, demo.bodies[milk.identifier]).position
    assert position == pytest.approx(milk.pose.to_json()[:3])


def test_the_steps_become_their_native_actions(demo, built):
    _, context = built
    actions = StepActions(context, demo.bodies)
    assert [type(actions.action(step)) for step in demo.steps()] == [
        ParkArmsAction,
        MoveTorsoAction,
        PickUpAction,
        PlaceAction,
    ]
    assert actions.action(demo.steps()[0]).arm is Arms[demo.steps()[0].arm]


def test_a_transports_constraint_switch_reaches_the_action(document, demo, built):
    _, context = built
    transport = document.plan.robots[1].steps[0]
    assert transport.kind is StepKind.TRANSPORT
    transport.constraints = [
        StepConstraint(text="Look", switch=StepSwitch.LOOK_AT_OPERATION_SITE)
    ]
    action = StepActions(context, demo.bodies).action(transport)
    assert isinstance(action, TransportAction)
    assert action.look_at_operation_site is True
    assert isinstance(action.target_location, SurfaceTargets)


def test_a_navigation_drives_to_its_target(document, demo, built):
    world, context = built
    navigate = document.plan.robots[1].steps[1]
    action = StepActions(context, demo.bodies).action(navigate)
    assert isinstance(action, NavigateAction)
    assert action.target_location.to_position().to_np()[:3] == pytest.approx(
        navigate.target.to_json()[:3]
    )


def test_a_surface_the_world_lacks_offers_no_spot(demo, built):
    world, _ = built
    targets = SurfaceTargets(
        world=world, body=demo.bodies["milk"], surface_type="Table"
    )
    with pytest.raises(SurfaceNotInWorld):
        targets.first()


def test_a_spot_on_a_surface_rests_the_object_on_it(demo, built):
    world, _ = built
    table = BodySpecification.box("table", TABLE_SIZE).spawn(
        world,
        parent_T_self=HomogeneousTransformationMatrix.from_xyz_rpy(
            *TABLE_POSITION, TABLE_SIZE.z / 2
        ),
    )
    with world.modify_world():
        world.add_semantic_annotation(Table(root=table))
    targets = SurfaceTargets(
        world=world, body=demo.bodies["milk"], surface_type="Table"
    )
    position = targets.first().to_position().to_np()
    assert position[2] > TABLE_SIZE.z + targets.bottom_offset() - PLACEMENT_TOLERANCE
    assert abs(position[0] - TABLE_POSITION[0]) <= TABLE_SIZE.x / 2


# %% naming and measuring


def test_a_plan_on_an_empty_floor_is_recorded_under_its_name(document, demo):
    assert demo.scene_name() == document.plan.name


def test_a_taken_name_gets_the_next_number(demo, locations):
    (locations.local_scenes / demo.name).mkdir(parents=True)
    assert demo.scene_name() == f"{demo.name}_2"


def test_an_environment_bundle_names_the_recording(document, locations):
    document.environment_directory = str(DATASET / "scenes" / "lab")
    demo = PlannedTaskDemo.of_document(document, port=0)
    assert demo.scene_name() == "lab_PR2_pr2_pick_and_place"
    assert demo.environment_name == "Test laboratory"


def test_an_object_far_from_its_pose_fails_the_task(demo, built):
    world, context = built
    milk = demo.bodies["milk"]
    milk.parent_connection.origin = HomogeneousTransformationMatrix.from_xyz_rpy(
        5.0, 5.0, 0.0, reference_frame=world.root
    )
    with pytest.raises(TaskFailed):
        demo.measure(context)


# %% running


def test_the_plan_is_performed_and_its_recording_saved(document, locations):
    saved = PlanDemoCommand(document).main([DemoOption.PORT, "0"])
    bundle = locations.local_scenes / saved.scene
    metrics = DocumentFile(bundle / BundleFile.ACCEPTANCE_METRICS).read(
        AcceptanceMetrics
    )
    error = metrics.measurements[
        MEASUREMENT_SEPARATOR.join((PLACEMENT_ERROR, "step_4"))
    ]
    assert saved.scene == document.plan.name
    assert (bundle / BundleFile.SCENE).is_file()
    assert math.isfinite(error) and error <= PLACEMENT_TOLERANCE


def test_a_stopped_stage_restores_the_signal_handlers(demo):
    handlers = {number: signal.getsignal(number) for number in STOP_SIGNALS}
    staged = StagedWorld(demo)
    staged.stopped.set()
    staged.run()
    assert {number: signal.getsignal(number) for number in STOP_SIGNALS} == handlers


def test_a_staged_demo_publishes_its_world_until_it_is_stopped(
    tmp_path, document, locations
):
    port = free_port()
    runner = DemoRunner(
        directory=DemoDirectory(tmp_path / "demos", interpreter=sys.executable),
        port=port,
        log_limit=64 * 1024,
    )
    runner.start(document, RunMode.STAGE)
    objects_url = f"http://{LIVE_HOST}:{port}{LiveRoute.OBJECTS}"
    deadline = time.monotonic() + STAGE_WAIT
    catalog = None
    while catalog is None and time.monotonic() < deadline:
        assert runner.status().state is RunState.RUNNING, runner.status().log
        catalog = ObjectCatalogReader(objects_url).read()
        time.sleep(STAGE_POLL_INTERVAL)
    stopped = runner.stop()
    assert [item.identifier for item in catalog.objects] == ["milk"]
    assert stopped.state is RunState.STOPPED
