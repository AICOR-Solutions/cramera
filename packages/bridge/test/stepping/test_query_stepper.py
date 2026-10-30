"""
Publishing a task's queries as steps and holding its thread at them, with queries over
plain objects, so no world is built.
"""

from __future__ import annotations

import inspect
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from typing_extensions import Any, Iterable, List, Tuple

from cramera_bridge import query_stepping
from cramera_bridge.live.query_steps import HeldQueries, QueryStepBoard
from cramera_bridge.query_stepping import (
    ANSWER_LENGTH,
    QueryStepper,
    SteppedBackend,
    package_directories,
)
from cramera_protocol.query_steps import QueryStep, StepMoment, StepPhase
from cramera_protocol.resolutions import SceneHighlight
from krrood.entity_query_language.backends import (
    EntityQueryLanguageBackend,
    QueryBackend,
)
from krrood.entity_query_language.evaluable import Evaluable
from krrood.entity_query_language.factories import an, entity, the, variable
from krrood.entity_query_language.verbalization.vocabulary.english import Directive
from semantic_digital_twin.datastructures.prefixed_name import PrefixedName
from semantic_digital_twin.semantic_annotations.semantic_annotations import Handle
from semantic_digital_twin.world_description.world_entity import Body

TASK = "carrying cups"
"""
What the stepped task does.
"""

WAIT_SECONDS = 10.0
"""
How long a test waits for a thread, in seconds.
"""

# %% stand-ins


@dataclass
class Cup:
    """
    Something a query finds.
    """

    name: str
    """
    The cup's name.
    """


CUPS = [Cup("red"), Cup("blue")]
"""
The cups the queries range over.
"""


@dataclass
class HighlightingBoard:
    """
    Stands in for the live publisher: keeps the published steps and remembers what each
    answer would light up.
    """

    query_steps: QueryStepBoard = field(default_factory=QueryStepBoard)
    """
    The published steps.
    """

    highlighted: List[List[Any]] = field(default_factory=list)
    """
    The answers each highlight was asked for, in order.
    """

    def scene_highlight(
        self, about: Iterable[Any], framed: Iterable[Any] = ()
    ) -> SceneHighlight:
        self.highlighted.append(list(about))
        return SceneHighlight()


@dataclass
class FailingBackend(QueryBackend):
    """
    Gives one answer and then fails.
    """

    def evaluate(self, expression: Evaluable) -> Iterable[Any]:
        yield CUPS[0]
        raise ValueError("the backend failed")


@dataclass
class GeneratingBackend(EntityQueryLanguageBackend):
    """
    Answers as the in-process backend does, but says it generates its answers.
    """

    opening_directive = Directive.GENERATE


def stepper(stepping: bool = False) -> QueryStepper:
    """
    :param stepping: Whether the run is held at its queries.
    :return: A stepper publishing to a stand-in board.
    """
    return QueryStepper(
        publisher=HighlightingBoard(),
        task=TASK,
        control=HeldQueries(stepping=stepping),
    )


def the_red_cup() -> Cup:
    """
    :return: The red cup, found by a query asked here.
    """
    cup = variable(Cup, CUPS)
    return the(entity(cup).where(cup.name == "red")).first()


def every_cup() -> List[Cup]:
    """
    :return: Every cup, found by a query asked here.
    """
    return an(entity(variable(Cup, CUPS))).tolist()


def every_cup_from(backend: QueryBackend) -> List[Cup]:
    """
    :param backend: The backend answering.
    :return: Every cup it answers with, found by a query asked here.
    """
    return an(entity(variable(Cup, CUPS))).tolist(backend=backend)


def held_moments(stepped: QueryStepper, ask) -> Tuple[List[tuple], List[Any]]:
    """
    Ask on a thread of its own while stepping, and move the thread on from each step it
    is held at.

    :param stepped: The stepper, holding at every query.
    :param ask: Asks the queries.
    :return: The steps the thread was held at, as numbers and moments, and what the
        thread's asking returned or raised.
    """
    outcome: List[Any] = []

    def run() -> None:
        with stepped.watching():
            outcome.append(ask())

    thread = threading.Thread(target=run)
    thread.start()
    held = []
    deadline = time.monotonic() + WAIT_SECONDS
    while thread.is_alive() and time.monotonic() < deadline:
        step = stepped.control.held
        if step is None:
            time.sleep(0.01)
            continue
        held.append((step.number, step.moment))
        stepped.control.advance(step)
    thread.join(timeout=WAIT_SECONDS)
    return held, outcome


# %% stepping


def test_a_query_asked_while_watching_is_published_as_a_step():
    stepped = stepper()
    with stepped.watching():
        cup = the_red_cup()
    (step,) = stepped.publisher.query_steps.current().steps
    line = inspect.getsourcelines(the_red_cup)[1] + 5
    assert cup == CUPS[0]
    assert step.number == 0 and step.depth == 0 and step.asker is None
    assert step.moment is StepMoment.ANSWERED
    assert step.phase is StepPhase.SETUP
    assert step.during == TASK
    assert step.answers == [str(CUPS[0])]
    assert step.caller.function == "the_red_cup"
    assert step.caller.module == "test_query_stepper"
    assert step.caller.line == line
    assert step.code.focus_first_line == line
    assert step.backend.name == EntityQueryLanguageBackend.__name__
    assert not step.generates
    assert stepped.publisher.highlighted[-1] == [CUPS[0]]


