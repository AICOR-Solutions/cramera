"""
The PR2's vessel transfer at the laboratory bench, held at every query it asks.

The transfer finds its robot, the bench's handles and the vessel it carries with entity
queries, and every query asked on the run's thread, the plan's own included, is
published as a query step and holds the run until the viewer's **Next** moves it on.

``python -m cramera_bridge.demos.query_stepping --bundle DIR``, where ``DIR`` is a scene
bundle such as ``~/.cramera/scenes/aicor_medical_lab``.
"""

from __future__ import annotations

import copy
import inspect
import linecache
import sys
import threading
import time
from argparse import ArgumentParser
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from typing_extensions import Any, Iterable, Iterator, List, Optional, Sequence

import krrood.entity_query_language as entity_query_language
from coraplex.datastructures.dataclasses import Context
from coraplex.execution_environment import ExecutionEnvironment
from coraplex.plans.plan import Plan
from coraplex.plans.plan_callbacks import PlanCallback
from coraplex.plans.plan_node import PlanNode
from krrood.entity_query_language.backends import (
    EntityQueryLanguageBackend,
    QueryBackend,
)
from krrood.entity_query_language.evaluable import Evaluable
from krrood.entity_query_language.factories import an, entity, the, variable
from semantic_digital_twin.robots.pr2 import PR2
from semantic_digital_twin.semantic_annotations.semantic_annotations import Handle
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.world_entity import Body

from cramera_bridge.exceptions import SceneNameTaken
from cramera_bridge.laboratory.transfer import VesselTransferDemo
from cramera_bridge.live.publisher import LivePublisher
from cramera_bridge.live.query_steps import QueryStepControl
from cramera_bridge.questions.verbalization import QueryVerbalizer
from cramera_bridge.visualization import LiveVisualization
from cramera_protocol.live_messages import (
    RecordingSaveRequest,
    SavedScene,
    SceneDestination,
)
from cramera_protocol.query_steps import (
    CallSite,
    HeldStep,
    QueryStep,
    QuerySteps,
    SourceExcerpt,
    StepMoment,
    StepPhase,
    SteppingRequest,
)
from cramera_protocol.resolutions import BackendDescription, KnowledgeSource

NAME = "aicor_medical_lab_pr2_query_steps"
"""
The name the recording is saved under.
"""

TASK = "PR2: vessel transfer A1 → A3, stepping through its queries"
"""
What the recording shows, as the scene picker labels it.
"""

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

DURING = {
    StepPhase.SETUP: "setting up the robot at the bench",
    StepPhase.RESOLUTION: "choosing the vessel to carry",
    StepPhase.EXPANSION: "expanding the transfer",
    StepPhase.EXECUTION: "carrying out the transfer",
}
"""
What the run is doing in each phase, as said to a person.
"""

SKIPPED_FILES = (
    str(Path(entity_query_language.__file__).parent.parent),
    contextmanager.__code__.co_filename,
)
"""
The files whose frames are not the code asking a query: krrood's own and contextlib.
"""

STEPPING_CODE = ("QueryStepper.", "SteppedBackend.")
"""
The qualified names opening the stepping's own functions, which ask no query either.
"""

# %% holding


@dataclass
class HeldQueries(QueryStepControl):
    """
    Holds the run's thread at a query until the viewer moves it on.
    """

    stepping: bool = True
    """
    Whether the run is held at every query.
    """

    holds_nested: bool = True
    """
    Whether it is also held at queries asked while another is answered.
    """

    held: Optional[HeldStep] = None
    """
    The step the run is held at, or None while it runs on.
    """

    condition: threading.Condition = field(default_factory=threading.Condition)
    """
    Wakes the held run when the viewer moves it on.
    """

    def advance(self, held: Optional[HeldStep]) -> None:
        with self.condition:
            if held is None or held == self.held:
                self.held = None
                self.condition.notify_all()

    def change_stepping(self, request: SteppingRequest) -> None:
        with self.condition:
            self.stepping = request.stepping
            self.holds_nested = request.holds_nested
            if not self.stepping:
                self.held = None
            self.condition.notify_all()

    def holds_at(self, depth: int) -> bool:
        """
        :param depth: How many queries a query is asked inside.
        :return: Whether the run is held at it.
        """
        return self.stepping and (depth == 0 or self.holds_nested)


# %% stepping


@dataclass
class SteppedBackend(QueryBackend):
    """
    Answers with another backend while the stepper publishes and holds each query.
    """

    inner: QueryBackend = field(kw_only=True)
    """
    The backend answering the queries.
    """

    stepper: QueryStepper = field(kw_only=True)
    """
    Publishes the queries and holds the run at them.
    """

    def evaluate(self, expression: Evaluable) -> Iterable[Any]:
        return self.stepper.answer(expression, self.inner)


