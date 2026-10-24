"""
The plan builder's routes as the viewer serves them.
"""

from __future__ import annotations

import json
from http import HTTPStatus


from cramera.http.messages import HttpMethod, MediaType
from cramera.locations import DataLocations
from cramera_plan_builder.constraints import ConstraintCompiler
from cramera_plan_builder.demos import DEMO_SUFFIX, DemoTemplate
from cramera_plan_builder.plugin import (
    PlanBuilderPlugin,
    PlanBuilderStorage,
    StorageDirectory,
)
from cramera_plan_builder.workspace import (
    CramModule,
    CramModules,
    MissingWorkspace,
    WorkspaceLoader,
)
from cramera_protocol.live import LIVE_HOST, LIVE_PORT
from cramera_protocol.plan_builder import (
    ConstraintText,
    DemoDocument,
    DemoSource,
    PlanBuilderCatalog,
    PlanBuilderLimits,
    PlanBuilderRoute,
    PlanBuilderVariable,
    PlanList,
    PlanRecord,
    RunMode,
    RunRequest,
    RunState,
    RunStatus,
    SavedDemo,
    StepConstraint,
)
from cramera_protocol.viewer import ErrorKey

from .conftest import DEMO_PORT, send
from .dataset.demo_source import demo_document
from .dataset.given_workspace import DATASET
from cramera_plan_builder.plugin import NAVIGATION_TITLE
from cramera_protocol.viewer import NavigationGroup, ViewerRoute
from cramera_protocol.plan_builder import PlanBuilderFile

# %% configuration


def test_demos_go_below_the_data_directory_unless_configured(tmp_path):
    locations = DataLocations(data=tmp_path, shared_scenes=None)
    default = PlanBuilderStorage.of(locations, {})
    configured = PlanBuilderStorage.of(
        locations, {PlanBuilderVariable.OUTPUT: str(tmp_path / "elsewhere")}
    )
    assert default.demos == tmp_path / StorageDirectory.BUILDER / StorageDirectory.DEMOS
    assert configured.demos == tmp_path / "elsewhere"
    assert default.plans == configured.plans


def test_demos_publish_on_the_live_port_unless_configured():
    assert PlanBuilderPlugin(environment={}).port() == LIVE_PORT
    configured = PlanBuilderPlugin(environment={PlanBuilderVariable.PORT: DEMO_PORT})
    assert configured.port() == int(DEMO_PORT)


# %% catalog


def test_the_catalog_lists_the_workspace_and_the_environments(get, given_workspace):
    answer = get(PlanBuilderRoute.CATALOG)
    catalog = PlanBuilderCatalog.from_json(json.loads(answer.body))
    assert answer.status == HTTPStatus.OK
    assert catalog.robots == given_workspace.robots()
    assert catalog.objects == given_workspace.objects()
    assert [entry.name for entry in catalog.environments] == ["lab"]
    assert catalog.live_url == f"http://{LIVE_HOST}:{DEMO_PORT}"
    assert catalog.missing == []
    assert catalog.limits == PlanBuilderLimits()


def test_the_catalog_lists_the_actions_and_the_modules_that_failed(
    get, given_workspace
):
    catalog = PlanBuilderCatalog.from_json(
        json.loads(get(PlanBuilderRoute.CATALOG).body)
    )
    discovered = given_workspace.action_catalog()
    assert catalog.actions == discovered.actions
    assert catalog.failed_action_modules == discovered.failed_modules


def test_without_cram_the_catalog_names_what_is_missing(serve, output):
    plugin = PlanBuilderPlugin(
        environment={PlanBuilderVariable.OUTPUT: str(output)},
        workspace=WorkspaceLoader(modules=CramModules(finder=lambda name: None)),
    )
    answer = send(serve(plugin), HttpMethod.GET, PlanBuilderRoute.CATALOG)
    catalog = PlanBuilderCatalog.from_json(json.loads(answer.body))
    assert catalog.missing == [module.value for module in CramModule]
    assert catalog.robots == [] and catalog.objects == []
    assert catalog.actions == [] and catalog.failed_action_modules == []
    assert [entry.name for entry in catalog.environments] == ["lab"]


