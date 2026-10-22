"""
The plan with native statuses, and the constraints attached to its nodes.
"""

from __future__ import annotations

import json
from http import HTTPStatus

import pytest

from cramera_cram.exceptions import (
    InvalidConstraint,
    RobotSelectionBusy,
    UnknownBody,
    UnknownPlanNode,
)
from cramera_cram.live.plan import PLAN_NODE_PREFIX, PlanPublisher
from cramera_protocol.live import LiveRoute
from cramera_protocol.live_messages import (
    ConstraintActivation,
    ConstraintMonitorType,
    ConstraintRequest,
    LivePlan,
    MonitorSpecification,
    PlanNodeReference,
    RobotSelection,
)
from coraplex.datastructures.enums import Arms, TaskStatus
from giskardpy.motion_statechart.data_types import ObservationStateValues
from cramera.http.messages import HttpMethod

from ..dataset.live_worlds import HeightChart
from .conftest import dataset_body, live_request

# %% plan


def test_every_node_shows_its_own_native_status(publisher, small_plan):
    small_plan.root.status = TaskStatus.RUNNING
    publisher.begin_plan(small_plan.plan)
    plan = publisher.current_plan()
    assert [node.status for node in plan.nodes] == [
        TaskStatus.RUNNING.name,
        TaskStatus.CREATED.name,
        TaskStatus.CREATED.name,
    ]
    assert plan.nodes[1].parent == plan.nodes[0].identifier
    assert plan.nodes[1].label == type(small_plan.action.designator).__name__


def test_a_parent_status_is_never_derived_from_its_children(publisher, small_plan):
    small_plan.action.status = TaskStatus.SUCCEEDED
    publisher.begin_plan(small_plan.plan)
    root = publisher.current_plan().nodes[0]
    assert root.status == TaskStatus.CREATED.name


def test_a_motion_names_its_arm_and_object(publisher, small_plan, kitchen):
    publisher.begin_plan(small_plan.plan)
    motion = publisher.current_plan().nodes[2]
    assert motion.arm == Arms.LEFT.name
    assert motion.target == str(kitchen.milk.id)


def test_a_node_is_found_by_its_identity(publisher, small_plan):
    publisher.begin_plan(small_plan.plan)
    identifier = PlanPublisher.identifier(small_plan.action)
    assert identifier.startswith(PLAN_NODE_PREFIX)
    assert publisher.plan.published_node(identifier).identifier == identifier
    with pytest.raises(UnknownPlanNode):
        publisher.plan.published_node("plan_node_99")


def test_no_plan_has_no_nodes(publisher):
    assert publisher.current_plan() == LivePlan()
    assert publisher.plan.running_action() is None


def test_the_running_action_names_the_step(publisher, small_plan):
    small_plan.action.status = TaskStatus.RUNNING
    publisher.begin_plan(small_plan.plan)
    assert (
        publisher.plan.running_action() == type(small_plan.action.designator).__name__
    )


def test_a_robot_cannot_be_selected_while_the_plan_runs(publisher, small_plan):
    small_plan.root.status = TaskStatus.RUNNING
    publisher.begin_plan(small_plan.plan)
    with pytest.raises(RobotSelectionBusy):
        publisher.select_robot(RobotSelection(identifier="any"))


# %% constraints


def height_constraint(kitchen, small_plan, activation) -> ConstraintRequest:
    """
    :return: A height constraint on the milk attached to the plan's root.
    """
    return ConstraintRequest(
        target_plan_node=PlanNodeReference(
            identifier=PlanPublisher.identifier(small_plan.root)
        ),
        monitor=MonitorSpecification(
            monitor_type=ConstraintMonitorType.HEIGHT,
            parameters={"tip_link": kitchen.milk.name.name, "lower_limit": 0.5},
        ),
        text="keep the milk up",
        apply=activation,
    )


def test_an_attached_constraint_is_observed_on_the_next_tick(
    publisher, kitchen, small_plan
):
    publisher.begin_plan(small_plan.plan)
    publisher.attach_constraint(
        height_constraint(kitchen, small_plan, ConstraintActivation.IMMEDIATE)
    )
    chart = HeightChart.build(kitchen.world, kitchen.milk)
    publisher.observe_motion_tick(chart.chart)
    constraint = publisher.refresh_plan().nodes[0].constraints[0]
    assert constraint.observation == ObservationStateValues.TRUE.name


def test_a_constraint_waits_for_the_next_motion(publisher, kitchen, small_plan):
    publisher.begin_plan(small_plan.plan)
    publisher.attach_constraint(
        height_constraint(kitchen, small_plan, ConstraintActivation.NEXT_ACTIVATION)
    )
    chart = HeightChart.build(kitchen.world, kitchen.milk)
    publisher.observe_motion_tick(chart.chart)
    assert publisher.refresh_plan().nodes[0].constraints[0].observation is None
    publisher.observe_node_started(small_plan.motion)
    publisher.observe_motion_tick(chart.chart)
    observed = publisher.refresh_plan().nodes[0].constraints[0]
    assert observed.observation == ObservationStateValues.TRUE.name


