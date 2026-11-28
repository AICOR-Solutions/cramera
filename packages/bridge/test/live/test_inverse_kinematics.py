"""
Inverse kinematics of an arm chain for hand control.
"""

from __future__ import annotations

import numpy
import pytest

from cramera_bridge.live.inverse_kinematics import (
    POSITION_TOLERANCE_METRES,
    ChainInverseKinematics,
)

from ..dataset.worlds import RobotWorld


@pytest.fixture
def chain() -> ChainInverseKinematics:
    """
    :return: The inverse kinematics of a PR2's left arm.
    """
    robot_world = RobotWorld.build()
    arm = robot_world.robot.get_left_arm_if_specified()
    return ChainInverseKinematics(
        robot_world.world, arm.root, arm.end_effector.tool_frame
    )


def tool_pose(chain: ChainInverseKinematics) -> numpy.ndarray:
    """
    :return: The tip's pose in the root frame.
    """
    return chain.world.compute_forward_kinematics_np(chain.root, chain.tip)


def test_a_reachable_target_is_solved_without_moving_the_world(chain):
    start = tool_pose(chain)
    target = start.copy()
    target[0, 3] -= 0.03
    solution = chain.solve(target, 60)
    assert solution is not None
    assert tool_pose(chain) == pytest.approx(start)
    for degree_of_freedom, value in solution.items():
        chain.world.state[degree_of_freedom.id].position = value
    chain.world.notify_state_change()
    reached = tool_pose(chain)
    assert numpy.linalg.norm(reached[:3, 3] - target[:3, 3]) <= (
        POSITION_TOLERANCE_METRES
    )
    assert reached[:3, :3] == pytest.approx(start[:3, :3], abs=1e-2)


def test_a_target_beyond_the_reach_of_the_arm_has_no_solution(chain):
    target = tool_pose(chain)
    target[0, 3] += 0.03
    assert chain.solve(target, 60) is None


def test_a_solution_keeps_the_joints_within_their_limits(chain):
    target = tool_pose(chain)
    target[0, 3] -= 0.03
    solution = chain.solve(target, 60)
    for degree_of_freedom, value in solution.items():
        lower = degree_of_freedom.limits.lower.position
        upper = degree_of_freedom.limits.upper.position
        assert lower is None or value >= lower
        assert upper is None or value <= upper
