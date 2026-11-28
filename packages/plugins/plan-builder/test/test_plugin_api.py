"""
The plugin API facade: what a plugin built on the plan builder imports, in one module.
"""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path

from cramera.plugins import PluginContext
from cramera_plan_builder import plugin_api
from cramera_plan_builder.plugin_api import (
    PlanBuilderServices,
    api_version,
)
from cramera_protocol.object_library import LibraryVariable
from cramera_protocol.plan_builder import PlanDocument, PlanRecord
from cramera_protocol.robot_profile import RobotProfileVariable

PROFILE = Path(__file__).parent / "dataset" / "profile" / "tracy.json"
"""
The test dataset's profile of Tracy.
"""


def test_every_name_the_facade_exports_is_importable():
    for name in plugin_api.__all__:
        assert getattr(plugin_api, name) is not None


def test_the_facade_names_the_plugin_api_version_the_viewer_checks():
    assert api_version().major == 1
    assert plugin_api.ViewerPlugin.api_version(None) == api_version()


def test_the_services_read_the_profile_the_plans_and_the_objects_of_the_environment(
    tmp_path, scenes, locations
):
    library = tmp_path / "library" / "objects" / "cubes"
    library.mkdir(parents=True)
    (library / "collection.json").write_text(
        json.dumps({"objects": [{"slug": "red_cube", "name": "Red cube"}]})
    )
    services = PlanBuilderServices.of(
        PluginContext(catalog=scenes, locations=locations),
        {
            RobotProfileVariable.PROFILE: str(PROFILE),
            LibraryVariable.LIBRARIES: str(tmp_path / "library"),
        },
    )
    assert services.profile.profile.robot == "tracy"
    assert services.profile_path == PROFILE
    assert services.objects.description("x/red_cube/model.urdf").name == "Red cube"
    saved = services.plans.save(
        PlanRecord(identifier=None, document=PlanDocument(name="Tower", task="tower"))
    )
    assert services.plans.load(saved.identifier).document.task == "tower"
    assert services.plan_builder_page(saved.identifier).endswith(
        f"builder.html?plan={saved.identifier}"
    )


def test_without_a_profile_the_services_have_none(scenes, locations):
    services = PlanBuilderServices.of(
        PluginContext(catalog=scenes, locations=locations), {}
    )
    assert services.profile.profile is None
    assert services.profile_path is None


def test_the_facade_reaches_the_plan_builder_only_through_its_public_modules():
    source = Path(plugin_api.__file__).read_text("utf-8")
    imported = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    for module in imported:
        importlib.import_module(module)
    assert not any(module.startswith("cramera_bridge") for module in imported)
