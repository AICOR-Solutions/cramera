"""
Stepping through the queries a robot task asks: each query of the task's own is
published as a query step, and the run is held at it until the viewer's **Next** moves
it on.

A query is the task's own when it is asked on the run's thread by code outside the CRAM
workspace, such as a demo finding its robot, or when it grounds a part the task's plan
leaves open. The queries CRAM's packages ask for their own purposes, such as a robot
part finding its robot or the world reasoner's rules, are answered without a step.
"""

from __future__ import annotations

import copy
import importlib.util
import inspect
import linecache
import os
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import FrameType

from typing_extensions import Any, Iterable, Iterator, List, Optional, Tuple

from coraplex.plans.plan import Plan
from coraplex.plans.plan_callbacks import PlanCallback
from coraplex.plans.plan_node import ActionNode, PlanNode
from coraplex.plans.underspecified import UnderspecifiedNode
from cramera_bridge.live.plan import DesignatorSummary
from cramera_bridge.live.publisher import LivePublisher
from cramera_bridge.live.world_model import ObjectKey
from cramera_bridge.live.query_steps import HeldQueries
from cramera_bridge.questions.verbalization import QueryVerbalizer
from cramera_protocol.query_steps import (
    CallSite,
    HeldStep,
    QueryStep,
    QuerySteps,
    SourceExcerpt,
    StepMoment,
    StepPhase,
)
from cramera_protocol.designator_roles import RoleEntity
from cramera_protocol.resolutions import BackendDescription, KnowledgeSource
from krrood.entity_query_language.backends import (
    EntityQueryLanguageBackend,
    QueryBackend,
)
from krrood.entity_query_language.evaluable import Evaluable
from krrood.entity_query_language.verbalization.vocabulary.english import Directive
from semantic_digital_twin.semantic_annotations.mixins import (
    HasRootKinematicStructureEntity,
)
from semantic_digital_twin.world_description.world_entity import (
    Body,
    SemanticAnnotation,
    WorldEntity,
)

EXCERPT_CONTEXT = 4
"""
How many lines around the asking line a step's code shows.
"""

HIGHLIGHTED_ANSWERS = 12
"""
How many answers of one query the scene lights up.
"""

ANSWER_LENGTH = 120
"""
The longest an answer is written, in characters.
"""

# %% where a query is asked


class CramPackage(StrEnum):
    """
    The packages of the CRAM workspace, whose own queries are no steps of a task.
    """

    CORAPLEX = "coraplex"
    """
    Plans, actions and motions.
    """

    SEMANTIC_DIGITAL_TWIN = "semantic_digital_twin"
    """
    Worlds, bodies and their annotations.
    """

    GISKARDPY = "giskardpy"
    """
    Motion statecharts.
    """

    KRROOD = "krrood"
    """
    The entity query language.
    """

    SEGMIND = "segmind"
    """
    Event detection.
    """

    ROBOKUDO = "robokudo"
    """
    Perception.
    """

    PHYSICS_SIMULATORS = "physics_simulators"
    """
    Physics simulation.
    """

    PROBABILISTIC_MODEL = "probabilistic_model"
    """
    Probabilistic models.
    """

    RANDOM_EVENTS = "random_events"
    """
    Random events.
    """


def package_directories(packages: Iterable[str]) -> Tuple[str, ...]:
    """
    :param packages: Names of top-level packages.
    :return: The directories of those that are installed, each ending in a separator,
        so a file's path starts with one exactly when the file belongs to its package.
    """
    specifications = [importlib.util.find_spec(package) for package in packages]
    return tuple(
        str(Path(location)) + os.sep
        for specification in specifications
        if specification is not None
        for location in specification.submodule_search_locations or ()
    )


STEPPING_FILE = __file__
"""
This module, whose frames answer a query rather than ask one.
"""

ANSWERING_FILES = package_directories([CramPackage.KRROOD]) + (
    contextmanager.__code__.co_filename,
)
"""
The files whose frames evaluate a query rather than ask it: krrood's own and contextlib.
"""