@dataclass
class QueryStepper:
    """
    Publishes every query asked on one thread as a query step and holds the thread at
    it, while :meth:`watching`.
    """

    publisher: LivePublisher
    """
    The live publisher the steps are published through.
    """

    control: HeldQueries = field(default_factory=HeldQueries)
    """
    Holds the run at its queries.
    """

    phase: StepPhase = StepPhase.SETUP
    """
    What the run is doing.
    """

    actions: List[str] = field(default_factory=list)
    """
    The actions under way, outermost first.
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
        Step every query asked on this thread until the block ends, whichever backend
        answers it.
        """
        original = Evaluable.evaluate
        stepper = self

        def evaluate(expression: Evaluable, backend: Optional[QueryBackend] = None):
            if (
                threading.current_thread() is not stepper.thread
                or isinstance(backend, SteppedBackend)
                or stepper.answers_within()
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
            self.control.change_stepping(SteppingRequest(stepping=False))
            self.publish()

    def backend(self, inner: QueryBackend) -> QueryBackend:
        """
        :param inner: A backend a context answers its plans' open parts with.
        :return: The backend stepping its queries.
        """
        return SteppedBackend(inner=inner, stepper=self)

    def progress(self) -> PlanCallback:
        """
        :return: The plan callback that follows the action under way.
        """
        return ActionProgress(stepper=self)

    # %% answering

    def answer(self, expression: Evaluable, inner: QueryBackend) -> Iterator[Any]:
        """
        Publish the query, hold at it, answer it with the inner backend and hold at its
        answers once they are all given.

        :param expression: The query.
        :param inner: The backend answering it.
        :return: The answers, as the inner backend gives them.
        """
        step = self.ask(expression, inner)
        self.hold(step)
        started = time.perf_counter()
        answers = iter(inner.evaluate(expression))
        about = []
        finished = False
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
                about.append(answer)
                yield answer
            finished = True
        finally:
            step.moment = StepMoment.ANSWERED
            step.milliseconds = (time.perf_counter() - started) * 1000
            shown = about[:HIGHLIGHTED_ANSWERS]
            step.highlight = self.publisher.scene_highlight(shown, framed=shown)
            if finished:
                self.hold(step)
            else:
                self.publish()

    def ask(self, expression: Evaluable, inner: QueryBackend) -> QueryStep:
        """
        :param expression: The query.
        :param inner: The backend answering it.
        :return: Its new step, asked and not yet answered.
        """
        frame = self.asking_frame()
        step = QueryStep(
            number=len(self.steps),
            asker=self.asking[-1] if self.asking else None,
            depth=len(self.asking),
            phase=self.phase,
            during=self.actions[-1] if self.actions else DURING[self.phase],
            moment=StepMoment.ASKED,
            question=self.verbalizer.verbalize(expression, inner),
            code=None if frame is None else self.excerpt(frame),
            caller=None if frame is None else self.call_site(frame),
            backend=BackendDescription(
                name=type(inner).__name__, source=KnowledgeSource.WORKING_MEMORY
            ),
            generates=inner.opening_directive is not None
            and inner.opening_directive.name == "GENERATE",
        )
        self.steps.append(step)
        return step

    def hold(self, step: QueryStep) -> None:
        """
        Publish the steps and, while stepping, wait until the viewer moves on.

        :param step: The step the run reached.
        """
        control = self.control
        with control.condition:
            if control.holds_at(step.depth):
                control.held = HeldStep(number=step.number, moment=step.moment)
            self.publish()
            while control.held is not None:
                control.condition.wait()
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

    @staticmethod
    def answers_within() -> bool:
        """
        :return: Whether the query is evaluated by krrood within answering another, as
            a part of that query rather than a query of its own.
        """
        frame = sys._getframe(2)
        while frame is not None and frame.f_code.co_filename.startswith(SKIPPED_FILES):
            frame = frame.f_back
        return frame is not None and frame.f_code.co_qualname.startswith(STEPPING_CODE)

    # %% describing

    @staticmethod
    def word(answer: Any) -> str:
        """
        :param answer: One answer.
        :return: It in words: its name where it has one, with its body's where the
            name only repeats its kind.
        """
        name = getattr(answer, "name", None)
        if str(name) == type(answer).__name__ and hasattr(answer, "root"):
            name = f"{name} · {answer.root.name}"
        text = str(answer if name is None else name)
        return text if len(text) <= ANSWER_LENGTH else text[: ANSWER_LENGTH - 1] + "…"

    @staticmethod
    def asking_frame() -> Optional[inspect.FrameInfo]:
        """
        :return: The frame of the code asking the query, outside krrood and the
            stepping.
        """
        frame = sys._getframe(1)
        while frame is not None:
            if not (
                frame.f_code.co_filename.startswith(SKIPPED_FILES)
                or frame.f_code.co_qualname.startswith(STEPPING_CODE)
            ):
                return inspect.getframeinfo(frame, context=0)._replace(
                    function=frame.f_code.co_qualname
                )
            frame = frame.f_back
        return None

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
    Tells the stepper which action is under way.
    """

    stepper: QueryStepper = field(kw_only=True)
    """
    The stepper whose steps name the action.
    """

    def on_start(self, node: PlanNode) -> None:
        designator = getattr(node, "designator", None)
        self.stepper.actions.append(
            type(node).__name__ if designator is None else type(designator).__name__
        )

    def on_end(self, node: PlanNode) -> None:
        if self.stepper.actions:
            self.stepper.actions.pop()


# %% demo


@dataclass
class QueryingTransferDemo(VesselTransferDemo):
    """
    The vessel transfer, finding its robot, the handles and its vessel with queries and
    held at every query it asks.
    """

    stepper: Optional[QueryStepper] = field(init=False, default=None)
    """
    Steps the current run's queries, once it is published.
    """

    vessel: Optional[Body] = field(init=False, default=None)
    """
    The vessel the run carries, once a query found it.
    """

    holds: bool = True
    """
    Whether the run starts held at every query; the viewer can change it.
    """

    def the_robot(self, world: World) -> PR2:
        """
        :param world: The world built for the task.
        :return: The PR2 in it.
        """
        robot = variable(PR2, world.semantic_annotations)
        return the(entity(robot)).first()

    def the_handles(self, world: World) -> List[Handle]:
        """
        :param world: The world built for the task.
        :return: Every handle at the bench.
        """
        handle = variable(Handle, world.semantic_annotations)
        return an(entity(handle)).tolist()

    def the_vessel(self, world: World) -> Body:
        """
        :param world: The world built for the task.
        :return: The vessel standing in the source slot.
        """
        key = self.vessel_in(self.source_slot)
        body = variable(Body, world.bodies)
        return the(entity(body).where(body.name.name == key)).first()

    def vessel_key(self) -> str:
        return str(self.vessel.name.name)

    def build_context(self, world: World) -> Context:
        self.stepper.phase = StepPhase.SETUP
        self.the_robot(world)
        self.the_handles(world)
        self.stepper.phase = StepPhase.RESOLUTION
        self.vessel = self.the_vessel(world)
        self.stepper.phase = StepPhase.SETUP
        context = super().build_context(world)
        context.query_backend = self.stepper.backend(context.query_backend)
        return context

    def run(self) -> SavedScene:
        """
        Publish the world before the first query, so every query can be held, then run
        the transfer as :meth:`RobotTaskDemo.run` does.

        :return: The measured recording.
        """
        name = self.scene_name()
        if (self.locations.local_scenes / name).exists():
            raise SceneNameTaken(name)
        world = self.build_world()
        visualization = LiveVisualization(
            world=world, port=self.port, locations=self.locations
        ).start()
        try:
            self.on_live_started(visualization)
            self.stepper = QueryStepper(
                publisher=visualization.publisher,
                control=HeldQueries(stepping=self.holds),
            )
            with self.stepper.watching():
                context = self.build_context(world)
                self.stepper.phase = StepPhase.EXPANSION
                plan = self.build_plan(context)
                plan.node_callbacks.append(visualization.plan_callback(plan))
                plan.node_callbacks.append(self.stepper.progress())
                self.stepper.phase = StepPhase.EXECUTION
                with ExecutionEnvironment(
                    execution_type=self.execution_type,
                    collision_avoidance=self.collision_avoidance,
                ):
                    plan.perform()
            metrics = self.measure(context)
            visualization.publisher.finish_recording()
            saved = visualization.publisher.save_recording(
                RecordingSaveRequest(
                    name=name,
                    destination=SceneDestination.LOCAL,
                    environment=self.environment_name,
                    task=self.task,
                )
            )
        finally:
            if self.observation is not None:
                self.observation.stop()
            visualization.stop()
        self.complete(self.locations.local_scenes / saved.scene, metrics)
        return saved


def main(arguments: Optional[Sequence[str]] = None) -> None:
    """
    ``python -m cramera_bridge.demos.query_stepping --bundle DIR [--port PORT]``
    """
    parser = ArgumentParser(description=TASK)
    parser.add_argument(
        "--bundle", type=Path, required=True, help="the laboratory bundle"
    )
    parser.add_argument("--port", type=int, default=None, help="the live port")
    parser.add_argument(
        "--name", default=NAME, help="the name the recording is saved under"
    )
    parser.add_argument(
        "--no-hold", action="store_true", help="run on without holding at queries"
    )
    options = parser.parse_args(arguments)
    fields = dict(name=options.name, task=TASK, holds=not options.no_hold)
    if options.port is not None:
        fields["port"] = options.port
    demo = QueryingTransferDemo.at_the_bench(options.bundle.expanduser(), **fields)
    saved = demo.run()
    print(f"asked {len(demo.stepper.steps)} queries; saved {saved.scene}")


if __name__ == "__main__":
    main()
