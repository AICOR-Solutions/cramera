"""
GARMI carrying a bowl and a spoon across the apartment, run once with its queries
stepped, recorded and measured; skipped where the apartment's ROS package is not built.
"""

from __future__ import annotations

import pytest

from cramera.locations import DataLocations
from cramera_bridge.demos.garmi_apartment import (
    APARTMENT_PACKAGE,
    PLACE_TOLERANCE,
    TASK,
    GarmiApartmentEnvironment,
    SceneBody,
    ScenePose,
    demo,
)
from cramera_bridge.documents import DocumentFile
from cramera_bridge.exceptions import TaskFailed
from cramera_protocol.bundle.acceptance import AcceptanceMetrics
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.query_steps import QuerySteps, StepPhase
from coraplex.robot_plans.actions.composite.transporting import TransportAction
from semantic_digital_twin.semantic_annotations.semantic_annotations import (
    Bowl,
    Drawer,
    Spoon,
)
from semantic_digital_twin.world import World

packages = pytest.importorskip("ament_index_python.packages")

if APARTMENT_PACKAGE not in packages.get_packages_with_prefixes():
    pytest.skip(f"{APARTMENT_PACKAGE} is not built", allow_module_level=True)

POSITION_TOLERANCE = 1e-6
"""
How far, in metres, an object may stand from where the scene puts it.
"""

# %% fixtures


@pytest.fixture(scope="module")
def garmi_run(tmp_path_factory):
    """
    :return: The demo after one run stepping through its queries without holding, and
        the bundle it saved.
    """
    data = tmp_path_factory.mktemp("garmi")
    task = demo()
    task.locations = DataLocations(data=data, shared_scenes=None)
    task.port = 0
    task.step_queries = True
    task.holds_at_queries = False
    saved = task.run()
    return task, task.locations.local_scenes / saved.scene


@pytest.fixture(scope="module")
def apartment() -> World:
    """
    :return: The apartment with the bowl and the spoon, and no robot.
    """
    return GarmiApartmentEnvironment().create_world()


# %% the scene


def test_the_bowl_stands_on_the_counter_and_the_spoon_lies_in_its_drawer(apartment):
    bowl = apartment.get_body_by_name(SceneBody.BOWL)
    spoon = apartment.get_body_by_name(SceneBody.SPOON)
    start = ScenePose.BOWL_START.value
    position = bowl.global_pose.to_np()[:3, 3]
    assert list(position) == pytest.approx(
        [start.x, start.y, start.z], abs=POSITION_TOLERANCE
    )
    assert spoon.parent_connection.parent.name.name == SceneBody.SPOON_DRAWER
    assert apartment.get_semantic_annotations_by_type(Bowl)
    assert apartment.get_semantic_annotations_by_type(Spoon)


def test_the_furniture_is_annotated(apartment):
    assert apartment.get_semantic_annotations_by_type(Drawer)


def test_the_apartment_can_be_added_to_another_world():
    world = World.create_with_root_body()
    GarmiApartmentEnvironment().populate(world)
    assert world.get_body_by_name(SceneBody.SPOON_DRAWER) is not None
    assert world.get_semantic_annotations_by_type(Bowl)


def test_objects_far_from_the_table_fail_the_task():
    task = demo()
    world = task.build_world()
    with pytest.raises(TaskFailed):
        task.measure(task.build_context(world))


# %% the run


def test_both_objects_end_on_the_table(garmi_run):
    _, bundle = garmi_run
    metrics = DocumentFile(bundle / BundleFile.ACCEPTANCE_METRICS).read(
        AcceptanceMetrics
    )
    scene = DocumentFile(bundle / BundleFile.SCENE).read(SceneDescription)
    assert scene.task == TASK
    assert set(metrics.measurements) == {"bowlPlaceError", "spoonPlaceError"}
    assert all(error <= PLACE_TOLERANCE for error in metrics.measurements.values())


def test_the_run_steps_through_its_lookups_and_its_groundings(garmi_run):
    _, bundle = garmi_run
    scene = DocumentFile(bundle / BundleFile.SCENE).read(SceneDescription)
    steps = DocumentFile(bundle / scene.query_steps).read(QuerySteps).steps
    lookups = [step for step in steps if step.phase is not StepPhase.RESOLUTION]
    groundings = [step for step in steps if step.phase is StepPhase.RESOLUTION]
    assert [step.caller.function for step in lookups] == [
        "GarmiApartmentDemo.the_robot",
        "GarmiApartmentDemo.the_bowl",
        "GarmiApartmentDemo.the_spoon",
    ]
    assert len(groundings) >= 4
    assert all(step.generates and step.answers for step in groundings)
    assert {step.during for step in groundings} == {TransportAction.__name__}