CRAM_FILES = package_directories(CramPackage)
"""
The files of the CRAM workspace, whose queries are no steps of a task.
"""


def first_frame_outside(
    frame: Optional[FrameType], files: Tuple[str, ...]
) -> Optional[FrameType]:
    """
    :param frame: A frame of a thread's stack.
    :param files: The files whose frames are passed over.
    :return: The frame or the innermost of its callers whose file is none of
        ``files``, or None where every frame's is.
    """
    while frame is not None and frame.f_code.co_filename.startswith(files):
        frame = frame.f_back
    return frame


# %% stepping


@dataclass
class SteppedBackend(QueryBackend):
    """
    Answers with another backend while the stepper publishes and holds each query asked
    on the run's thread.
    """

    inner: QueryBackend = field(kw_only=True)
    """
    The backend answering the queries.
    """

    stepper: QueryStepper = field(kw_only=True)
    """
    Publishes the queries and holds the run at them.
    """

    resolves: bool = field(kw_only=True, default=False)
    """
    Whether it answers the parts a plan leaves open, each a query of the task's own.
    """

    def evaluate(self, expression: Evaluable) -> Iterable[Any]:
        if threading.current_thread() is not self.stepper.thread:
            return self.inner.evaluate(expression)
        return self.stepper.answer(expression, self.inner, self.resolves)


