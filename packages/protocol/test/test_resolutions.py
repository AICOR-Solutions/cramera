"""
The documents saying how a running plan's open parts were resolved.
"""

from __future__ import annotations

import pytest

from cramera_protocol.exceptions import InvalidDocumentValue
from cramera_protocol.geometry import Pose
from cramera_protocol.resolutions import (
    ContactReasoning,
    ExecutionRequest,
    KnowledgeSource,
    PerceptionReasoning,
    PlanResolutions,
    PlanResolutionsKey,
    PlanResolutionKey,
    Reasoning,
    ReasoningKey,
    ResolutionPresentation,
    ResolvedPartKey,
    RuleReasoning,
    SamplingReasoning,
    SceneHighlight,
)

# %% round trips


@pytest.mark.parametrize(
    "document_class, relative_path",
    [
        (PlanResolutions, "live/resolutions.json"),
        (ExecutionRequest, "live/execution_request.json"),
    ],
)
def test_resolution_documents_round_trip(read_json, document_class, relative_path):
    document = document_class.from_json(read_json(relative_path))
    assert document_class.from_json(document.to_json()) == document


# %% reasoning


def test_each_part_reads_the_reasoning_of_the_source_it_names(read_json):
    resolutions = PlanResolutions.from_json(read_json("live/resolutions.json"))
    reasoning = [part.reasoning for part in resolutions.resolutions[0].parts]
    assert [type(each) for each in reasoning] == [
        PerceptionReasoning,
        ContactReasoning,
        SamplingReasoning,
        RuleReasoning,
    ]


@pytest.mark.parametrize(
    "reasoning",
    [
        PerceptionReasoning(),
        ContactReasoning(),
        RuleReasoning(case="cylinder_1", case_kind="Cylinder"),
        SamplingReasoning(subject="cylinder_1"),
    ],
)
def test_reasoning_reads_back_as_the_kind_it_was_written_as(reasoning):
    assert Reasoning.from_json(reasoning.to_json()) == reasoning


def test_every_knowledge_source_has_its_reasoning():
    assert {kind.source() for kind in Reasoning.__subclasses__()} == set(
        KnowledgeSource
    )


def test_reasoning_of_an_unknown_source_is_refused():
    with pytest.raises(InvalidDocumentValue):
        Reasoning.from_json({ReasoningKey.SOURCE.value: "intuition"})


def test_reasoning_that_is_no_object_is_refused():
    with pytest.raises(InvalidDocumentValue):
        Reasoning.from_json(["perception"])


# %% parts and resolutions


def test_a_part_reads_the_regions_it_outlines(read_json):
    data = read_json("live/resolutions.json")
    part = PlanResolutions.from_json(data).resolutions[0].parts[3]
    outline = data[PlanResolutionsKey.RESOLUTIONS][0][PlanResolutionKey.PARTS][3][
        ResolvedPartKey.HIGHLIGHT
    ]["regions"][0]
    assert part.highlight.regions[0].pose == Pose.from_json(outline["pose"])


def test_a_part_without_a_highlight_lights_nothing(read_json):
    resolutions = PlanResolutions.from_json(read_json("live/resolutions.json"))
    assert resolutions.resolutions[0].parts[1].highlight == SceneHighlight()


def test_resolutions_without_a_presentation_take_the_default_one():
    assert PlanResolutions.from_json({}).presentation == ResolutionPresentation()
