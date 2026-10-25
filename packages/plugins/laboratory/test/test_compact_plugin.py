"""
The compact medical lab's catalog, default tab and owned worker lifecycle.
"""

from __future__ import annotations

import json
import sys
from http import HTTPStatus

import pytest

from cramera.http.messages import HttpMethod, Request
from cramera.plugins import PluginContext, PluginRoute
from cramera.scenes import SceneCatalog, SceneDirectory, SceneSource
from cramera_laboratory.plugin import LaboratoryPlugin
from cramera_laboratory.resources import LaboratoryResource
from cramera_laboratory.exceptions import DemoBusy
from cramera_laboratory.task_runs import TaskProcess
from cramera_protocol.laboratory.physics import (
    DeviceCatalog,
    LaboratoryCatalog,
    LaboratoryChoiceKey,
    LaboratoryRoute,
    SimulationAnswer,
    SimulationState,
)
from cramera_protocol.laboratory.runs import DemoRoute, LaboratoryDemo, TaskRunState

from .conftest import DATASET

# %% compact catalog


def test_only_the_compact_laboratory_is_available(get):
    response = get(LaboratoryRoute.LABORATORIES)
    assert response.status == HTTPStatus.OK
    catalog = LaboratoryCatalog.from_json(json.loads(response.body))
    assert [entry.name for entry in catalog.laboratories] == [LaboratoryResource.BENCH]


@pytest.mark.parametrize("route", [LaboratoryRoute.INSTALL, LaboratoryRoute.START])
def test_expanded_laboratory_requests_are_rejected(post, factory, locations, route):
    response = post(route, {LaboratoryChoiceKey.LABORATORY: "aicor_medical_lab_large"})
    assert response.status == HTTPStatus.NOT_FOUND
    assert factory.created == []
    assert not locations.local_scenes.exists()


def test_only_compact_devices_are_served(get):
    response = get(LaboratoryRoute.DEVICES)
    assert response.status == HTTPStatus.OK
    catalog = DeviceCatalog.from_json(json.loads(response.body))
    assert {device.name for device in catalog.devices} == {
        "centrifuge",
        "dual_dispenser",
        "scale",
        "tube_rack",
        "refrigerator",
    }


def test_the_medical_lab_has_its_own_page_instead_of_a_scene_tab(factory):
    plugin = LaboratoryPlugin(factory=factory)
    assert plugin.navigation().page == "laboratory.html"
    assert plugin.module() is None


# %% shutdown


@pytest.fixture
def plugin_routes(locations, factory):
    plugin = LaboratoryPlugin(factory=factory)
    context = PluginContext(
        catalog=SceneCatalog(
            [SceneDirectory(locations.local_scenes, SceneSource.LOCAL)]
        ),
        locations=locations,
    )
    routes = plugin.routes(context)
    owner = next(
        route.handler.__self__
        for route in routes
        if isinstance(route, PluginRoute) and route.path == LaboratoryRoute.START
    )
    yield plugin, context, owner
    owner.session.stop()
    for process in owner.demos.values():
        process.stop()
    plugin.close()


def test_closing_the_plugin_joins_its_simulation_and_releases_the_object(
    plugin_routes, bench_laboratory, factory
):
    plugin, _, owner = plugin_routes
    owner.session.start(bench_laboratory)
    worker = owner.session.worker
    plugin.close()
    assert not worker.is_alive()
    assert owner.session.worker is None
    assert factory.created[0].commands == [None]
    plugin.close()
    assert factory.created[0].commands == [None]


def test_registering_routes_again_keeps_the_running_session(
    plugin_routes, bench_laboratory
):
    plugin, context, owner = plugin_routes
    owner.session.start(bench_laboratory)
    state_route = next(
        route
        for route in plugin.routes(context)
        if isinstance(route, PluginRoute) and route.path == LaboratoryRoute.STATE
    )
    response = state_route.handler(
        Request(method=HttpMethod.GET, path=LaboratoryRoute.STATE)
    )
    assert (
        SimulationAnswer.from_json(json.loads(response.body)).state
        is SimulationState.RUNNING
    )


def waiting(demo, locations) -> TaskProcess:
    """
    :param demo: The demo the stand-in stands in for.
    :param locations: Where the viewer keeps its scenes.
    :return: A stand-in that runs until it is ended.
    """
    return TaskProcess(
        command=[sys.executable, str(DATASET / "tasks" / "waiting_task.py")],
        demo=demo,
        locations=locations,
        packages=(),
    )


@pytest.mark.parametrize("demo", list(LaboratoryDemo))
def test_closing_the_plugin_ends_its_running_demo(plugin_routes, locations, demo):
    plugin, _, owner = plugin_routes
    owner.demos[demo] = waiting(demo, locations)
    assert owner.demos[demo].start().state is TaskRunState.RUNNING
    process = owner.demos[demo].process
    plugin.close()
    assert process.poll() is not None


def test_a_second_demo_does_not_start_while_one_runs(plugin_routes, locations):
    plugin, context, owner = plugin_routes
    for demo in LaboratoryDemo:
        owner.demos[demo] = waiting(demo, locations)
    owner.demos[LaboratoryDemo.TRANSFER].start()
    start = next(
        route
        for route in plugin.routes(context)
        if isinstance(route, PluginRoute)
        and route.path == LaboratoryDemo.WORKFLOW.route(DemoRoute.START)
    )
    with pytest.raises(DemoBusy) as refused:
        start.handler(Request(method=HttpMethod.POST, path=start.path, body=b"{}"))
    assert refused.value.running is LaboratoryDemo.TRANSFER
    assert owner.demos[LaboratoryDemo.WORKFLOW].process is None


def test_transfer_is_stopped_if_releasing_the_simulation_fails(
    plugin_routes, locations, monkeypatch
):
    plugin, _, owner = plugin_routes
    owner.demos[LaboratoryDemo.TRANSFER] = waiting(LaboratoryDemo.TRANSFER, locations)
    owner.demos[LaboratoryDemo.TRANSFER].start()
    process = owner.demos[LaboratoryDemo.TRANSFER].process

    def fail_to_stop():
        raise RuntimeError("simulation could not release its target")

    with monkeypatch.context() as patch:
        patch.setattr(owner.session, "stop", fail_to_stop)
        with pytest.raises(RuntimeError):
            plugin.close()
    assert process.poll() is not None


def test_closing_before_routes_are_registered_is_safe(factory):
    LaboratoryPlugin(factory=factory).close()
