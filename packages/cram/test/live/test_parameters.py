"""
The fields of a plan's actions as the texts a replayed step shows.
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from cramera_cram.live.parameters import (
    LIST_SEPARATOR,
    MAXIMUM_TEXT_LENGTH,
    PARAMETER_PRECISION,
    BooleanText,
    FieldDeclarations,
    FieldPoses,
    FieldTexts,
    FieldValue,
    ParameterText,
)
from coraplex.datastructures.enums import Arms
from coraplex.robot_plans.actions.core.navigation import NavigateAction
from coraplex.robot_plans.actions.core.robot_body import MoveTorsoAction
from cramera_cram.geometry import NumericPose
from semantic_digital_twin.spatial_types import Point3, Pose

from cramera_protocol.bundle.scene import FieldValueKind

from ..dataset.live_worlds import Approach, Hint, Side

# %% values


@pytest.mark.parametrize(
    "value, text",
    [
        (None, None),
        (True, BooleanText.YES),
        (False, BooleanText.NO),
        (Arms.LEFT, Arms.LEFT.name),
        (3, "3"),
        ("shelf", "shelf"),
    ],
)
def test_a_plain_value_reads_as_itself(value, text):
    assert ParameterText().text(value) == text


def test_a_number_is_rounded():
    assert float(ParameterText().text(0.123456)) == round(0.123456, PARAMETER_PRECISION)


def test_a_body_is_named(kitchen):
    assert ParameterText().text(kitchen.milk) == kitchen.milk.name.name


def test_a_pose_shows_its_position_heading_and_frame(kitchen):
    pose = Pose.from_xyz_rpy(
        1.2, 0.4, 0.0, 0.0, 0.0, math.pi / 2, reference_frame=kitchen.root
    )
    assert (
        ParameterText().text(pose)
        == f"(1.2, 0.4, 0) yaw 90° in {kitchen.root.name.name}"
    )


def test_a_point_shows_its_position(kitchen):
    point = Point3(1.0, -0.25, 0.5, reference_frame=kitchen.root)
    assert ParameterText().text(point) == f"(1, -0.25, 0.5) in {kitchen.root.name.name}"


def test_a_class_is_named():
    assert ParameterText().text(MoveTorsoAction) == MoveTorsoAction.__name__


def test_a_list_shows_its_items():
    assert ParameterText().text([Arms.LEFT, Arms.RIGHT]) == LIST_SEPARATOR.join(
        [Arms.LEFT.name, Arms.RIGHT.name]
    )


def test_a_dataclass_value_shows_the_fields_it_was_given():
    assert ParameterText().text(
        Approach(Side.TOP, rotated=True)
    ) == LIST_SEPARATOR.join([f"side {Side.TOP.name}", f"rotated {BooleanText.YES}"])


def test_any_other_value_is_named_by_its_class():
    assert ParameterText().text(object()) == object.__name__


def test_a_long_text_is_shortened():
    text = ParameterText().text("x" * (2 * MAXIMUM_TEXT_LENGTH))
    assert len(text) == MAXIMUM_TEXT_LENGTH


# %% fields


def test_a_field_left_at_its_default_is_not_shown():
    assert FieldTexts(Approach(Side.FRONT)).texts() == {"side": Side.FRONT.name}


def test_a_field_given_another_value_than_its_default_is_shown():
    texts = FieldTexts(Approach(Side.FRONT, offset=0.1)).texts()
    assert texts == {"side": Side.FRONT.name, "offset": ParameterText().text(0.1)}


# %% declared fields


def test_every_field_of_an_action_is_declared_in_its_order():
    declarations = FieldDeclarations(Approach(Side.FRONT)).declarations()
    assert [field.name for field in declarations] == [
        declared.name for declared in dataclasses.fields(Approach)
    ]
    assert [field.required for field in declarations] == [True, False, False]


def test_a_declared_field_names_its_plain_default():
    side, offset, rotated = FieldDeclarations(Approach(Side.TOP)).declarations()
    defaults = {
        declared.name: declared.default for declared in dataclasses.fields(Approach)
    }
    assert side.default is None
    assert offset.default == ParameterText().text(defaults[offset.name])
    assert rotated.default == BooleanText.NO


# %% kinds of values


@pytest.mark.parametrize(
    "value, kind",
    [
        (True, FieldValueKind.BOOLEAN),
        (Arms.LEFT, FieldValueKind.ENUMERATION),
        (3, FieldValueKind.NUMBER),
        (0.25, FieldValueKind.NUMBER),
        ("shelf", FieldValueKind.TEXT),
        (MoveTorsoAction, FieldValueKind.CLASS),
        ([Arms.LEFT, Arms.RIGHT], FieldValueKind.LIST),
        (Approach(Side.TOP), FieldValueKind.STRUCTURE),
        (object(), FieldValueKind.OTHER),
    ],
)
def test_a_value_is_named_by_its_kind(value, kind):
    assert FieldValue(value).kind() == kind


def test_poses_points_and_bodies_are_named_by_their_kind(kitchen):
    assert [
        FieldValue(Pose.from_xyz_rpy(reference_frame=kitchen.root)).kind(),
        FieldValue(Point3(0.0, 0.0, 0.0, reference_frame=kitchen.root)).kind(),
        FieldValue(kitchen.milk).kind(),
    ] == [FieldValueKind.POSE, FieldValueKind.POINT, FieldValueKind.ENTITY]


def test_a_declared_field_names_the_kind_of_its_value():
    side, offset, rotated = FieldDeclarations(
        Approach(Side.TOP, offset=0.2)
    ).declarations()
    assert (side.kind, offset.kind, rotated.kind) == (
        FieldValueKind.ENUMERATION,
        FieldValueKind.NUMBER,
        FieldValueKind.BOOLEAN,
    )


def test_a_field_neither_given_nor_with_a_default_has_no_kind():
    [note] = FieldDeclarations(Hint()).declarations()
    assert note.kind is None


# %% poses


def test_a_pose_field_keeps_its_pose_and_its_frame(kitchen):
    target = Pose.from_xyz_rpy(
        1.2, 0.4, 0.0, 0.0, 0.0, math.pi / 2, reference_frame=kitchen.root
    )
    action = NavigateAction(target)
    poses = FieldPoses(action).poses()
    assert set(poses) == {
        name for name, value in vars(action).items() if isinstance(value, Pose)
    }
    [given] = poses.values()
    assert given.pose == NumericPose.of_matrix(target.to_np()).published()
    assert given.frame == kitchen.root.name.name
