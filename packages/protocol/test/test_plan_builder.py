"""
The plan builder's plans, catalog, constraints and demo runs.
"""

from __future__ import annotations

import pytest

from cramera_protocol.browser import BROWSER_ENUMERATIONS
from cramera_protocol.exceptions import (
    InvalidDocumentValue,
    UnsupportedProtocolVersion,
)
from cramera_protocol.geometry import Pose
from cramera_protocol.live_messages import (
    ConstraintMonitorType,
    MonitorParameterKey,
    MonitorSpecificationKey,
)
from cramera_protocol.plan_builder import (
    DemoDocument,
    DemoDocumentKey,
    PlacementMode,
    PlanBuilderCatalog,
    PlanBuilderCatalogKey,
    PlanBuilderLimits,
    PlanBuilderLimitsKey,
    PlanBuilderPageParameter,
    PlanBuilderRoute,
    PlanDocument,
    PlanKey,
    PlannedObjectKey,
    PlannedRobotKey,
    PlanRecord,
    PlanRecordKey,
    PlanStepKey,
    RuleValue,
    RunMode,
    RunRequest,
    RunState,
    RunStatus,
    RunStatusKey,
    StepConstraintKey,
    StepKind,
    StepSwitch,
)
from cramera_protocol.version import CURRENT_VERSION

# %% plans


def test_a_plan_reads_its_robots_steps_and_objects(read_json):
    data = read_json("plan_builder/plan.json")
    plan = PlanDocument.from_json(data)
    written_robot = data[PlanKey.ROBOTS][0]
    robot, standing = plan.robots
    park, torso, transport, navigate = robot.steps
    written_transport = written_robot[PlannedRobotKey.STEPS][2]
    assert robot.pose == Pose.from_json(written_robot[PlannedRobotKey.POSE])
    assert robot.joint_positions == written_robot[PlannedRobotKey.JOINT_POSITIONS]
    assert [step.kind for step in robot.steps] == [
        StepKind.PARK_ARMS,
        StepKind.MOVE_TORSO,
        StepKind.TRANSPORT,
        StepKind.NAVIGATE,
    ]
    assert (
        torso.torso_state
        == written_robot[PlannedRobotKey.STEPS][1][PlanStepKey.TORSO_STATE]
    )
    assert transport.placement is PlacementMode.SURFACE
    assert transport.object_identifier == written_transport[PlanStepKey.OBJECT]
    assert navigate.target == Pose.from_json(
        written_robot[PlannedRobotKey.STEPS][3][PlanStepKey.TARGET]
    )
    assert standing.steps == []
    assert plan.selected_robot == data[PlanKey.SELECTED_ROBOT]
    assert plan.objects[0].pose == Pose.from_json(
        data[PlanKey.OBJECTS][0][PlannedObjectKey.POSE]
    )


def test_a_step_keeps_the_monitor_and_the_switch_its_constraints_compiled_to(
    read_json,
):
    data = read_json("plan_builder/plan.json")
    transport = PlanDocument.from_json(data).robots[0].steps[2]
    upright, looking = transport.constraints
    written = data[PlanKey.ROBOTS][0][PlannedRobotKey.STEPS][2][
        PlanStepKey.CONSTRAINTS
    ][0]
    assert upright.monitor.monitor_type is ConstraintMonitorType.VECTORS_ALIGNED
    assert (
        upright.monitor.parameters[MonitorParameterKey.TIP_LINK]
        == written[StepConstraintKey.MONITOR][MonitorSpecificationKey.PARAMETERS][
            MonitorParameterKey.TIP_LINK
        ]
    )
    assert upright.switch is None
    assert looking.monitor is None
    assert looking.switch is StepSwitch.LOOK_AT_OPERATION_SITE


def test_a_plan_round_trips(read_json):
    plan = PlanDocument.from_json(read_json("plan_builder/plan.json"))
    assert PlanDocument.from_json(plan.to_json()) == plan


def test_left_out_fields_take_their_defaults(read_json):
    plan = PlanDocument.from_json(read_json("plan_builder/plan_with_defaults.json"))
    step = plan.robots[0].steps[0]
    assert plan.format_version == CURRENT_VERSION
    assert plan.environment is None and plan.selected_robot is None
    assert plan.task == ""
    assert step.placement is PlacementMode.POSE
    assert step.target is None and step.constraints == []
    assert plan.objects[0].color is None


def test_a_written_plan_names_the_current_version():
    written = PlanDocument(name="empty").to_json()
    assert written[PlanKey.FORMAT_VERSION] == CURRENT_VERSION.to_json()
    assert PlanKey.ENVIRONMENT not in written