@dataclass
class QueryStepper:
    """
    Publishes each query a task asks of its own on one thread as a query step and holds
    the thread at it, while :meth:`watching`.
    """

    publisher: LivePublisher
    """
    The live publisher the steps are published through.
    """

    task: str
    """
    What the task does, said of the queries asked while no action is under way.
    """

    control: HeldQueries = field(default_factory=HeldQueries)
    """
    Holds the run at its queries.
    """

    phase: StepPhase = StepPhase.SETUP
    """
    What the run is doing.
    """

    plans: List[Plan] = field(default_factory=list)
    """
    The plans whose progress the stepper follows.
    """

    running: List[PlanNode] = field(default_factory=list)
    """
    The plan nodes under way, in the order they started.
    """

    steps: List[QueryStep] = field(default_factory=list)
    """
    Every query asked so far.
    """

    asking: List[int] = field(default_factory=list)
    """
    The numbers of the queries being answered, outermost first.
    """

    verbalizer: QueryVerbalizer = field(default_factory=QueryVerbalizer)
    """
    Reads the queries back as English.
    """

    thread: Optional[threading.Thread] = None
    """
    The thread whose queries are stepped, while watching.
    """

    @contextmanager
    def watching(self) -> Iterator[None]:
        """
        Step each query of the task's own asked on this thread until the block ends,
        whichever backend answers it.
        """
        original = Evaluable.evaluate
        stepper = self

        def evaluate(expression: Evaluable, backend: Optional[QueryBackend] = None):
            if isinstance(backend, SteppedBackend) or not stepper.owns(
                sys._getframe(1)
            ):
                return original(expression, backend)
            return original(
                expression,
                SteppedBackend(
                    inner=backend or EntityQueryLanguageBackend(), stepper=stepper
                ),
            )

        self.thread = threading.current_thread()
        Evaluable.evaluate = evaluate
        self.publish()
        try:
            yield
        finally:
            Evaluable.evaluate = original
            self.thread = None
            self.control.release()
            self.publish()

    def owns(self, caller: Optional[FrameType]) -> bool:
        """
        :param caller: The frame that evaluates a query.
        :return: Whether the query is the task's own: asked on the watched thread by
            code outside the CRAM workspace, and not evaluated by krrood within
            answering another query.
        """
        if threading.current_thread() is not self.thread:
            return False
        frame = first_frame_outside(caller, ANSWERING_FILES)
        return frame is not None and not frame.f_code.co_filename.startswith(
            CRAM_FILES + (STEPPING_FILE,)
        )

    def resolving(self, inner: QueryBackend) -> QueryBackend:
        """
        :param inner: The backend a context answers its plans' open parts with.
        :return: The backend stepping through them.
        """
        return SteppedBackend(inner=inner, stepper=self, resolves=True)

    def progress(self, plan: Plan) -> PlanCallback:
        """
        :param plan: A plan about to be performed.
        :return: The plan callback that follows its nodes under way.
        """
        self.plans.append(plan)
        return ActionProgress(stepper=self, plan=plan)

    # %% answering

    def answer(
        self, expression: Evaluable, inner: QueryBackend, resolves: bool = False
    ) -> Iterator[Any]:
        """
        Publish the query, hold at it, answer it with the inner backend, publishing each
        answer as it is given, and hold at its answers once the answering ends: once
        every answer is given, or once the asker wants no further one, as a plan does
        when one of its candidates worked out.

        :param expression: The query.
        :param inner: The backend answering it.
        :param resolves: Whether it grounds a part a plan leaves open.
        :return: The answers, as the inner backend gives them.
        """
        step = self.ask(expression, inner, resolves)
        self.hold(step)
        started = time.perf_counter()
        answers = iter(inner.evaluate(expression))
        about = []
        ended = False
        try:
            while True:
                self.asking.append(step.number)
                try:
                    answer = next(answers)
                except StopIteration:
                    break
                finally:
                    self.asking.pop()
                step.answers.append(self.word(answer))
                if isinstance(answer, (Body, SemanticAnnotation)):
                    step.entities.append(self.entity(answer))
                about.append(answer)
                self.show(step, about, started)
                self.publish()
                ended = True
                yield answer
                ended = False
            ended = True
        finally:
            step.moment = StepMoment.ANSWERED
            self.show(step, about, started)
            if ended and threading.current_thread() is self.thread:
                self.hold(step)
            else:
                self.publish()

    def ask(
        self, expression: Evaluable, inner: QueryBackend, resolves: bool
    ) -> QueryStep:
        """
        :param expression: The query.
        :param inner: The backend answering it.
        :param resolves: Whether it grounds a part a plan leaves open.
        :return: Its new step, asked and not yet answered.
        """
        frame = first_frame_outside(
            sys._getframe(1), ANSWERING_FILES + (STEPPING_FILE,)
        )
        information = (
            None
            if frame is None
            else inspect.getframeinfo(frame, context=0)._replace(
                function=frame.f_code.co_qualname
            )
        )
        step = QueryStep(
            number=len(self.steps),
            asker=self.asking[-1] if self.asking else None,
            depth=len(self.asking),
            phase=StepPhase.RESOLUTION if resolves else self.phase,
            during=self.during(expression if resolves else None),
            moment=StepMoment.ASKED,
            question=self.verbalizer.verbalize(expression, inner),
            code=None if information is None else self.excerpt(information),
            caller=None if information is None else self.call_site(information),
            backend=BackendDescription(
                name=type(inner).__name__, source=KnowledgeSource.WORKING_MEMORY
            ),
            generates=inner.opening_directive is Directive.GENERATE,
            frame=self.publisher.recording.frame_count(),
            plan_node=self.running_action(),
        )
        self.steps.append(step)
        return step

    def show(self, step: QueryStep, about: List[Any], started: float) -> None:
        """
        Let a step show its answers so far: how long they took and what they light up.

        :param step: The step being answered.
        :param about: Its answers so far.
        :param started: When its answering started, by :func:`time.perf_counter`.
        """
        step.milliseconds = (time.perf_counter() - started) * 1000
        shown = about[:HIGHLIGHTED_ANSWERS]
        step.highlight = self.publisher.scene_highlight(shown, framed=shown)

    def hold(self, step: QueryStep) -> None:
        """
        Publish the steps and, while stepping, wait until the viewer moves on.

        :param step: The step the run reached.
        """
        self.control.hold(
            HeldStep(number=step.number, moment=step.moment), step.depth, self.publish
        )
        self.publish()

    def publish(self) -> None:
        """
        Publish every step so far and where the run is held.
        """
        control = self.control
        self.publisher.query_steps.publish(
            QuerySteps(
                stepping=control.stepping,
                holds_nested=control.holds_nested,
                held=control.held,
                steps=copy.deepcopy(self.steps),
            ),
            control,
        )

    # %% describing

    def entity(self, answer: Body | SemanticAnnotation) -> RoleEntity:
        """
        :param answer: An answer that is a body or an annotation of the world.
        :return: It as a designator's role names it, with the keys the scene lights up.
        """
        object_keys = {ObjectKey.of(body) for body in self.publisher.current_objects()}
        return DesignatorSummary.entity(answer, object_keys)

    def running_action(self) -> Optional[str]:
        """
        :return: The identity of the deepest action under way, as the recording's plan
            trees name it, or None while no plan runs.
        """
        running = self.publisher.plan.running()
        return None if running is None else running.identifier

    def during(self, open_part: Optional[Evaluable] = None) -> str:
        """
        Coraplex reports the start of motions and of the nodes it performs one by one,
        not of the actions it builds one motion statechart of, so an action is found
        among the ancestors of a node.

        :param open_part: The part a plan leaves open, while it is grounded.
        :return: The action under way: the innermost action enclosing the open part's
            node, else the one enclosing the plan node under way that started last; the
            task while no action is under way.
        """
        lines = [node.path for node in self.open_part_nodes(open_part)] + [
            [node, *node.path] for node in reversed(self.running)
        ]
        actions = [
            node for line in lines for node in line if isinstance(node, ActionNode)
        ]
        return type(actions[0].designator).__name__ if actions else self.task

    def open_part_nodes(self, open_part: Optional[Evaluable]) -> List[PlanNode]:
        """
        :param open_part: A part a plan leaves open, or None.
        :return: The nodes of the followed plans standing for it.
        """
        return [
            node
            for plan in self.plans
            for node in plan.nodes
            if isinstance(node, UnderspecifiedNode)
            and node.underspecified_action is open_part
        ]

    @staticmethod
    def word(answer: Any) -> str:
        """
        :param answer: One answer.
        :return: It in words: a world entity's name, with its root's where the name
            only repeats its kind; anything else as it prints.
        """
        text = str(answer)
        if isinstance(answer, WorldEntity):
            text = str(answer.name)
            if text == type(answer).__name__ and isinstance(
                answer, HasRootKinematicStructureEntity
            ):
                text = f"{text} · {answer.root.name}"
        return text if len(text) <= ANSWER_LENGTH else text[: ANSWER_LENGTH - 1] + "…"

    @staticmethod
    def excerpt(frame: inspect.FrameInfo) -> Optional[SourceExcerpt]:
        """
        :param frame: The frame asking a query.
        :return: The lines around the asking line, or None where they cannot be read.
        """
        first = max(1, frame.lineno - EXCERPT_CONTEXT)
        lines = [
            linecache.getline(frame.filename, number).rstrip("\n")
            for number in range(first, frame.lineno + EXCERPT_CONTEXT + 1)
        ]
        if not any(lines):
            return None
        return SourceExcerpt(
            file=frame.filename,
            function=frame.function,
            first_line=first,
            lines=lines,
            focus_first_line=frame.lineno,
            focus_last_line=frame.lineno,
        )

    @staticmethod
    def call_site(frame: inspect.FrameInfo) -> CallSite:
        """
        :param frame: The frame asking a query.
        :return: Where it asks.
        """
        module = inspect.getmodulename(frame.filename) or frame.filename
        return CallSite(function=frame.function, module=module, line=frame.lineno)


@dataclass
class ActionProgress(PlanCallback):
    """
    Tells the stepper which plan nodes are under way, so its steps name the action they
    are asked during.
    """

    stepper: QueryStepper = field(kw_only=True)
    """
    The stepper whose steps name the action.
    """

    def on_start(self, node: PlanNode) -> None:
        self.stepper.running.append(node)

    def on_end(self, node: PlanNode) -> None:
        self.stepper.running = [
            running for running in self.stepper.running if running is not node
        ]
