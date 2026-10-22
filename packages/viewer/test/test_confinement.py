"""
Requested paths stay inside their directory.
"""

from __future__ import annotations

import pytest

from cramera.confinement import ConfinedDirectory
from cramera.exceptions import FileNotInDirectory, PathOutsideDirectory


@pytest.fixture
def directory(tmp_path):
    root = tmp_path / "bundle"
    (root / "meshes").mkdir(parents=True)
    (root / "meshes" / "base.stl").write_text("solid", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    return ConfinedDirectory(root)


def test_a_file_inside_is_found(directory):
    assert directory.file("meshes/base.stl").read_text(encoding="utf-8") == "solid"


@pytest.mark.parametrize(
    "requested",
    [
        "../secret.txt",
        "meshes/../../secret.txt",
        "/etc/passwd",
        "",
        "meshes\\..\\..\\secret.txt",
        "a\x00b",
    ],
)
def test_paths_leading_out_are_refused(directory, requested):
    with pytest.raises(PathOutsideDirectory):
        directory.file(requested)


def test_a_symbolic_link_leading_out_is_refused(directory, tmp_path):
    (directory.root / "link.txt").symlink_to(tmp_path / "secret.txt")
    with pytest.raises(PathOutsideDirectory):
        directory.file("link.txt")


def test_a_symbolic_link_inside_is_followed(directory):
    (directory.root / "alias.stl").symlink_to(directory.root / "meshes" / "base.stl")
    assert directory.file("alias.stl").name == "base.stl"


@pytest.mark.parametrize("requested", ["missing.stl", "meshes"])
def test_a_path_that_names_no_file_is_not_found(directory, requested):
    with pytest.raises(FileNotInDirectory):
        directory.file(requested)
