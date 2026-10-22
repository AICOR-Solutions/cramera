"""
Straight workshop translations: the corridor is checked against the collision shapes
before the base moves, and a target that turns the base or lies too far is refused.
"""

from __future__ import annotations

import math

import pytest

from cramera_workshop.robot.navigation import (
    TRANSLATION_LIMITS,
    TranslationBlocked,
    TranslationProblem,
    WorkshopTranslation,
)
from semantic_digital_twin.spatial_types import Pose

AISLE_Y = -1.62
"""
The free aisle's y position, in metres.
"""


def translation(context, x: float, y: float, yaw: float) -> WorkshopTranslation:
    return WorkshopTranslation(
        context.world,
        context.robot,
        Pose.from_xyz_rpy(x, y, yaw=yaw, reference_frame=context.world.root),
    )


def start_of(context):
    return context.robot.root.global_pose


def test_a_free_corridor_is_certified(assembly_context):
    start = start_of(assembly_context)
    clearance = translation(assembly_context, start.x, AISLE_Y, math.pi / 2).validate()
    distance = abs(AISLE_Y - start.y)
    assert (
        clearance.samples
        == math.ceil(distance / TRANSLATION_LIMITS.maximum_sample_spacing) + 1
    )
    assert clearance.sample_spacing <= TRANSLATION_LIMITS.maximum_sample_spacing
    assert clearance.minimum_clearance > 0


def test_a_corridor_into_the_shelf_is_blocked(assembly_context):
    start = start_of(assembly_context)
    with pytest.raises(TranslationBlocked) as blocked:
        translation(assembly_context, start.x, 0.1, math.pi / 2).validate()
    assert blocked.value.problem is TranslationProblem.OBSTRUCTION
    assert blocked.value.pair is not None
    assert str(blocked.value.pair[0]) in blocked.value.error_message()


def test_a_turning_target_is_refused(assembly_context):
    start = start_of(assembly_context)
    with pytest.raises(TranslationBlocked) as blocked:
        translation(assembly_context, start.x, AISLE_Y, 0.0).world_target()
    assert blocked.value.problem is TranslationProblem.ORIENTATION
    assert blocked.value.error_message() == TranslationProblem.ORIENTATION.value


def test_a_far_target_is_refused(assembly_context):
    start = start_of(assembly_context)
    far = start.y - 2 * TRANSLATION_LIMITS.maximum_distance
    with pytest.raises(TranslationBlocked) as blocked:
        translation(assembly_context, start.x, far, math.pi / 2).world_target()
    assert blocked.value.problem is TranslationProblem.LIMITS