def test_an_object_models_file_is_served(get):
    answer = get(f"{PlanBuilderRoute.OBJECT_FILES}milk.stl")
    assert answer.status == HTTPStatus.OK
    assert answer.media_type is MediaType.STL
    assert answer.body == (DATASET / "objects" / "milk.stl").read_bytes()


def test_without_cram_no_object_file_is_served(serve, output):
    plugin = PlanBuilderPlugin(environment={PlanBuilderVariable.OUTPUT: str(output)})
    plugin.workspace.loaded = MissingWorkspace([CramModule.CORAPLEX.value])
    answer = send(
        serve(plugin), HttpMethod.GET, f"{PlanBuilderRoute.OBJECT_FILES}milk.stl"
    )
    assert answer.status == HTTPStatus.SERVICE_UNAVAILABLE


# %% plans


def test_a_saved_plan_is_listed_and_loaded(get, post, plan):
    saved = PlanRecord.from_json(
        json.loads(
            post(PlanBuilderRoute.PLANS, PlanRecord(document=plan).to_json()).body
        )
    )
    listed = PlanList.from_json(json.loads(get(PlanBuilderRoute.PLANS).body))
    loaded = get(f"{PlanBuilderRoute.PLAN}{saved.identifier}")
    assert [summary.identifier for summary in listed.plans] == [saved.identifier]
    assert PlanRecord.from_json(json.loads(loaded.body)) == saved
    catalog = PlanBuilderCatalog.from_json(
        json.loads(get(PlanBuilderRoute.CATALOG).body)
    )
    assert catalog.plans == listed.plans


def test_an_unfinished_plan_is_saved(post, read_plan):
    answer = post(
        PlanBuilderRoute.PLANS,
        PlanRecord(document=read_plan("unfinished.json")).to_json(),
    )
    assert answer.status == HTTPStatus.OK


def test_an_unknown_plan_is_not_found(get):
    assert get(f"{PlanBuilderRoute.PLAN}missing").status == HTTPStatus.NOT_FOUND


def test_a_body_that_is_no_json_is_refused(answerer):
    answer = send(answerer, HttpMethod.POST, PlanBuilderRoute.PLANS, b"{not json")
    assert answer.status == HTTPStatus.BAD_REQUEST
    assert ErrorKey.ERROR in json.loads(answer.body)


def test_a_body_beyond_the_document_limit_is_refused(answerer):
    body = b" " * (PlanBuilderLimits().maximum_document_bytes + 1)
    answer = send(answerer, HttpMethod.POST, PlanBuilderRoute.PLANS, body)
    assert answer.status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE


# %% constraints


def test_a_constraint_is_compiled_for_its_step(post):
    answer = post(
        PlanBuilderRoute.CONSTRAINT,
        ConstraintText(
            text="Keep the milk upright",
            step_action="transport",
            objects=["milk"],
        ).to_json(),
    )
    compiled = StepConstraint.from_json(json.loads(answer.body))
    assert compiled.monitor is not None and compiled.monitor_type is not None


def test_a_constraint_turns_on_a_switch_of_the_steps_action(post):
    answer = post(
        PlanBuilderRoute.CONSTRAINT,
        ConstraintText(
            text="Look where it operates", step_action="transport"
        ).to_json(),
    )
    compiled = StepConstraint.from_json(json.loads(answer.body))
    assert compiled.switch == ConstraintCompiler.of_file().rule_for("look at").switch


def test_a_constraint_on_an_action_the_workspace_lacks_turns_on_nothing(post):
    answer = post(
        PlanBuilderRoute.CONSTRAINT,
        ConstraintText(text="Look where it operates", step_action="search").to_json(),
    )
    assert StepConstraint.from_json(json.loads(answer.body)).switch is None


