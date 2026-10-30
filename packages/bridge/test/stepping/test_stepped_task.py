"""
A robot task run with its queries stepped: published from before its setup, held at each
query of its own until the viewer moves it on, and recorded with them.
"""

from __future__ import annotations

import threading
import time

import pytest
from typing_extensions import List

from cramera.locations import DataLocations
from cramera_bridge.demos.navigation import BarrierEnvironment
from cramera_bridge.documents import DocumentFile
from cramera_bridge.visualization import LiveVisualization
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.query_steps import QuerySteps, StepAdvance, StepMoment, StepPhase
from semantic_digital_twin.robots.pr2 import PR2
from semantic_digital_twin.specifications.robots import RobotSpecification

from ..dataset.demos import GroundedTorsoAction, QueryingTorsoDemo

TASK = "PR2: raise the torso, finding it by a query"
"""
The task label of the stepped demo.
"""

WAIT_SECONDS = 120.0
"""
How long a test waits for a run to reach a step or to end, in seconds.
"""

# %% fixtures


@pytest.fixture
def locations(tmp_path) -> DataLocations:
    """
    :return: Data locations below the test's directory.
    """
    return DataLocations(data=tmp_path / "data", shared_scenes=None)


def querying_demo(locations: DataLocations, **changes) -> QueryingTorsoDemo:
    """
    :param locations: Where the recording is saved.
    :param changes: Fields that differ from the test task.
    :return: A PR2 finding itself by a query and raising its torso by a grounded move.
    """
    fields = dict(
        environment=BarrierEnvironment(distance=2.0),
        robot=RobotSpecification(semantic_annotation_type=PR2),
        name="barrier_pr2_stepped_torso",
        task=TASK,
        locations=locations,
        port=0,
    )
    fields.update(changes)
    return QueryingTorsoDemo(**fields)


@pytest.fixture(scope="module")
def stepped_run(tmp_path_factory):
    """
    :return: The demo of one run stepping through its queries without holding, and
        its saved recording's directory.
    """
    root = tmp_path_factory.mktemp("stepped")
    demo = querying_demo(
        DataLocations(data=root / "data", shared_scenes=None),
        step_queries=True,
        holds_at_queries=False,
    )
    saved = demo.run()
    return demo, demo.locations.local_scenes / saved.scene


def recorded_steps(bundle) -> QuerySteps:
    """
    :param bundle: A saved recording.
    :return: The query steps it keeps.
    """
    scene = DocumentFile(bundle / BundleFile.SCENE).read(SceneDescription)
    return DocumentFile(bundle / scene.query_steps).read(QuerySteps)


# %% stepping


def test_the_run_records_the_queries_of_its_own(stepped_run):
    _, bundle = stepped_run
    finding, grounding = recorded_steps(bundle).steps
    assert finding.phase is StepPhase.SETUP
    assert finding.during == TASK
    assert finding.caller.function == "QueryingTorsoDemo.build_context"
    assert len(finding.answers) == 1
    assert grounding.phase is StepPhase.RESOLUTION
    assert grounding.during == GroundedTorsoAction.__name__
    assert grounding.caller.module == "underspecified"
    assert grounding.generates
    assert all(step.moment is StepMoment.ANSWERED for step in (finding, grounding))


def test_the_recording_is_stamped_with_a_clock_that_stops_while_held(stepped_run):
    demo, _ = stepped_run
    stepper = demo.stepper
    assert stepper.publisher.recording.clock == stepper.control.running_time
    assert not stepper.control.stepping


def test_a_run_not_stepping_records_no_queries(locations):
    demo = querying_demo(locations)
    saved = demo.run()
    scene = DocumentFile(locations.local_scenes / saved.scene / BundleFile.SCENE).read(
        SceneDescription
    )
    assert demo.stepper is None
    assert scene.query_steps is None


# %% holding


def test_a_held_run_carries_on_each_time_the_viewer_moves_it_on(locations):
    demo = querying_demo(locations, step_queries=True)
    saved = []
    thread = threading.Thread(target=lambda: saved.append(demo.run()))
    thread.start()
    held = []
    deadline = time.monotonic() + WAIT_SECONDS
    while thread.is_alive() and time.monotonic() < deadline:
        board = None if demo.stepper is None else demo.stepper.publisher.query_steps
        step = None if board is None else board.current().held
        if step is None or (step.number, step.moment) in held:
            time.sleep(0.05)
            continue
        held.append((step.number, step.moment))
        board.advance(StepAdvance(held=step))
    thread.join(timeout=WAIT_SECONDS)
    assert held == [
        (0, StepMoment.ASKED),
        (0, StepMoment.ANSWERED),
        (1, StepMoment.ASKED),
        (1, StepMoment.ANSWERED),
    ]
    assert len(saved) == 1


def test_a_held_run_is_let_go_when_its_visualization_stops(locations):
    demo = querying_demo(locations, step_queries=True)
    world = demo.build_world()
    visualization = LiveVisualization(world=world, port=0, locations=locations).start()
    contexts: List = []

    def set_up() -> None:
        with demo.stepping(visualization):
            contexts.append(demo.build_context(world))

    thread = threading.Thread(target=set_up)
    thread.start()
    deadline = time.monotonic() + WAIT_SECONDS
    while (
        demo.stepper is None or demo.stepper.control.held is None
    ) and time.monotonic() < deadline:
        time.sleep(0.05)
    visualization.stop()
    thread.join(timeout=WAIT_SECONDS)
    assert not thread.is_alive()
    assert len(contexts) == 1
    assert not demo.stepper.control.stepping
