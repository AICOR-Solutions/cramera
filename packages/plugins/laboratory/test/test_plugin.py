"""
The laboratory's routes as the viewer serves them.
"""

from __future__ import annotations

import json
from http import HTTPStatus

import pytest

from cramera.application import ViewerApplication
from cramera.http.messages import HttpMethod, Request
from cramera.http.origin import OriginPolicy
from cramera.http.server import RequestAnswerer
from cramera.scenes import SceneCatalog, SceneDirectory, SceneSource
from cramera_laboratory.devices import DeviceFile, LaboratoryDevice
from cramera_laboratory.plugin import COMMAND_ROUTES, LaboratoryPlugin
from cramera_laboratory.resources import LaboratoryResource
from cramera_protocol.laboratory.runs import (
    DemoRoute,
    LaboratoryDemo,
    TaskRun,
    TaskRunState,
)
from cramera_protocol.laboratory.physics import (
    DeviceCatalog,
    InstalledLaboratory,
    LaboratoryCatalog,
    LaboratoryChoiceKey,
    LaboratoryFile,
    LaboratoryName,
    LaboratoryRoute,
    LiquidRequestKey,
    SimulationAnswer,
    SimulationState,
    TargetRequestKey,
)
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.viewer import NavigationGroup, ViewerInfo, ViewerRoute

from .conftest import HEADERS, send
from .dataset.simulations import RecordingFactory

CHOICE = {LaboratoryChoiceKey.LABORATORY: LaboratoryResource.BENCH}
"""
A request naming the bench laboratory.
"""

TARGET = {
    TargetRequestKey.KEY: "tube_clear",
    TargetRequestKey.POSITION: [0.16, -0.065, 1.0],
}
"""
A pull target request.
"""


def decoded(response):
    """
    :param response: A JSON answer.
    :return: Its decoded body.
    """
    return json.loads(response.body)


# %% catalog


def test_the_catalog_lists_the_compact_laboratory(get):
    catalog = LaboratoryCatalog.from_json(decoded(get(LaboratoryRoute.LABORATORIES)))
    assert [entry.name for entry in catalog.laboratories] == [
        LaboratoryResource.BENCH,
    ]
    assert not any(entry.installed for entry in catalog.laboratories)
    assert catalog.physics_available
    assert catalog.laboratories[0].instruments == 0


def test_installing_makes_the_viewer_show_the_laboratory(get, post, locations):
    answer = post(LaboratoryRoute.INSTALL, CHOICE)
    scene = InstalledLaboratory.from_json(decoded(answer)).scene
    catalog = LaboratoryCatalog.from_json(decoded(get(LaboratoryRoute.LABORATORIES)))
    assert scene == LaboratoryResource.BENCH
    assert catalog.laboratories[0].installed
    assert (locations.local_scenes / scene / BundleFile.SCENE).is_file()


def test_an_unknown_laboratory_is_not_found(post):
    response = post(
        LaboratoryRoute.INSTALL, {LaboratoryChoiceKey.LABORATORY: "kitchen"}
    )
    assert response.status == HTTPStatus.NOT_FOUND


def test_the_devices_and_their_files_are_served(get):
    catalog = DeviceCatalog.from_json(decoded(get(LaboratoryRoute.DEVICES)))
    assert len(catalog.devices) == len(LaboratoryDevice)
    response = get(
        f"{LaboratoryRoute.DEVICE_FILES}{LaboratoryDevice.SCALE}/{DeviceFile.DESCRIPTION}"
    )
    assert response.status == HTTPStatus.OK and b"<robot" in response.body


@pytest.mark.parametrize(
    "path, status",
    [
        (f"{LaboratoryDevice.SCALE}/../centrifuge/model.urdf", HTTPStatus.FORBIDDEN),
        ("toaster/model.urdf", HTTPStatus.NOT_FOUND),
    ],
)
def test_device_files_stay_inside_their_folder(get, path, status):
    assert get(f"{LaboratoryRoute.DEVICE_FILES}{path}").status == status


# %% task demos


@pytest.mark.parametrize("demo", list(LaboratoryDemo))
def test_every_demo_names_its_recording_on_its_own_route(get, demo):
    run = TaskRun.from_json(decoded(get(demo.route(DemoRoute.STATE))))
    assert run.scene == demo.recording


