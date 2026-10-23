"""
The documents questions are asked and answered with.
"""

from __future__ import annotations

import pytest

from cramera_protocol.bundle.statecharts import Statecharts
from cramera_protocol.exceptions import (
    InvalidDocumentValue,
    UnsupportedProtocolVersion,
)
from cramera_protocol.questions import (
    AnswerColumn,
    AnswerKind,
    GraphLayout,
    GraphView,
    GraphViewName,
    Members,
    PresetCatalog,
    QueryAnswer,
    QueryAnswerKey,
    QueryRequest,
    QueryScope,
    QuestionMatch,
    RecordedAnswers,
    ReplayWindow,
    Vocabulary,
    VocabularyKind,
)

# %% round trips


@pytest.mark.parametrize(
    "document_class, relative_path",
    [
        (QueryRequest, "questions/query_request.json"),
        (QueryAnswer, "questions/query_answer.json"),
        (QueryAnswer, "questions/failed_query_answer.json"),
        (QueryAnswer, "questions/event_answer.json"),
        (PresetCatalog, "questions/preset_catalog.json"),
        (QuestionMatch, "questions/question_match.json"),
        (QuestionMatch, "questions/unmatched_question.json"),
        (Vocabulary, "questions/vocabulary.json"),
        (Members, "questions/members.json"),
        (GraphView, "questions/plan_graph.json"),
        (GraphView, "questions/chart_graph.json"),
        (RecordedAnswers, "questions/recorded_answers.json"),
    ],
)
def test_question_documents_round_trip(read_json, document_class, relative_path):
    document = document_class.from_json(read_json(relative_path))
    assert document_class.from_json(document.to_json()) == document


# %% answers


def test_an_answer_keeps_its_reserved_columns(read_json):
    answer = QueryAnswer.from_json(read_json("questions/query_answer.json"))
    assert answer.kind is AnswerKind.ENTITIES
    assert AnswerColumn.ENTITY in answer.rows[0]
    assert answer.replay == [None]


def test_an_answer_reads_replay_windows(read_json):
    data = read_json("questions/event_answer.json")
    answer = QueryAnswer.from_json(data)
    assert answer.replay[0] == ReplayWindow.from_json(data[QueryAnswerKey.REPLAY][0])


def test_a_failed_answer_has_no_rows(read_json):
    answer = QueryAnswer.from_json(read_json("questions/failed_query_answer.json"))
    assert answer.ok is False
    assert answer.rows == []


def test_a_query_defaults_to_the_current_state():
    assert QueryRequest(code="x").scope is QueryScope.CURRENT_STATE


def test_an_unknown_scope_is_refused():
    with pytest.raises(InvalidDocumentValue):
        QueryRequest.from_json({"code": "x", "scope": "dreams"})


def test_presets_and_vocabulary_read_their_enumerations(read_json):
    catalog = PresetCatalog.from_json(read_json("questions/preset_catalog.json"))
    vocabulary = Vocabulary.from_json(read_json("questions/vocabulary.json"))
    assert catalog.presets[1].scope is QueryScope.DETECTED_EVENTS
    assert catalog.scopes[0].name is QueryScope.CURRENT_STATE
    assert [entry.kind for entry in vocabulary.entries] == [
        VocabularyKind.VARIABLE,
        VocabularyKind.FACTORY,
    ]


# %% graph


def test_a_graph_node_keeps_keys_a_view_added(read_json):
    view = GraphView.from_json(read_json("questions/plan_graph.json"))
    assert view.view is GraphViewName.PLAN
    assert view.layout is GraphLayout.HIERARCHY
    assert view.nodes[0].extensions == {"target": "milk"}


def test_the_statechart_view_carries_the_recorded_statecharts(read_json):
    view = GraphView.from_json(read_json("questions/chart_graph.json"))
    assert isinstance(view.recorded, Statecharts)
    assert view.recorded.frames == [0, -1]


# %% recorded answers


def test_recorded_answers_are_found_by_query_and_scope(read_json):
    data = read_json("questions/recorded_answers.json")
    recorded = RecordedAnswers.from_json(data)
    [first] = recorded.answers
    assert recorded.answer_to(first.code, first.scope) == first.answer
    assert recorded.answer_to(first.code, QueryScope.DETECTED_EVENTS) is None


def test_recorded_graphs_are_found_by_view(read_json):
    recorded = RecordedAnswers.from_json(read_json("questions/recorded_answers.json"))
    assert recorded.graph(GraphViewName.PLAN) == recorded.graphs[0]
    assert recorded.graph(GraphViewName.KINEMATICS) is None


def test_recorded_answers_of_another_major_version_are_refused(read_json):
    with pytest.raises(UnsupportedProtocolVersion):
        RecordedAnswers.from_json(
            read_json("questions/recorded_answers_from_next_major_version.json")
        )
