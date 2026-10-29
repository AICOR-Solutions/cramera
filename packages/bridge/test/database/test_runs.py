"""
The SQLite database a scene bundle keeps of every run recorded into it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from cramera_bridge.database.runs import (
    PlanDatabase,
    RecordedPlanStep,
    RunDocument,
    SavedRun,
)
from cramera_bridge.documents import DocumentFile
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import (
    PlanConstraint,
    PlanNode,
    PlanNodeKind,
    SceneDescription,
)

FIRST_SAVE = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
"""
When the first run of a test is saved.
"""

SECOND_SAVE = datetime(2026, 10, 28, 13, 0, tzinfo=timezone.utc)
"""
When the second run of a test is saved.
"""

# %% a recorded bundle


def recorded_scene(task: str) -> SceneDescription:
    """
    :param task: What the run did.
    :return: A scene whose plan picks a cup up with one motion below the action.
    """
    motion = PlanNode(
        kind=PlanNodeKind.MOTION,
        label="MoveGripperMotion",
        status="SUCCEEDED",
        identifier="plan_node_2",
        parent="plan_node_1",
        start=3,
        end=7,
        parameters={"motion": "OPEN", "gripper": "PR2LeftGripper"},
    )
    action = PlanNode(
        kind=PlanNodeKind.ACTION,
        label="PickUpAction",
        status="SUCCEEDED",
        identifier="plan_node_1",
        arm="PR2LeftArm",
        target="cup",
        robot="PR2",
        parameters={"arm": "PR2LeftArm"},
        constraints=[PlanConstraint(text="keep the cup upright", monitor="Upright")],
        children=[motion],
    )
    return SceneDescription(name="pick_up", task=task, plan_trees=[action])


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    """
    :return: A bundle holding a recorded run, its trajectory and a mesh.
    """
    DocumentFile(tmp_path / BundleFile.SCENE).write(recorded_scene("first run"))
    (tmp_path / BundleFile.TRAJECTORY).write_text('{"frames": [1]}')
    (tmp_path / BundleFile.MESHES).mkdir()
    (tmp_path / BundleFile.MESHES / "cup.stl").write_text("solid cup")
    return tmp_path


def runs(database: PlanDatabase) -> list[SavedRun]:
    """
    :return: Every run the database keeps, with what belongs to it loaded.
    """
    steps = selectinload(SavedRun.steps)
    query = (
        select(SavedRun)
        .options(
            selectinload(SavedRun.documents),
            steps.selectinload(RecordedPlanStep.parameters),
            steps.selectinload(RecordedPlanStep.constraints),
        )
        .order_by(SavedRun.identifier)
    )
    with Session(database.engine()) as session:
        return list(session.scalars(query).all())


# %% keeping a run


def test_the_database_is_the_bundles_plan_database_file(bundle):
    assert PlanDatabase(bundle).path == bundle / BundleFile.PLAN_DATABASE


def test_a_run_is_kept_with_what_the_scene_says_of_it(bundle):
    database = PlanDatabase(bundle)

    run = database.add_run(FIRST_SAVE)

    [kept] = runs(database)
    assert kept.identifier == run
    assert kept.recorded_at.replace(tzinfo=timezone.utc) == FIRST_SAVE
    assert (kept.scene, kept.task) == ("pick_up", "first run")


def test_a_run_keeps_the_documents_that_change_but_not_the_meshes(bundle):
    database = PlanDatabase(bundle)

    database.add_run(FIRST_SAVE)

    [kept] = runs(database)
    assert {document.file: document.content for document in kept.documents} == {
        BundleFile.SCENE.value: (bundle / BundleFile.SCENE).read_text(),
        BundleFile.TRAJECTORY.value: (bundle / BundleFile.TRAJECTORY).read_text(),
    }


def test_every_step_is_kept_with_its_parameters_and_constraints(bundle):
    database = PlanDatabase(bundle)
    [action] = recorded_scene("first run").plan_trees
    [motion] = action.children

    database.add_run(FIRST_SAVE)

    [kept] = runs(database)
    steps = {step.node: step for step in kept.steps}
    assert set(steps) == {action.identifier, motion.identifier}
    assert {
        parameter.name: parameter.value
        for parameter in steps[motion.identifier].parameters
    } == motion.parameters
    assert (
        steps[motion.identifier].parent,
        steps[motion.identifier].kind,
        steps[motion.identifier].first_frame,
        steps[motion.identifier].last_frame,
    ) == (action.identifier, PlanNodeKind.MOTION.value, motion.start, motion.end)
    assert [
        (constraint.text, constraint.monitor)
        for constraint in steps[action.identifier].constraints
    ] == [(constraint.text, constraint.monitor) for constraint in action.constraints]
    assert (
        steps[action.identifier].arm,
        steps[action.identifier].target,
        steps[action.identifier].robot,
    ) == (action.arm, action.target, action.robot)


def test_a_further_run_joins_the_earlier_ones(bundle):
    database = PlanDatabase(bundle)
    first = database.add_run(FIRST_SAVE)
    DocumentFile(bundle / BundleFile.SCENE).write(recorded_scene("second run"))

    second = database.add_run(SECOND_SAVE)

    assert [(run.identifier, run.task) for run in runs(database)] == [
        (first, "first run"),
        (second, "second run"),
    ]
    assert database.latest_run() == second


def test_refreshing_a_run_keeps_what_was_written_after_it_was_saved(bundle):
    database = PlanDatabase(bundle)
    run = database.add_run(FIRST_SAVE)
    (bundle / BundleFile.ACCEPTANCE_METRICS).write_text('{"success": true}')

    database.refresh_documents(run)

    [kept] = runs(database)
    assert {document.file for document in kept.documents} == {
        BundleFile.SCENE.value,
        BundleFile.TRAJECTORY.value,
        BundleFile.ACCEPTANCE_METRICS.value,
    }


def test_refreshing_a_run_replaces_its_documents_rather_than_adding_to_them(bundle):
    database = PlanDatabase(bundle)
    run = database.add_run(FIRST_SAVE)

    database.refresh_documents(run)

    with Session(database.engine()) as session:
        assert sorted(session.scalars(select(RunDocument.file)).all()) == sorted(
            [BundleFile.SCENE.value, BundleFile.TRAJECTORY.value]
        )


def test_a_run_without_plans_keeps_no_steps(tmp_path):
    DocumentFile(tmp_path / BundleFile.SCENE).write(SceneDescription(name="empty"))
    database = PlanDatabase(tmp_path)

    database.add_run(FIRST_SAVE)

    with Session(database.engine()) as session:
        assert session.scalars(select(RecordedPlanStep)).all() == []
