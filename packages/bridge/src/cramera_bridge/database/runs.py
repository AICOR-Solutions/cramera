"""
The SQLite database a scene bundle keeps of every run recorded into it.

The bundle's files show its newest run, and the database keeps every run: the documents
that change from one run to the next, and every step of the run's plans with the
parameters and constraints it was recorded with. What stays the same from run to run,
the meshes and the URDFs, is kept once, as the bundle's files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import DateTime, ForeignKey, Text, create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
)
from typing_extensions import List, Optional, Tuple

from cramera_bridge.documents import DocumentFile
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import PlanNode, SceneDescription

# %% tables


class RunTable(DeclarativeBase):
    """
    The tables of the database of recorded runs.
    """


class SavedRun(RunTable):
    """
    One run recorded into the bundle.
    """

    __tablename__ = "saved_run"

    identifier: Mapped[int] = mapped_column(primary_key=True)
    """
    The run's number in the database.
    """

    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    """
    When the run was saved.
    """

    scene: Mapped[str]
    """
    The name of the bundle it was saved into.
    """

    robot: Mapped[Optional[str]]
    """
    The robot's display name, if the run named one.
    """

    environment: Mapped[Optional[str]]
    """
    The environment's display name, if the run named one.
    """

    task: Mapped[Optional[str]]
    """
    What the run did, if it said.
    """

    documents: Mapped[List[RunDocument]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    """
    The documents of the bundle as the run left them.
    """

    steps: Mapped[List[RecordedPlanStep]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    """
    Every step of the plans the run performed.
    """


class RunDocument(RunTable):
    """
    One of the bundle's documents as a run left it.
    """

    __tablename__ = "run_document"

    identifier: Mapped[int] = mapped_column(primary_key=True)
    """
    The document's number in the database.
    """

    run_identifier: Mapped[int] = mapped_column(ForeignKey("saved_run.identifier"))
    """
    The run the document belongs to.
    """

    file: Mapped[str]
    """
    The document's file name in the bundle.
    """

    content: Mapped[str] = mapped_column(Text)
    """
    The document's text.
    """

    run: Mapped[SavedRun] = relationship(back_populates="documents")
    """
    The run the document belongs to.
    """


class RecordedPlanStep(RunTable):
    """
    One step of a plan a run performed, as the bundle's plan view shows it.
    """

    __tablename__ = "recorded_plan_step"

    identifier: Mapped[int] = mapped_column(primary_key=True)
    """
    The step's number in the database.
    """

    run_identifier: Mapped[int] = mapped_column(ForeignKey("saved_run.identifier"))
    """
    The run that performed the step.
    """

    node: Mapped[Optional[str]]
    """
    The step's identifier in the run's plan.
    """

    parent: Mapped[Optional[str]]
    """
    The identifier of the step it belongs to, or None for a plan's root.
    """

    kind: Mapped[str]
    """
    What kind of step it is: an action, a motion, a sequence, ...
    """

    label: Mapped[str]
    """
    The class the step performed.
    """

    status: Mapped[str]
    """
    How the step ended.
    """

    robot: Mapped[Optional[str]]
    """
    The robot that performed it, where the plan names one.
    """

    arm: Mapped[Optional[str]]
    """
    The arm it used, where it used one.
    """

    target: Mapped[Optional[str]]
    """
    What it worked on, where it names it.
    """

    first_frame: Mapped[Optional[int]]
    """
    The first recorded frame it ran in.
    """

    last_frame: Mapped[Optional[int]]
    """
    The last recorded frame it ran in.
    """

    run: Mapped[SavedRun] = relationship(back_populates="steps")
    """
    The run that performed the step.
    """

    parameters: Mapped[List[StepParameter]] = relationship(
        back_populates="step", cascade="all, delete-orphan"
    )
    """
    The parameters the step was performed with.
    """

    constraints: Mapped[List[StepConstraint]] = relationship(
        back_populates="step", cascade="all, delete-orphan"
    )
    """
    The constraints watched while the step ran.
    """


class StepParameter(RunTable):
    """
    One parameter a step was performed with.
    """

    __tablename__ = "step_parameter"

    identifier: Mapped[int] = mapped_column(primary_key=True)
    """
    The parameter's number in the database.
    """

    step_identifier: Mapped[int] = mapped_column(
        ForeignKey("recorded_plan_step.identifier")
    )
    """
    The step it belongs to.
    """

    name: Mapped[str]
    """
    The parameter's name.
    """

    value: Mapped[str]
    """
    The parameter's value, as the plan view shows it.
    """

    step: Mapped[RecordedPlanStep] = relationship(back_populates="parameters")
    """
    The step it belongs to.
    """


class StepConstraint(RunTable):
    """
    One constraint watched while a step ran.
    """

    __tablename__ = "step_constraint"

    identifier: Mapped[int] = mapped_column(primary_key=True)
    """
    The constraint's number in the database.
    """

    step_identifier: Mapped[int] = mapped_column(
        ForeignKey("recorded_plan_step.identifier")
    )
    """
    The step it was watched in.
    """

    text: Mapped[str]
    """
    The constraint as it was written.
    """

    monitor: Mapped[str]
    """
    The class of the monitor it became.
    """

    observation: Mapped[Optional[str]]
    """
    What the monitor last observed, if anything.
    """

    step: Mapped[RecordedPlanStep] = relationship(back_populates="constraints")
    """
    The step it was watched in.
    """


class RecordedPlan(RunTable):
    """
    A plan a run performed, as CRAM's own database mapping stores it in the same file.
    """

    __tablename__ = "recorded_plan"

    identifier: Mapped[int] = mapped_column(primary_key=True)
    """
    The plan's number in the database.
    """

    run_identifier: Mapped[int] = mapped_column(ForeignKey("saved_run.identifier"))
    """
    The run that performed the plan.
    """

    number: Mapped[int]
    """
    The plan's position among the run's plans, counted from one.
    """

    robot: Mapped[Optional[str]]
    """
    The display name of the robot that performed it.
    """

    stored_plan: Mapped[int]
    """
    The ``database_id`` of the plan's row in the ``PlanMappingDAO`` table CRAM's own
    mapping writes.
    """


# %% the database


@dataclass(frozen=True)
class PlanDatabase:
    """
    The plan database of one scene bundle.
    """

    bundle: Path
    """
    The bundle directory.
    """

    run_documents: Tuple[BundleFile, ...] = field(
        default=(
            BundleFile.SCENE,
            BundleFile.TRAJECTORY,
            BundleFile.STATECHARTS,
            BundleFile.QUERY_STEPS,
            BundleFile.ACCEPTANCE_METRICS,
            BundleFile.RECORDED_ANSWERS,
        )
    )
    """
    The bundle's documents that change from one run to the next and are kept with each
    run.
    """

    @property
    def path(self) -> Path:
        """
        The database file.
        """
        return self.bundle / BundleFile.PLAN_DATABASE

    def engine(self) -> Engine:
        """
        :return: An engine on the database file, with every table of the runs created.
        """
        engine = create_engine(f"sqlite:///{self.path}")
        RunTable.metadata.create_all(engine)
        return engine

    def add_run(self, recorded_at: datetime) -> int:
        """
        Keep the run the bundle's files now hold.

        :param recorded_at: When the run was saved.
        :return: The run's number in the database.
        """
        scene = DocumentFile(self.bundle / BundleFile.SCENE).read(SceneDescription)
        run = SavedRun(
            recorded_at=recorded_at,
            scene=scene.name,
            robot=scene.robot_name,
            environment=scene.environment_name,
            task=scene.task,
            documents=self.documents(),
            steps=[step for root in scene.plan_trees for step in self.steps(root)],
        )
        with Session(self.engine()) as session, session.begin():
            session.add(run)
            session.flush()
            return run.identifier

    def refresh_documents(self, run: int) -> None:
        """
        Keep the documents the bundle's files now hold as those of a run, for what is
        written into the bundle after the run was saved.

        :param run: The run's number in the database.
        """
        with Session(self.engine()) as session, session.begin():
            session.get(SavedRun, run).documents = self.documents()

    def latest_run(self) -> int:
        """
        :return: The number of the run kept last.
        """
        with Session(self.engine()) as session:
            return session.scalar(select(func.max(SavedRun.identifier)))

    def documents(self) -> List[RunDocument]:
        """
        :return: The bundle's documents of :attr:`run_documents` that it holds.
        """
        return [
            RunDocument(file=file.value, content=(self.bundle / file).read_text())
            for file in self.run_documents
            if (self.bundle / file).is_file()
        ]

    def steps(self, node: PlanNode) -> List[RecordedPlanStep]:
        """
        :param node: A step of a recorded plan.
        :return: The step and every step below it.
        """
        return [
            RecordedPlanStep(
                node=node.identifier,
                parent=node.parent,
                kind=node.kind.value,
                label=node.label,
                status=node.status,
                robot=node.robot,
                arm=node.arm,
                target=node.target,
                first_frame=node.start,
                last_frame=node.end,
                parameters=[
                    StepParameter(name=name, value=value)
                    for name, value in node.parameters.items()
                ],
                constraints=[
                    StepConstraint(
                        text=constraint.text,
                        monitor=constraint.monitor,
                        observation=constraint.observation,
                    )
                    for constraint in node.constraints
                ],
            )
        ] + [step for child in node.children for step in self.steps(child)]
