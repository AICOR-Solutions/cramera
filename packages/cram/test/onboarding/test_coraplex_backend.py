"""
Selecting this package's live visualization as coraplex's cramera backend.
"""

from __future__ import annotations

import importlib
import os
import sys
import types

from cramera_cram.coraplex_backend import CoraplexBackend, CoraplexBackendRegistration
from cramera_cram.visualization import LiveVisualization
from cramera_questions.workspace_classes import WorkspaceClassIndex

PREVIOUS_SELECTION = "rviz"
"""
A backend a process selected before the registration.
"""


def test_a_registration_selects_the_backend_while_entered(monkeypatch):
    monkeypatch.delenv(CoraplexBackend.VARIABLE, raising=False)
    with CoraplexBackendRegistration():
        selection = os.environ[CoraplexBackend.VARIABLE]
        module = importlib.import_module(CoraplexBackend.MODULE)
    assert selection == CoraplexBackend.VALUE
    assert vars(module)[CoraplexBackend.CLASS] is LiveVisualization
    assert CoraplexBackend.VARIABLE not in os.environ
    assert CoraplexBackend.MODULE not in sys.modules


def test_leaving_restores_what_the_registration_replaced(monkeypatch):
    previous_module = types.ModuleType(CoraplexBackend.MODULE)
    monkeypatch.setenv(CoraplexBackend.VARIABLE, PREVIOUS_SELECTION)
    monkeypatch.setitem(sys.modules, CoraplexBackend.MODULE, previous_module)
    with CoraplexBackendRegistration():
        pass
    assert os.environ[CoraplexBackend.VARIABLE] == PREVIOUS_SELECTION
    assert sys.modules[CoraplexBackend.MODULE] is previous_module


def test_coraplex_creates_its_visualization_through_the_factory(
    sliding_box, locations, monkeypatch, coraplex_visualization
):
    created = []

    def factory(world) -> LiveVisualization:
        visualization = LiveVisualization(
            world=world,
            port=0,
            locations=locations,
            read_ros_markers=False,
            class_index=WorkspaceClassIndex(),
        )
        created.append(visualization)
        return visualization

    monkeypatch.delenv(CoraplexBackend.VARIABLE, raising=False)
    with CoraplexBackendRegistration(factory=factory):
        visualization = coraplex_visualization.WorldVisualization.from_environment(
            sliding_box.world
        ).start()
    shown = visualization.cramera_visualization
    visualization.stop()
    assert created == [shown]
    assert shown.world is sliding_box.world