def test_the_steps_follow_the_phase_the_run_is_in():
    stepped = stepper()
    with stepped.watching():
        the_red_cup()
        stepped.phase = StepPhase.EXECUTION
        every_cup()
    phases = [step.phase for step in stepped.steps]
    assert phases == [StepPhase.SETUP, StepPhase.EXECUTION]
    assert stepped.steps[1].answers == [str(cup) for cup in CUPS]


def test_watching_ends_with_the_run_held_nowhere():
    stepped = stepper(stepping=True)
    original = Evaluable.evaluate
    with stepped.watching():
        patched = Evaluable.evaluate
    the_red_cup()
    assert patched is not original
    assert Evaluable.evaluate is original
    assert stepped.steps == []
    assert not stepped.control.stepping
    assert stepped.thread is None


def test_a_query_asked_on_another_thread_is_answered_without_a_step():
    stepped = stepper(stepping=True)
    found = []
    with stepped.watching():
        thread = threading.Thread(target=lambda: found.append(the_red_cup()))
        thread.start()
        thread.join(timeout=WAIT_SECONDS)
        backend = stepped.resolving(EntityQueryLanguageBackend())
        thread = threading.Thread(
            target=lambda: found.extend(
                backend.evaluate(an(entity(variable(Cup, CUPS))))
            )
        )
        thread.start()
        thread.join(timeout=WAIT_SECONDS)
    assert found == [CUPS[0], *CUPS]
    assert stepped.steps == []


def test_queries_the_cram_workspace_asks_are_answered_without_a_step(monkeypatch):
    here = str(Path(__file__).parent) + os.sep
    monkeypatch.setattr(query_stepping, "CRAM_FILES", (here,))
    stepped = stepper()
    with stepped.watching():
        cup = the_red_cup()
    assert cup == CUPS[0]
    assert stepped.steps == []


def test_a_plans_open_parts_are_stepped_wherever_they_are_grounded(monkeypatch):
    here = str(Path(__file__).parent) + os.sep
    monkeypatch.setattr(query_stepping, "CRAM_FILES", (here,))
    stepped = stepper()
    backend = stepped.resolving(GeneratingBackend())
    with stepped.watching():
        cup = variable(Cup, CUPS)
        found = the(entity(cup).where(cup.name == "blue")).first(backend=backend)
    (step,) = stepped.steps
    assert isinstance(backend, SteppedBackend) and backend.resolves
    assert found == CUPS[1]
    assert step.phase is StepPhase.RESOLUTION
    assert step.generates
    assert step.backend.name == GeneratingBackend.__name__


# %% holding


def test_a_held_query_waits_at_its_question_and_at_its_answers():
    stepped = stepper(stepping=True)
    held, outcome = held_moments(stepped, lambda: (the_red_cup(), every_cup()))
    assert held == [
        (0, StepMoment.ASKED),
        (0, StepMoment.ANSWERED),
        (1, StepMoment.ASKED),
        (1, StepMoment.ANSWERED),
    ]
    assert outcome == [(CUPS[0], CUPS)]


def test_an_answering_cut_short_by_an_error_is_not_held_at_its_answers():
    stepped = stepper(stepping=True)
    backend = FailingBackend()

    def ask() -> bool:
        with pytest.raises(ValueError):
            every_cup_from(backend)
        return True

    held, outcome = held_moments(stepped, ask)
    (step,) = stepped.steps
    assert held == [(0, StepMoment.ASKED)]
    assert outcome == [True]
    assert step.moment is StepMoment.ANSWERED
    assert step.answers == [str(CUPS[0])]
    assert stepped.publisher.query_steps.current().steps[0] == step


def test_each_answer_is_published_as_it_is_given():
    stepped = stepper()
    published: List[QueryStep] = []
    board = stepped.publisher.query_steps
    publish = board.publish

    def remember(steps, control=None) -> None:
        published.append(steps.steps[-1] if steps.steps else None)
        publish(steps, control)

    board.publish = remember
    with stepped.watching():
        every_cup()
    answered = [
        (step.moment, len(step.answers)) for step in published if step is not None
    ]
    assert (StepMoment.ASKED, 1) in answered
    assert (StepMoment.ASKED, 2) in answered
    assert answered[-1] == (StepMoment.ANSWERED, 2)


# %% describing


def test_an_answer_is_worded_by_its_name():
    body = Body(name=PrefixedName("cup"))
    assert QueryStepper.word(body) == "cup"
    assert QueryStepper.word(Handle(root=body)) == "Handle · cup"
    assert QueryStepper.word(CUPS[0]) == str(CUPS[0])


def test_a_long_answer_is_cut_short():
    word = QueryStepper.word("x" * (2 * ANSWER_LENGTH))
    assert len(word) == ANSWER_LENGTH
    assert word.endswith("…")


def test_code_that_cannot_be_read_has_no_excerpt():
    frame = inspect.Traceback(
        filename="/no/such/file.py",
        lineno=12,
        function="f",
        code_context=None,
        index=None,
    )
    assert QueryStepper.excerpt(frame) is None
    assert QueryStepper.call_site(frame).module == "file"


def test_a_package_that_is_not_installed_has_no_directory():
    assert package_directories(["no_such_package_of_cramera"]) == ()
    assert all(
        directory.endswith(os.sep) for directory in package_directories(["krrood"])
    )
