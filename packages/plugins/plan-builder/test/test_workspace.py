"""
Finding out whether the CRAM workspace is importable, and what a workspace serves.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.machinery import ModuleSpec
from pathlib import Path

import pytest
from typing_extensions import Dict

from cramera.exceptions import FileNotInDirectory, PathOutsideDirectory
from cramera_plan_builder.exceptions import CramUnavailable
from cramera_plan_builder.workspace import (
    CramModule,
    CramModules,
    MissingWorkspace,
    WorkspaceLoader,
)
from cramera_protocol.plan_builder import ActionCatalog

from .dataset.given_workspace import DATASET, GivenWorkspace

LIBRARY = DATASET / "object_library"
"""
The test object library.
"""


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
    assert workspace.surface_types() == []
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


# %% object libraries


@dataclass(frozen=True)
class LibraryWorkspace(GivenWorkspace):
    """
    The test workspace with the test object library beside its meshes.
    """

    def object_roots(self) -> Dict[str, Path]:
        return {LIBRARY.name: LIBRARY}


@pytest.mark.parametrize(
    "path",
    [
        "objects/cup/model.urdf",
        "objects/cup/assets/cup.obj",
        "objects/cup/assets/cup.mtl",
    ],
)
def test_a_library_serves_its_descriptions_and_meshes(path):
    requested = f"{LIBRARY.name}/{path}"
    assert LibraryWorkspace().object_file(requested) == (LIBRARY / path).resolve()


def test_a_library_serves_nothing_but_descriptions_meshes_and_textures():
    with pytest.raises(FileNotInDirectory):
        LibraryWorkspace().object_file(f"{LIBRARY.name}/objects/cup/notes.md")


def test_a_path_leaving_the_library_is_refused():
    with pytest.raises(PathOutsideDirectory):
        LibraryWorkspace().object_file(f"{LIBRARY.name}/../workspace.json")


def test_a_path_naming_no_library_is_read_from_the_mesh_directory():
    assert (
        LibraryWorkspace().object_file("milk.stl")
        == (DATASET / "objects" / "milk.stl").resolve()
    )
    with pytest.raises(FileNotInDirectory):
        LibraryWorkspace().object_file("elsewhere/objects/cup/model.urdf")
