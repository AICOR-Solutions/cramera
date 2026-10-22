"""
The centrifuge's operating knowledge as the laboratory reports it.
"""

from __future__ import annotations

from cramera_protocol.browser import BROWSER_ENUMERATIONS
from cramera_protocol.laboratory.knowledge import (
    EvaluationKey,
    KnowledgeKey,
    ManualEdition,
    OperatingKnowledge,
    OperatingRule,
    RequirementKey,
    StartRequirementName,
)

# %% knowledge


def knowledge_of(read_json) -> dict:
    """
    :param read_json: Reads a dataset file.
    :return: The centrifuge knowledge fixture.
    """
    return read_json("laboratory/knowledge.json")


def test_the_knowledge_reads_its_manual_history_and_evaluation(read_json):
    data = knowledge_of(read_json)
    knowledge = OperatingKnowledge.from_json(data)
    latest = knowledge.history[-1]
    assert knowledge.revision == latest.revision == data[KnowledgeKey.REVISION]
    assert latest.changes[0].rule is OperatingRule.MINIMUM_SAMPLES
    assert knowledge.history[0].simulation_time is None
    assert knowledge.history[0].changes == []
    assert knowledge.manual.citation.line == latest.changes[0].citation.line


def test_a_requirement_keeps_a_count_or_a_truth_value(read_json):
    data = knowledge_of(read_json)
    count, lid = OperatingKnowledge.from_json(data).evaluation.requirements
    written = data[KnowledgeKey.EVALUATION][EvaluationKey.REQUIREMENTS]
    assert count.name is StartRequirementName.MINIMUM_SAMPLES
    assert count.actual == written[0][RequirementKey.ACTUAL]
    assert lid.actual is False and lid.required is True
    assert lid.citation is None


def test_the_knowledge_round_trips(read_json):
    data = knowledge_of(read_json)
    assert OperatingKnowledge.from_json(data).to_json() == data


def test_the_browser_reads_the_knowledge_keys():
    assert {ManualEdition, KnowledgeKey, RequirementKey} <= set(BROWSER_ENUMERATIONS)
