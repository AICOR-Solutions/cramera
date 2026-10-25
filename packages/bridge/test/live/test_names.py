"""
The table between CRAM's names and the protocol's: it must follow CRAM, so a rename
there fails here, in the bridge, and nowhere else.
"""

from __future__ import annotations

import pytest

from coraplex.plans.plan_node import PlanNode
from coraplex.robot_plans.actions.core.pick_up import PickUpAction
from cramera_bridge.names import (
    ACTION_NAMES,
    ACTIONS,
    PLAN_NODE_KINDS,
    ROBOT_NAMES,
    ROBOTS,
    PinnedClass,
    derived_identifier,
    plan_node_kind,
    plan_node_classes,
)
from cramera_bridge.plans.actions import ActionDiscovery
from cramera_bridge.plans.workspace import RobotAnnotations
from cramera_protocol.bundle.scene import PlanNodeKind
from semantic_digital_twin.robots.pr2 import PR2

# %% the table follows CRAM


@pytest.mark.parametrize("entry", ACTIONS + ROBOTS, ids=lambda entry: entry.identifier)
def test_every_pinned_class_is_where_the_table_says(entry: PinnedClass):
    resolved = entry.resolve()
    assert f"{resolved.__module__}.{resolved.__name__}" == entry.path


def test_every_action_the_workspace_offers_is_pinned():
    discovered = ActionDiscovery().discover().actions
    unpinned = [
        action.action_class.__name__
        for action in discovered
        if ACTION_NAMES.entry_of(action.action_class) is None
    ]
    assert unpinned == [], "pin these actions in cramera_bridge/names.py"


def test_every_robot_the_workspace_offers_is_pinned():
    unpinned = [
        annotation.__name__
        for annotation in RobotAnnotations().annotations()
        if ROBOT_NAMES.entry_of(annotation) is None
    ]
    assert unpinned == [], "pin these robots in cramera_bridge/names.py"


def test_identifiers_are_unique_and_snake_case():
    for table in (ACTIONS, ROBOTS):
        identifiers = [entry.identifier for entry in table]
        assert len(set(identifiers)) == len(identifiers)
        assert all(identifier == identifier.lower() for identifier in identifiers)


def test_every_plan_node_class_of_the_table_exists():
    assert len(plan_node_classes()) == len(PLAN_NODE_KINDS)


# %% translating


def test_a_class_is_named_by_its_identifier_and_found_by_its_saved_name():
    assert ACTION_NAMES.identifier_of(PickUpAction) == "pick_up"
    assert ROBOT_NAMES.identifier_of(PR2) == "pr2"
    assert ACTION_NAMES.matches(PickUpAction, "pick_up")
    assert ACTION_NAMES.matches(PickUpAction, "PickUpAction")
    assert not ACTION_NAMES.matches(PickUpAction, "place")


def test_a_class_not_pinned_yet_gets_an_identifier_from_its_name():
    class SwirlingAction:
        pass

    assert ACTION_NAMES.identifier_of(SwirlingAction) == "swirling"
    assert ACTION_NAMES.saved_as(SwirlingAction) == ["SwirlingAction"]
    assert derived_identifier("FollowToolCenterPointPathAction", "Action") == (
        "follow_tool_center_point_path"
    )
    assert derived_identifier("MMPDresden") == "mmp_dresden"


def test_plan_nodes_are_named_by_the_protocols_kinds(small_plan):
    assert plan_node_kind(small_plan.action) is PlanNodeKind.ACTION
    assert plan_node_kind(small_plan.motion) is PlanNodeKind.MOTION
    assert plan_node_kind(PlanNode()) is PlanNodeKind.OTHER
