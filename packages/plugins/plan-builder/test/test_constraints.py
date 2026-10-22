"""
Compiling constraints written in plain language with the rule book.
"""

from __future__ import annotations

import pytest

from cramera_plan_builder.constraints import ConstraintCompiler, NamedObjects
from cramera_plan_builder.exceptions import (
    ConstraintReferenceMissing,
    ConstraintSubjectMissing,
)
from cramera_protocol.live_messages import ConstraintMonitorType, MonitorParameterKey
from cramera_protocol.plan_builder import (
    ConstraintText,
    RuleValue,
    StepKind,
    StepSwitch,
)

EXAMPLE_SEPARATOR = ", "
"""
Separates the wordings a rule lists as its examples.
"""


@pytest.fixture(scope="module")
def compiler() -> ConstraintCompiler:
    """
    :return: The compiler of the rule book the builder ships.
    """
    return ConstraintCompiler.of_file()


def attached(text: str, step_kind: StepKind = StepKind.PICK_UP, **fields):
    """
    :param text: A constraint.
    :param step_kind: The kind of step it is attached to.
    :param fields: The other fields of the request.
    :return: The request compiling the constraint on such a step.
    """
    return ConstraintText(text=text, step_kind=step_kind, **fields)


# %% the rule book


def test_every_example_of_a_rule_is_understood_as_that_rule(compiler):
    for rule in compiler.book.rules:
        for example in rule.examples.split(EXAMPLE_SEPARATOR):
            assert compiler.rule_for(example) is rule, example


def test_every_rules_sentence_is_understood_as_that_rule(compiler):
    for rule in compiler.book.rules:
        assert compiler.rule_for(rule.sentence.lower()) is rule, rule.sentence


def test_every_rule_measuring_a_length_has_a_default_one(compiler):
    for rule in compiler.book.rules:
        if RuleValue.LENGTH in rule.parameters.values():
            assert rule.default_length is not None, rule.monitor_type


# %% compiling


def test_a_sentence_no_rule_matches_compiles_to_nothing(compiler):
    compiled = compiler.compile(attached("Sing while working", step_object="milk"))
    assert compiled.monitor_type is None
    assert compiled.monitor is None and compiled.switch is None


def test_a_constraint_not_attached_yet_only_names_its_monitor(compiler):
    compiled = compiler.compile(ConstraintText(text="Milk must stay upright"))
    assert compiled.monitor_type is ConstraintMonitorType.VECTORS_ALIGNED
    assert compiled.monitor is None


def test_the_object_a_sentence_names_is_its_subject(compiler):
    compiled = compiler.compile(
        attached("Keep the milk upright", step_object="cup", objects=["cup", "milk"])
    )
    assert compiled.monitor.parameters[MonitorParameterKey.TIP_LINK] == "milk"


def test_without_a_named_object_the_steps_object_is_the_subject(compiler):
    compiled = compiler.compile(attached("Do not tilt it", step_object="cup"))
    assert compiled.monitor.parameters[MonitorParameterKey.TIP_LINK] == "cup"


def test_an_identity_of_several_words_is_named_by_its_words(compiler):
    compiled = compiler.compile(
        attached("Keep the milk box level", objects=["milk_box", "cup"])
    )
    assert compiled.monitor.parameters[MonitorParameterKey.TIP_LINK] == "milk_box"


@pytest.mark.parametrize(
    ("text", "metres"),
    [
        ("Keep the milk above the table by 10 cm", 0.1),
        ("Keep the milk 250 mm higher", 0.25),
        ("Keep the milk 1.5 metres above the floor", 1.5),
    ],
)
def test_a_length_in_the_sentence_sets_the_limit(compiler, text, metres):
    compiled = compiler.compile(attached(text, objects=["milk"]))
    assert compiled.monitor.monitor_type is ConstraintMonitorType.HEIGHT
    assert compiled.monitor.parameters[
        MonitorParameterKey.LOWER_LIMIT
    ] == pytest.approx(metres)


def test_without_a_length_the_rule_default_applies(compiler):
    compiled = compiler.compile(attached("Keep the milk below", objects=["milk"]))
    rule = compiler.rule_for("keep the milk below")
    assert compiled.monitor.parameters[MonitorParameterKey.UPPER_LIMIT] == (
        rule.default_length
    )


def test_a_distance_is_kept_from_the_second_named_object(compiler):
    compiled = compiler.compile(
        attached(
            "Keep the milk 20 cm away from the cup",
            step_object="cup",
            objects=["cup", "milk"],
        )
    )
    parameters = compiled.monitor.parameters
    assert compiled.monitor.monitor_type is ConstraintMonitorType.DISTANCE
    assert parameters[MonitorParameterKey.TIP_LINK] == "milk"
    assert parameters[MonitorParameterKey.ROOT_LINK] == "cup"
    assert parameters[MonitorParameterKey.LOWER_LIMIT] == pytest.approx(0.2)


def test_a_distance_from_nothing_named_is_refused(compiler):
    with pytest.raises(ConstraintReferenceMissing):
        compiler.compile(attached("Keep away from it", step_object="milk"))


def test_an_attached_constraint_about_no_object_is_refused(compiler):
    with pytest.raises(ConstraintSubjectMissing):
        compiler.compile(attached("Stay upright", step_kind=StepKind.NAVIGATE))


def test_looking_turns_on_the_transports_own_switch(compiler):
    compiled = compiler.compile(
        attached("Look where it operates", step_kind=StepKind.TRANSPORT)
    )
    assert compiled.switch is StepSwitch.LOOK_AT_OPERATION_SITE
    assert compiled.monitor is None


def test_looking_on_a_step_without_the_switch_changes_nothing(compiler):
    compiled = compiler.compile(
        attached("Look where it operates", step_kind=StepKind.NAVIGATE)
    )
    assert compiled.monitor_type is ConstraintMonitorType.POINTING_AT
    assert compiled.switch is None and compiled.monitor is None


def test_objects_are_ordered_by_where_the_sentence_names_them():
    named = NamedObjects("put the cup next to the milk", ["milk", "cup", "bowl"])
    assert named.in_order() == ["cup", "milk"]
