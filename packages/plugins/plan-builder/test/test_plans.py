"""
Checking plans against the limits and the catalog, and keeping them in the plan
directory.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from cramera_plan_builder.exceptions import (
    DuplicateIdentifier,
    InvalidIdentifier,
    InvalidPlanName,
    InvalidPlanText,
    MissingStepParameter,
    PlanTooLarge,
    PlanWithoutRobot,
    TooManyEntries,
    UnknownPlan,
    UnknownReference,
    UnreadablePlan,
    UnsafeStoragePath,
    UnsupportedByCatalog,
    ValueOutOfRange,
)
from cramera_plan_builder.plans import CatalogCheck, PlanCheck, PlanFile, PlanStore
from cramera_protocol.plan_builder import (
    PlacementMode,
    PlanBuilderCatalog,
    PlanBuilderLimits,
    PlanDocument,
    PlanKey,
    PlanRecord,
    PlanStepKey,
    StepConstraint,
    StepKind,
)

# %% limits


@pytest.fixture
def check() -> PlanCheck:
    """
    :return: The check with the default limits.
    """
    return PlanCheck(PlanBuilderLimits())


def test_a_complete_plan_passes(check, plan):
    check.check(plan)
    check.complete(plan)


@pytest.mark.parametrize(
    ("file_name", "error"),
    [
        ("invalid_name.json", InvalidPlanName),
        ("invalid_robot_identity.json", InvalidIdentifier),
        ("duplicate_objects.json", DuplicateIdentifier),
        ("unknown_selected_robot.json", UnknownReference),
        ("step_with_unknown_object.json", UnknownReference),
        ("far_away_object.json", ValueOutOfRange),
        ("label_with_control_character.json", InvalidPlanText),
    ],
)
def test_a_malformed_plan_is_refused(check, read_plan, file_name, error):
    with pytest.raises(error):
        check.check(read_plan(f"invalid/{file_name}"))


def test_a_plan_with_more_steps_than_fit_is_refused(plan):
    limits = PlanBuilderLimits(maximum_steps=len(plan.robots[0].steps) - 1)
    with pytest.raises(TooManyEntries) as refusal:
        PlanCheck(limits).check(plan)
    assert refusal.value.limit == limits.maximum_steps


def test_a_plan_larger_than_the_document_limit_is_refused(plan):
    limits = PlanBuilderLimits(maximum_document_bytes=len(json.dumps(plan.to_json())))
    with pytest.raises(PlanTooLarge):
        PlanCheck(limits).check(replace(plan, task=plan.task + " again"))


def test_a_constraint_longer_than_a_text_may_be_is_refused(plan):
    limits = PlanBuilderLimits()
    step = plan.robots[0].steps[0]
    step.constraints = [StepConstraint(text="x" * (limits.maximum_text_length + 1))]
    with pytest.raises(InvalidPlanText):
        PlanCheck(limits).check(plan)


def test_an_unfinished_plan_can_be_saved_but_not_run(check, read_plan):
    unfinished = read_plan("unfinished.json")
    check.check(unfinished)
    with pytest.raises(MissingStepParameter) as refusal:
        check.complete(unfinished)
    assert refusal.value.parameter == PlanStepKey.OBJECT


def test_a_put_down_at_a_pose_needs_the_pose(check, plan):
    place = plan.robots[0].steps[5]
    place.target = None
    with pytest.raises(MissingStepParameter) as refusal:
        check.complete(plan)
    assert refusal.value.parameter == PlanStepKey.TARGET


def test_a_put_down_on_a_surface_needs_its_type(check, plan):
    transport = plan.robots[0].steps[3]
    assert transport.placement is PlacementMode.SURFACE
    transport.surface_type = None
    with pytest.raises(MissingStepParameter) as refusal:
        check.complete(plan)
    assert refusal.value.parameter == PlanStepKey.SURFACE_TYPE


def test_a_plan_without_a_robot_cannot_run(check):
    with pytest.raises(PlanWithoutRobot):
        check.complete(PlanDocument(name="empty"))


# %% catalog


@pytest.fixture
def catalog(read_json) -> PlanBuilderCatalog:
    """
    :return: The test workspace's catalog, with the test laboratory as environment.
    """
    catalog = PlanBuilderCatalog.from_json(read_json("workspace.json"))
    catalog.environments = PlanBuilderCatalog.from_json(
        {"liveUrl": catalog.live_url, "environments": [{"name": "lab"}]}
    ).environments
    return catalog


def test_a_plan_of_offered_entries_passes_the_catalog(catalog, plan):
    CatalogCheck(catalog).check(plan)


def test_an_arm_the_robot_does_not_have_is_refused(catalog, plan):
    plan.robots[0].steps[0].arm = "MIDDLE"
    with pytest.raises(UnsupportedByCatalog) as refusal:
        CatalogCheck(catalog).check(plan)
    assert refusal.value.offered == catalog.robots[0].arms


def test_a_step_the_robot_cannot_take_is_refused(catalog, plan):
    tracy = plan.robots[1]
    tracy.steps[0] = replace(tracy.steps[0], kind=StepKind.NAVIGATE)
    with pytest.raises(UnsupportedByCatalog) as refusal:
        CatalogCheck(catalog).check(plan)
    assert refusal.value.value == StepKind.NAVIGATE


@pytest.mark.parametrize(
    "change",
    [
        lambda plan: setattr(plan, "environment", "nowhere"),
        lambda plan: setattr(plan.objects[0], "model", "anvil.stl"),
        lambda plan: setattr(plan.robots[0], "model", "R2D2"),
        lambda plan: setattr(plan.robots[0].steps[1], "torso_state", "TALL"),
        lambda plan: setattr(plan.robots[0].steps[3], "surface_type", "Cloud"),
    ],
)
def test_an_entry_the_catalog_does_not_offer_is_refused(catalog, plan, change):
    change(plan)
    with pytest.raises(UnsupportedByCatalog):
        CatalogCheck(catalog).check(plan)


def test_without_cram_only_the_environment_is_checked(catalog, plan):
    catalog.robots, catalog.missing = [], ["coraplex"]
    CatalogCheck(catalog).check(plan)
    plan.environment = "nowhere"
    with pytest.raises(UnsupportedByCatalog) as refusal:
        CatalogCheck(catalog).check(plan)
    assert refusal.value.location == PlanKey.ENVIRONMENT


# %% storage


@pytest.fixture
def store(tmp_path) -> PlanStore:
    """
    :return: An empty plan directory in the test's directory.
    """
    return PlanStore(tmp_path / "plans")


def test_a_saved_plan_is_listed_and_loaded(store, plan):
    saved = store.save(PlanRecord(document=plan))
    assert [summary.identifier for summary in store.summaries()] == [saved.identifier]
    assert store.summaries()[0].name == plan.name
    assert store.load(saved.identifier) == saved


def test_saving_under_an_identity_replaces_the_plan(store, plan):
    saved = store.save(PlanRecord(document=plan))
    store.save(PlanRecord(identifier=saved.identifier, document=replace(plan, task="")))
    assert store.load(saved.identifier).document.task == ""
    assert len(store.summaries()) == 1


def test_a_damaged_plan_does_not_hide_the_others(store, plan):
    saved = store.save(PlanRecord(document=plan))
    (store.directory / f"damaged{PlanFile.SUFFIX}").write_text("{", encoding="utf-8")
    assert [summary.identifier for summary in store.summaries()] == [saved.identifier]
    with pytest.raises(UnreadablePlan):
        store.load("damaged")


def test_an_unknown_plan_is_answered_as_such(store):
    with pytest.raises(UnknownPlan):
        store.load("missing")


@pytest.mark.parametrize("identifier", ["../escape", "", "a/b", "x" * 97])
def test_a_malformed_plan_identity_is_refused(store, identifier):
    with pytest.raises(InvalidIdentifier):
        store.path(identifier)


def test_a_plan_directory_that_is_a_link_is_not_written(tmp_path, plan):
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "plans").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(UnsafeStoragePath):
        PlanStore(tmp_path / "plans").save(PlanRecord(document=plan))


def test_no_plan_directory_lists_no_plans(store):
    assert store.summaries() == []