def test_a_constraint_sees_the_world_change(publisher, kitchen, small_plan):
    publisher.begin_plan(small_plan.plan)
    publisher.attach_constraint(
        height_constraint(kitchen, small_plan, ConstraintActivation.IMMEDIATE)
    )
    chart = HeightChart.build(kitchen.world, kitchen.milk)
    publisher.observe_motion_tick(chart.chart)
    kitchen.milk_connection.origin = type(kitchen.milk_connection.origin).from_xyz_rpy(
        1.0, 0.1, 0.1, reference_frame=kitchen.root
    )
    publisher.observe_motion_tick(chart.chart)
    observed = publisher.refresh_plan().nodes[0].constraints[0]
    assert observed.observation == ObservationStateValues.FALSE.name


@pytest.mark.parametrize(
    "monitor_type, parameters",
    [
        (ConstraintMonitorType.VECTORS_ALIGNED, {"tip_link": "milk"}),
        (
            ConstraintMonitorType.POINTING_AT,
            {"tip_link": "milk", "goal_point_body": "cup"},
        ),
        (
            ConstraintMonitorType.POINTING_AT,
            {"tip_link": "milk", "goal_point": [1, 0, 0]},
        ),
        (ConstraintMonitorType.DISTANCE, {"root_link": "map", "tip_link": "milk"}),
    ],
)
def test_every_monitor_type_is_built_and_observed(
    publisher, kitchen, small_plan, monitor_type, parameters
):
    publisher.begin_plan(small_plan.plan)
    request = ConstraintRequest(
        target_plan_node=PlanNodeReference(
            identifier=PlanPublisher.identifier(small_plan.action)
        ),
        monitor=MonitorSpecification(monitor_type=monitor_type, parameters=parameters),
        apply=ConstraintActivation.IMMEDIATE,
    )
    publisher.attach_constraint(request)
    publisher.observe_motion_tick(HeightChart.build(kitchen.world, kitchen.milk).chart)
    constraint = publisher.refresh_plan().nodes[1].constraints[0]
    assert constraint.monitor == monitor_type
    assert constraint.observation in ObservationStateValues.__members__


@pytest.mark.parametrize(
    "parameters, error",
    [
        ({"tip_link": "fridge"}, UnknownBody),
        ({"tip_link": 3}, InvalidConstraint),
        ({"tip_link": "milk", "goal_normal": [1, 0]}, InvalidConstraint),
    ],
)
def test_an_unreadable_constraint_is_refused(publisher, small_plan, parameters, error):
    publisher.begin_plan(small_plan.plan)
    request = ConstraintRequest(
        target_plan_node=PlanNodeReference(
            identifier=PlanPublisher.identifier(small_plan.root)
        ),
        monitor=MonitorSpecification(
            monitor_type=ConstraintMonitorType.VECTORS_ALIGNED, parameters=parameters
        ),
    )
    with pytest.raises(error):
        publisher.attach_constraint(request)


def test_a_limit_must_be_a_number(publisher, small_plan):
    publisher.begin_plan(small_plan.plan)
    request = ConstraintRequest(
        target_plan_node=PlanNodeReference(
            identifier=PlanPublisher.identifier(small_plan.root)
        ),
        monitor=MonitorSpecification(
            monitor_type=ConstraintMonitorType.HEIGHT,
            parameters={"tip_link": "milk", "lower_limit": "low"},
        ),
    )
    with pytest.raises(InvalidConstraint):
        publisher.attach_constraint(request)


def test_pointing_needs_a_goal(publisher, small_plan):
    publisher.begin_plan(small_plan.plan)
    request = ConstraintRequest(
        target_plan_node=PlanNodeReference(
            identifier=PlanPublisher.identifier(small_plan.root)
        ),
        monitor=MonitorSpecification(
            monitor_type=ConstraintMonitorType.POINTING_AT,
            parameters={"tip_link": "milk"},
        ),
    )
    with pytest.raises(InvalidConstraint):
        publisher.attach_constraint(request)


def test_a_constraint_posted_by_the_plan_view_reaches_its_node(
    publisher, answerer, small_plan, kitchen
):
    publisher.begin_plan(small_plan.plan)
    answer = answerer.answer(
        live_request(
            HttpMethod.POST,
            LiveRoute.CONSTRAINT,
            dataset_body("height_constraint.json"),
        )
    )
    plan = LivePlan.from_json(json.loads(answer.body))
    assert answer.status is HTTPStatus.OK
    assert [node.constraints != [] for node in plan.nodes] == [False, True, False]
