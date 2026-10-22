"""
Reading centrifuge manuals and evaluating whether the centrifuge may start.
"""

from __future__ import annotations

import pytest

from cramera_laboratory.exceptions import InvalidManual, ManualProblem
from cramera_laboratory.knowledge import (
    HISTORY_LIMIT,
    CentrifugeManual,
    CentrifugeObservation,
    ManualKnowledge,
    ManualSyntax,
    NextStep,
)
from cramera_protocol.laboratory.knowledge import (
    ManualEdition,
    OperatingRule,
    StartRequirementName,
)

from .conftest import DATASET

MANUALS = DATASET / "manuals"
"""
The test manuals.
"""

READY = CentrifugeObservation(
    secured_samples=2, balanced=True, lid_closed=True, stopped=True
)
"""
A centrifuge with one balanced pair, closed and still.
"""

SIMULATION_TIME = 3.5
"""
When a manual is read in the tests, in simulated seconds.
"""


def manual_text(name: str) -> str:
    """
    :param name: A test manual's file name.
    :return: Its text.
    """
    return (MANUALS / name).read_text(encoding="utf-8")


# %% reading


@pytest.mark.parametrize(
    "edition, samples", [(ManualEdition.FIRST, 2), (ManualEdition.SECOND, 4)]
)
def test_the_shipped_editions_state_their_minimum(edition, samples):
    manual = CentrifugeManual.shipped(edition)
    assert manual.minimum_samples == samples
    assert manual.citation.section == ManualSyntax.RULE_SECTION
    assert (
        manual.citation.quote == manual.document.splitlines()[manual.citation.line - 1]
    )


def test_a_german_manual_is_read():
    manual = CentrifugeManual.of_text(manual_text("german.md"))
    assert manual.minimum_samples == 4 and manual.version == "1.1"


def test_the_digest_identifies_the_exact_text():
    first = CentrifugeManual.shipped(ManualEdition.FIRST)
    again = CentrifugeManual.of_text(first.document)
    changed = CentrifugeManual.of_text(first.document + "\n")
    assert again.digest == first.digest != changed.digest


@pytest.mark.parametrize(
    "name, problem",
    [
        ("without_title.md", ManualProblem.TITLE),
        ("two_versions.md", ManualProblem.VERSION),
        ("without_rules.md", ManualProblem.RULE_SECTION),
        ("header_twice.md", ManualProblem.HEADER),
        ("separator_first.md", ManualProblem.SEPARATOR),
        ("three_samples.md", ManualProblem.UNSUPPORTED_RULE),
        ("rule_twice.md", ManualProblem.RULE_COUNT),
        ("empty_table.md", ManualProblem.RULE_COUNT),
        ("too_long.md", ManualProblem.TOO_LONG),
    ],
)
def test_a_malformed_manual_is_refused_with_its_problem(name, problem):
    with pytest.raises(InvalidManual) as refused:
        CentrifugeManual.of_text(manual_text(name))
    assert refused.value.problem is problem


def test_an_empty_text_is_refused():
    with pytest.raises(InvalidManual):
        CentrifugeManual.of_text("")


# %% knowledge


def test_reading_another_edition_records_the_rule_change():
    knowledge = ManualKnowledge()
    second = CentrifugeManual.shipped(ManualEdition.SECOND)
    knowledge.read(second, SIMULATION_TIME)
    latest = knowledge.history[-1]
    assert knowledge.revision == latest.revision == 2
    [change] = latest.changes
    assert change.rule is OperatingRule.MINIMUM_SAMPLES
    assert (change.before, change.after) == (2, second.minimum_samples)
    assert latest.simulation_time == SIMULATION_TIME


def test_reading_the_same_text_again_changes_nothing():
    knowledge = ManualKnowledge()
    knowledge.read(CentrifugeManual.shipped(ManualEdition.FIRST), SIMULATION_TIME)
    assert knowledge.revision == 1 and len(knowledge.history) == 1


def test_the_history_keeps_the_latest_revisions():
    knowledge = ManualKnowledge()
    editions = [CentrifugeManual.shipped(edition) for edition in ManualEdition]
    for revision in range(HISTORY_LIMIT + 3):
        knowledge.read(editions[(revision + 1) % 2], SIMULATION_TIME)
    assert len(knowledge.history) == HISTORY_LIMIT
    assert knowledge.history[-1].revision == knowledge.revision


def test_a_ready_centrifuge_may_start():
    evaluation = ManualKnowledge().evaluate(READY)
    assert evaluation.allowed
    assert evaluation.next_steps == [NextStep.START.value]


def test_a_missing_pair_under_the_second_edition_is_explained():
    knowledge = ManualKnowledge()
    knowledge.read(CentrifugeManual.shipped(ManualEdition.SECOND), SIMULATION_TIME)
    evaluation = knowledge.evaluate(READY)
    samples = {
        requirement.name: requirement for requirement in evaluation.requirements
    }[StartRequirementName.MINIMUM_SAMPLES]
    assert not evaluation.allowed and samples.satisfied is False
    assert samples.citation == knowledge.active.citation
    assert evaluation.next_steps == [
        NextStep.LOAD.value.format(missing=2),
        NextStep.OPEN_FOR_LOADING.value,
    ]


def test_a_turning_unbalanced_open_rotor_lists_every_step():
    observation = CentrifugeObservation(
        secured_samples=2, balanced=False, lid_closed=False, stopped=False
    )
    steps = ManualKnowledge().evaluate(observation).next_steps
    assert steps == [NextStep.STOP.value, NextStep.BALANCE.value, NextStep.CLOSE.value]


def test_the_knowledge_document_names_the_manual():
    knowledge = ManualKnowledge()
    document = knowledge.document(READY)
    assert document.manual.digest == knowledge.active.digest
    assert document.history == list(knowledge.history)