def test_a_plan_of_another_major_version_is_refused(read_json):
    with pytest.raises(UnsupportedProtocolVersion):
        PlanDocument.from_json(
            read_json("plan_builder/invalid/plan_from_next_major_version.json")
        )


@pytest.mark.parametrize(
    "file_name",
    ["plan_with_unknown_step_kind.json", "plan_with_short_pose.json"],
)
def test_a_plan_with_a_malformed_value_is_refused(read_json, file_name):
    with pytest.raises(InvalidDocumentValue):
        PlanDocument.from_json(read_json(f"plan_builder/invalid/{file_name}"))


def test_a_record_without_identity_asks_for_a_new_plan():
    record = PlanRecord(document=PlanDocument(name="new"))
    written = record.to_json()
    assert PlanRecordKey.IDENTIFIER not in written
    assert PlanRecord.from_json(written) == record


# %% catalog


def test_the_catalog_reads_robots_environments_objects_and_rules(read_json):
    data = read_json("plan_builder/catalog.json")
    catalog = PlanBuilderCatalog.from_json(data)
    robot, arm_only = catalog.robots
    rule = catalog.constraint_rules[0]
    assert robot.steps == list(StepKind)
    assert StepKind.NAVIGATE not in arm_only.steps
    assert [entry.name for entry in catalog.environments] == [
        entry["name"] for entry in data[PlanBuilderCatalogKey.ENVIRONMENTS]
    ]
    assert rule.monitor_type is ConstraintMonitorType.HEIGHT
    assert rule.parameters[MonitorParameterKey.LOWER_LIMIT] == RuleValue.LENGTH
    assert rule.observed is True
    assert (
        catalog.limits.maximum_steps
        == data[PlanBuilderCatalogKey.LIMITS][PlanBuilderLimitsKey.MAXIMUM_STEPS]
    )
    assert catalog.limits.maximum_robots == PlanBuilderLimits().maximum_robots
    assert PlanBuilderCatalog.from_json(catalog.to_json()) == catalog


def test_a_catalog_without_cram_names_what_is_missing():
    catalog = PlanBuilderCatalog(live_url="http://127.0.0.1:1", missing=["coraplex"])
    written = catalog.to_json()
    assert written[PlanBuilderCatalogKey.MISSING] == catalog.missing
    assert written[PlanBuilderCatalogKey.ROBOTS] == []
    assert written[PlanBuilderCatalogKey.LIMITS] == PlanBuilderLimits().to_json()


# %% runs


def test_a_run_request_stages_by_default():
    request = RunRequest(plan=PlanDocument(name="x"))
    assert RunRequest.from_json(request.to_json()).mode is RunMode.STAGE


def test_a_run_request_with_an_unknown_mode_is_refused(read_json):
    with pytest.raises(InvalidDocumentValue):
        RunRequest.from_json(
            read_json("plan_builder/invalid/run_request_with_unknown_mode.json")
        )


def test_the_run_status_reads_the_exit_and_the_log(read_json):
    data = read_json("plan_builder/run_status.json")
    status = RunStatus.from_json(data)
    assert status.state is RunState.FAILED
    assert status.mode is RunMode.PERFORM
    assert status.return_code == data[RunStatusKey.RETURN_CODE]
    assert status.log == data[RunStatusKey.LOG]


def test_an_idle_status_names_no_mode_and_no_exit():
    written = RunStatus().to_json()
    assert written[RunStatusKey.STATE] == RunState.IDLE
    assert RunStatusKey.MODE not in written
    assert RunStatusKey.RETURN_CODE not in written


# %% browser


@pytest.mark.parametrize(
    "enumeration",
    [
        PlanBuilderRoute,
        PlanBuilderPageParameter,
        StepKind,
        StepSwitch,
        RuleValue,
        RunMode,
        RunState,
        MonitorParameterKey,
    ],
)
def test_the_plan_builder_names_reach_the_browser(enumeration):
    assert enumeration in BROWSER_ENUMERATIONS


# %% demos


def test_a_demo_document_carries_the_plan_and_its_environment(read_json):
    plan = PlanDocument.from_json(read_json("plan_builder/plan.json"))
    demo = DemoDocument(plan=plan, environment_directory="/scenes/aicor_medical_lab")
    assert DemoDocument.from_json(demo.to_json()) == demo


def test_a_demo_on_an_empty_floor_names_no_environment_directory():
    written = DemoDocument(plan=PlanDocument(name="x")).to_json()
    assert DemoDocumentKey.ENVIRONMENT_DIRECTORY not in written
