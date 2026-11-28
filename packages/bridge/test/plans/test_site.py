"""
Where a plan stands its robot to work: the frame the robot profile's zones on the table
are written in.
"""

from __future__ import annotations

import pytest

from cramera_bridge.plans.site import RobotSite
from cramera_protocol.geometry import Pose
from cramera_protocol.plan_builder import (
    DemoDocument,
    LegacyStepKind,
    MigratedActionField,
    PlanDocument,
)

# %% plans

START = Pose(-1.5, -0.3, 0.9, 0.0, 0.0, 0.0, 1.0)
"""
Where the robot starts, away from its table.
"""

AT_THE_TABLE = Pose(0.0, 0.0, 0.9, 0.0, 0.0, 0.0, 1.0)
"""
Where the robot walks to, at its table.
"""


def plan_with_steps(steps: list[dict]) -> PlanDocument:
    """
    :param steps: The steps of the plan's one robot.
    :return: A plan whose robot starts at :data:`START` and takes the steps.
    """
    return PlanDocument.from_json(
        {
            "formatVersion": "1.4",
            "name": "site",
            "task": "",
            "environment": "table",
            "selectedRobot": "robot_1",
            "robots": [
                {
                    "id": "robot_1",
                    "model": "robot",
                    "label": "Robot",
                    "pose": START.to_json(),
                    "steps": steps,
                }
            ],
            "objects": [],
        }
    )


def navigation(identifier: str, target: Pose) -> dict:
    """
    :return: A step walking the robot to `target`.
    """
    return {
        "id": identifier,
        "action": LegacyStepKind.NAVIGATE.value,
        "values": {MigratedActionField.TARGET.value: target.to_json()},
    }


PARK = {"id": "step_2", "action": "park_arms", "values": {"arms": "both"}}
"""
A step that leaves the robot where it stands.
"""

# %% the site


def test_a_robot_that_stays_put_works_where_it_starts():
    site = RobotSite.of_demo(DemoDocument(plan=plan_with_steps([PARK])))

    assert site.pose == START


def test_a_robot_that_walks_works_where_its_last_walk_ends():
    plan = plan_with_steps(
        [navigation("step_1", START), navigation("step_2", AT_THE_TABLE), PARK]
    )

    site = RobotSite.of_demo(DemoDocument(plan=plan))

    assert site.pose == AT_THE_TABLE


def test_a_zone_lies_in_front_of_where_the_robot_walked_to():
    plan = plan_with_steps([navigation("step_1", AT_THE_TABLE), PARK])

    site = RobotSite.of_demo(DemoDocument(plan=plan))

    assert site.to_world(0.5, 0.0) == pytest.approx((0.5, 0.0))
