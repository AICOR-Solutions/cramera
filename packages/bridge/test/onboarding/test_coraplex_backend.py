"""
This package's live visualization as the world visualization of coraplex's executors,
and the registration adding it to the executors a demo creates.
"""

from __future__ import annotations

import pytest
from typing_extensions import List

from coraplex.plans.executors import KinematicallySimulatedPlanExecutor, PlanExecutor
from cramera_bridge.coraplex_backend import (
    CoraplexBackendRegistration,
    CrameraVisualization,
)
from cramera_bridge.visualization import LiveVisualization
from cramera_bridge.questions.workspace_classes import WorkspaceClassIndex
from cramph.composites import Sequence
from cramph.context import StatechartContext
from cramph.statechart import Statechart

from ..dataset.onboarding.sliding_box_demo import (
    BOX_HEIGHTS,
    BoxLowering,
    SlidingBoxWorld,
)

# %% helpers


@pytest.fixture
def created(locations) -> List[LiveVisualization]:
    """
    :return: The visualizations :func:`factory` created, in order.
    """
    return []


@pytest.fixture
def factory(locations, created):
    """
    :return: A factory of visualizations serving on a free port into the test's
        locations, which notes each one it creates.
    """

    def create(world) -> LiveVisualization:
        visualization = LiveVisualization(
            world=world,
            port=0,
            locations=locations,
            read_ros_markers=False,
            read_robokudo_images=False,
            class_index=WorkspaceClassIndex(),
        )
        created.append(visualization)
        return visualization

    return create


def executor_of(scene: SlidingBoxWorld) -> KinematicallySimulatedPlanExecutor:
    """
    :param scene: The world a plan is performed in.
    :return: A new executor of a plan in it.
    """
    return KinematicallySimulatedPlanExecutor(StatechartContext(world=scene.world))


def lower_the_box(executor: PlanExecutor, scene: SlidingBoxWorld) -> Statechart:
    """
    Perform the sliding box demo's plan with an executor.

    :param executor: The executor.
    :param scene: The world it performs the plan in.
    :return: The statechart the plan ran as.
    """
    statechart = Statechart(context=executor.context)
    statechart.add_node(
        Sequence(
            nodes=[
                BoxLowering(name=str(height), scene=scene, height=height)
                for height in BOX_HEIGHTS
            ]
        )
    )
    executor.compile(statechart)
    executor.execute()
    return statechart


def cramera_visualizations(executor: PlanExecutor) -> List[CrameraVisualization]:
    """
    :param executor: A plan executor.
    :return: The cramera visualizations among its extensions.
    """
    return [
        extension
        for extension in executor.extensions
        if isinstance(extension, CrameraVisualization)
    ]


# %% the executor extension


def test_the_visualization_publishes_the_plan_its_executor_runs(sliding_box, factory):
    visualization = CrameraVisualization(factory=factory)
    executor = KinematicallySimulatedPlanExecutor(
        StatechartContext(world=sliding_box.world), extensions=[visualization]
    )
    statechart = Statechart(context=executor.context)
    statechart.add_node(
        Sequence(nodes=[BoxLowering(name="down", scene=sliding_box, height=1.0)])
    )
    executor.compile(statechart)
    published = visualization.live.publisher.current_plan()
    executor.execute()
    assert [node.label for node in published.nodes] == ["Sequence", "BoxLowering"]


def test_a_visualization_it_started_stops_once_the_run_stopped(
    sliding_box, factory, created
):
    executor = KinematicallySimulatedPlanExecutor(
        StatechartContext(world=sliding_box.world),
        extensions=[CrameraVisualization(factory=factory)],
    )
    lower_the_box(executor, sliding_box)
    assert [visualization.server for visualization in created] == [None]


def test_a_visualization_it_was_given_keeps_running_after_the_run(sliding_box, factory):
    live = factory(world=sliding_box.world).start()
    executor = KinematicallySimulatedPlanExecutor(
        StatechartContext(world=sliding_box.world),
        extensions=[CrameraVisualization(live=live)],
    )
    lower_the_box(executor, sliding_box)
    running = live.server is not None
    live.stop()
    assert running


# %% registration


def test_a_registration_shows_every_executor_of_the_world_through_one_visualization(
    sliding_box, factory, created
):
    with CoraplexBackendRegistration(factory=factory) as registration:
        executors = [executor_of(sliding_box), executor_of(sliding_box)]
        for executor in executors:
            lower_the_box(executor, sliding_box)
        plans = len(registration.live.publisher.plan.performed_plans())
    assert [len(cramera_visualizations(executor)) for executor in executors] == [1, 1]
    assert len(created) == 1 and created[0].world is sliding_box.world
    assert plans == 2


def test_an_executor_of_another_world_is_not_shown(sliding_box, factory):
    with CoraplexBackendRegistration(factory=factory):
        executor_of(sliding_box)
        other = executor_of(SlidingBoxWorld.build())
    assert cramera_visualizations(other) == []


def test_leaving_stops_the_visualization_and_restores_the_executors(
    sliding_box, factory, created
):
    unregistered = PlanExecutor.__post_init__
    with CoraplexBackendRegistration(factory=factory):
        executor_of(sliding_box)
    after = executor_of(sliding_box)
    assert PlanExecutor.__post_init__ is unregistered
    assert cramera_visualizations(after) == []
    assert [visualization.server for visualization in created] == [None]


def test_the_innermost_registration_shows_the_executors(sliding_box, factory, created):
    with CoraplexBackendRegistration():
        with CoraplexBackendRegistration(factory=factory):
            executor_of(sliding_box)
        shown_inside = len(created)
    assert shown_inside == 1
