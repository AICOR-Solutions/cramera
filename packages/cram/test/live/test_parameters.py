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
    FieldTexts,
    ParameterText,
)
from coraplex.datastructures.enums import Arms
from coraplex.robot_plans.actions.core.robot_body import MoveTorsoAction
from semantic_digital_twin.spatial_types import Point3, Pose

from ..dataset.live_worlds import Approach, Side

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
