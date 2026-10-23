"""
Finding out whether the CRAM workspace is importable, and what a workspace serves.
"""

from __future__ import annotations

from importlib.machinery import ModuleSpec

import pytest

from cramera.exceptions import FileNotInDirectory, PathOutsideDirectory
from cramera_plan_builder.exceptions import CramUnavailable
from cramera_plan_builder.workspace import (
    CramModule,
    CramModules,
    MissingWorkspace,
    WorkspaceLoader,
)
from cramera_protocol.plan_builder import ActionCatalog

from .dataset.given_workspace import DATASET


def finder_without(*absent: CramModule):
    """
    :param absent: Modules the finder does not find.
    :return: A finder that finds every other module as code.
    """
    return lambda name: (
        None if name in absent else ModuleSpec(name, loader=None, origin=f"{name}.py")
    )


# %% modules


def test_modules_the_finder_does_not_find_are_missing():
    modules = CramModules(finder=finder_without(CramModule.CORAPLEX))
    assert modules.missing() == [CramModule.CORAPLEX.value]


def test_a_directory_sharing_a_modules_name_is_not_the_module():
    modules = CramModules(
        finder=lambda name: ModuleSpec(name, loader=None, origin=None)
    )
    assert modules.missing() == [module.value for module in CramModule]


def test_without_a_module_the_loader_answers_the_missing_workspace():
    loader = WorkspaceLoader(
        modules=CramModules(finder=finder_without(CramModule.KRROOD))
    )
    workspace = loader.workspace()
    assert workspace == MissingWorkspace([CramModule.KRROOD.value])
    assert loader.workspace() is workspace


# %% the missing workspace


def test_the_missing_workspace_offers_nothing_and_names_what_is_missing():
    workspace = MissingWorkspace([CramModule.CORAPLEX.value])
    assert workspace.robots() == [] and workspace.objects() == []
    assert workspace.torso_states() == [] and workspace.surface_types() == []
    assert workspace.action_catalog() == ActionCatalog()
    assert workspace.missing() == [CramModule.CORAPLEX.value]
    with pytest.raises(CramUnavailable) as refusal:
        workspace.object_file("milk.stl")
    assert refusal.value.missing == workspace.missing()


# %% object files


@pytest.mark.parametrize("name", ["milk.stl", "cup.obj", "cup.mtl"])
def test_meshes_and_their_material_libraries_are_served(given_workspace, name):
    assert given_workspace.object_file(name) == (DATASET / "objects" / name).resolve()


def test_a_file_of_another_kind_is_not_served(given_workspace):
    with pytest.raises(FileNotInDirectory):
        given_workspace.object_file("notes.txt")


def test_a_file_outside_the_object_directory_is_not_served(given_workspace):
    with pytest.raises(PathOutsideDirectory):
        given_workspace.object_file("../workspace.json")


def test_an_installed_workspace_names_nothing_missing(given_workspace):
    assert given_workspace.missing() == []