def test_a_blank_constraint_is_refused(post):
    answer = post(PlanBuilderRoute.CONSTRAINT, ConstraintText(text=" ").to_json())
    assert answer.status == HTTPStatus.UNPROCESSABLE_ENTITY


# %% demos


def test_the_demo_carries_the_plan_and_its_environment(post, plan, scenes):
    answer = post(PlanBuilderRoute.DEMO, plan.to_json())
    source = DemoSource.from_json(json.loads(answer.body))
    lab = scenes.directory_of(plan.environment).path / plan.environment
    assert answer.status == HTTPStatus.OK
    assert source.file_name == f"{plan.name}{DEMO_SUFFIX}"
    assert demo_document(source.source) == DemoDocument(
        plan=plan, environment_directory=str(lab.resolve())
    )


def test_an_unfinished_plan_has_no_demo(post, read_plan):
    answer = post(PlanBuilderRoute.DEMO, read_plan("unfinished.json").to_json())
    assert answer.status == HTTPStatus.UNPROCESSABLE_ENTITY


def test_a_plan_in_a_bundle_holding_a_robot_has_no_demo(post, plan):
    plan.environment = "cell"
    answer = post(PlanBuilderRoute.DEMO, plan.to_json())
    assert answer.status == HTTPStatus.UNPROCESSABLE_ENTITY


def test_a_written_demo_lies_in_the_output_directory(post, plan, output):
    saved = SavedDemo.from_json(
        json.loads(post(PlanBuilderRoute.DEMOS, plan.to_json()).body)
    )
    assert saved.path == str((output / f"{plan.name}{DEMO_SUFFIX}").resolve())
    assert saved.path in saved.command


# %% runs


def test_the_demo_process_is_idle_before_a_run(get):
    status = RunStatus.from_json(json.loads(get(PlanBuilderRoute.RUN).body))
    assert status.state is RunState.IDLE


def test_a_run_is_started_and_stopped(serve, output, workspace_loader, plan):
    plugin = PlanBuilderPlugin(
        environment={PlanBuilderVariable.OUTPUT: str(output)},
        workspace=workspace_loader,
        template=DemoTemplate(DATASET / "templates" / "waiting_demo.py"),
    )
    answerer = serve(plugin)

    def post(route, body):
        return send(answerer, HttpMethod.POST, route, json.dumps(body).encode())

    def get(route):
        return send(answerer, HttpMethod.GET, route)

    started = RunStatus.from_json(
        json.loads(
            post(
                PlanBuilderRoute.RUN,
                RunRequest(plan=plan, mode=RunMode.STAGE).to_json(),
            ).body
        )
    )
    stopped = RunStatus.from_json(json.loads(post(PlanBuilderRoute.RUN_STOP, {}).body))
    assert started.state is RunState.RUNNING and started.mode is RunMode.STAGE
    assert stopped.state is RunState.STOPPED
    assert RunStatus.from_json(json.loads(get(PlanBuilderRoute.RUN).body)) == stopped


def test_an_unfinished_plan_is_not_run(post, read_plan):
    answer = post(
        PlanBuilderRoute.RUN,
        RunRequest(plan=read_plan("unfinished.json")).to_json(),
    )
    assert answer.status == HTTPStatus.UNPROCESSABLE_ENTITY


def test_a_demo_document_names_no_environment_for_an_empty_floor(post, plan):
    plan.environment = None
    answer = post(PlanBuilderRoute.DEMO, plan.to_json())
    source = DemoSource.from_json(json.loads(answer.body))
    assert demo_document(source.source) == DemoDocument(plan=plan)


def test_the_plugin_has_an_entry_in_the_viewers_navigation():
    navigation = PlanBuilderPlugin(environment={}).info().navigation
    assert navigation.title == NAVIGATION_TITLE
    assert navigation.group == NavigationGroup.BUILDER
    assert (
        navigation.page
        == f"{ViewerRoute.PLUGIN_FILES}{PlanBuilderPlugin(environment={}).name()}/{PlanBuilderFile.PAGE}"
    )