def test_an_existing_recording_is_not_run_again(post, locations):
    demo = LaboratoryDemo.TRANSFER
    bundle = locations.local_scenes / demo.recording
    bundle.mkdir(parents=True)
    (bundle / BundleFile.SCENE).write_text("{}", encoding="utf-8")
    started = TaskRun.from_json(decoded(post(demo.route(DemoRoute.START), {})))
    stopped = TaskRun.from_json(decoded(post(demo.route(DemoRoute.STOP), {})))
    assert started.state is stopped.state is TaskRunState.RECORDED


# %% simulation


def test_the_state_of_an_idle_session(get):
    answer = SimulationAnswer.from_json(decoded(get(LaboratoryRoute.STATE)))
    assert answer.state is SimulationState.IDLE


def test_starting_and_commanding_the_simulation(post, factory):
    started = SimulationAnswer.from_json(decoded(post(LaboratoryRoute.START, CHOICE)))
    commanded = post(LaboratoryRoute.TARGET, TARGET)
    stopped = SimulationAnswer.from_json(decoded(post(LaboratoryRoute.STOP, {})))
    assert started.state is SimulationState.RUNNING
    assert commanded.status == HTTPStatus.OK
    assert factory.created[0].commands[0].key == TARGET[TargetRequestKey.KEY]
    assert stopped.state is SimulationState.IDLE


@pytest.mark.parametrize("command", COMMAND_ROUTES, ids=lambda command: command.route)
def test_every_command_needs_a_running_simulation(post, command):
    assert post(command.route, {}).status in (
        HTTPStatus.CONFLICT,
        HTTPStatus.BAD_REQUEST,
    )


def test_a_refused_operation_answers_conflict(post):
    post(LaboratoryRoute.START, CHOICE)
    response = post(LaboratoryRoute.TARE, {})
    post(LaboratoryRoute.STOP, {})
    assert response.status == HTTPStatus.CONFLICT


@pytest.mark.parametrize(
    "body",
    [b"{not json", json.dumps({LiquidRequestKey.KEY: "tube_clear"}).encode()],
)
def test_a_malformed_body_is_a_bad_request(answerer, post, body):
    post(LaboratoryRoute.START, CHOICE)
    response = send(answerer, HttpMethod.POST, LaboratoryRoute.LIQUID, body)
    post(LaboratoryRoute.STOP, {})
    assert response.status == HTTPStatus.BAD_REQUEST


def test_without_mujoco_the_start_is_unavailable(locations):
    application = ViewerApplication(
        catalog=SceneCatalog(
            [SceneDirectory(locations.local_scenes, SceneSource.LOCAL)]
        ),
        locations=locations,
        plugins=[LaboratoryPlugin(factory=RecordingFactory(installed=False))],
    )
    answerer = RequestAnswerer(router=application.router(), policy=OriginPolicy())
    response = send(
        answerer, HttpMethod.POST, LaboratoryRoute.START, json.dumps(CHOICE).encode()
    )
    assert response.status == HTTPStatus.SERVICE_UNAVAILABLE


def test_the_viewer_lists_the_laboratory_as_its_own_page(answerer):
    response = answerer.answer(
        Request(method=HttpMethod.GET, path=ViewerRoute.INFO, headers=HEADERS)
    )
    info = ViewerInfo.from_json(decoded(response))
    [plugin] = info.plugins
    assert plugin.name == LaboratoryName.PLUGIN
    assert plugin.module is None
    assert plugin.navigation.page == "/plugins/laboratory/laboratory.html"
    assert plugin.navigation.title == "Medical lab"


def test_the_plugin_has_its_own_laboratory_navigation_entry():
    navigation = (
        LaboratoryPlugin(factory=RecordingFactory(installed=False)).info().navigation
    )
    assert navigation.group is NavigationGroup.LABORATORY
    assert navigation.page.endswith(LaboratoryFile.PAGE)


def test_the_robot_preview_explains_missing_local_dependencies(post, monkeypatch):
    from cramera_laboratory.task_runs import TaskProcess

    monkeypatch.setattr(TaskProcess, "available", lambda self: False)
    response = post(LaboratoryRoute.PREVIEW, {})
    assert response.status == HTTPStatus.SERVICE_UNAVAILABLE
    assert "CRAM" in decoded(response)["error"]
