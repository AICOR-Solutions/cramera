"""
Only cramera-cram, of the repository's packages, imports the CRAM workspace, as
``AGENTS.md`` asks: every Python file outside ``packages/cram`` is read for imports of a
CRAM package, without importing anything.
"""

from __future__ import annotations

import ast
from pathlib import Path

from typing_extensions import Dict, FrozenSet, Iterator, List

PACKAGES = Path(__file__).resolve().parents[2]
"""
The repository's ``packages`` directory.
"""

CRAMERA_CRAM = PACKAGES / "cram"
"""
The package that may import CRAM.
"""

SKIPPED_DIRECTORIES = frozenset({"build", "node_modules", "__pycache__"})
"""
Directories holding copies or no sources of the packages, which are not read.
"""

CRAM_PACKAGES = frozenset(
    {
        "coraplex",
        "semantic_digital_twin",
        "giskardpy",
        "krrood",
        "segmind",
        "robokudo",
        "physics_simulators",
        "probabilistic_model",
        "random_events",
    }
)
"""
The top-level packages of the CRAM workspace.
"""

NOT_MOVED_YET: Dict[str, FrozenSet[str]] = {
    "questions/src/cramera_questions/entity.py": frozenset({"krrood"}),
    "questions/src/cramera_questions/knowledge.py": frozenset({"krrood"}),
    "questions/src/cramera_questions/runner.py": frozenset({"krrood"}),
    "questions/src/cramera_questions/verbalization.py": frozenset({"krrood"}),
    "questions/src/cramera_questions/vocabulary.py": frozenset({"krrood"}),
    "questions/test/test_verbalization.py": frozenset({"krrood"}),
    "questions/test/test_workspace_classes.py": frozenset({"krrood"}),
}
"""
The files that still import CRAM packages, relative to :data:`PACKAGES`, with what they
import; ``AGENTS.md`` lists them as the packages to move into cramera-cram.

A file is taken off once it imports none of them.
"""


def python_files() -> Iterator[Path]:
    """
    :return: Every Python file of the repository's packages outside cramera-cram.
    """
    for path in sorted(PACKAGES.rglob("*.py")):
        relative = path.relative_to(PACKAGES)
        if path.is_relative_to(CRAMERA_CRAM) or SKIPPED_DIRECTORIES.intersection(
            relative.parts
        ):
            continue
        yield path


def imported_cram_packages(path: Path) -> FrozenSet[str]:
    """
    :param path: A Python file.
    :return: The CRAM packages it imports anywhere, behind ``TYPE_CHECKING`` and inside
        functions included.
    """
    imported: List[str] = []
    for node in ast.walk(ast.parse(path.read_bytes(), filename=str(path))):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.append(node.module)
    return frozenset(
        name.split(".")[0] for name in imported if name.split(".")[0] in CRAM_PACKAGES
    )


def cram_imports() -> Dict[str, FrozenSet[str]]:
    """
    :return: The files outside cramera-cram that import CRAM packages, relative to
        :data:`PACKAGES`, with what they import.
    """
    found = {
        path.relative_to(PACKAGES).as_posix(): imported_cram_packages(path)
        for path in python_files()
    }
    return {file: packages for file, packages in found.items() if packages}


def test_only_cramera_cram_imports_cram():
    assert cram_imports() == NOT_MOVED_YET


def test_an_import_of_cram_is_found_wherever_it_stands(tmp_path):
    source = tmp_path / "module.py"
    source.write_text(
        "from typing import TYPE_CHECKING\n"
        "import json, coraplex.plans\n"
        "if TYPE_CHECKING:\n"
        "    from krrood.utils import recursive_subclasses\n"
        "def later():\n"
        "    import semantic_digital_twin.world\n"
        "from .coraplex import relative\n"
        "from cramera_cram.plans import command\n",
        encoding="utf-8",
    )
    assert imported_cram_packages(source) == {
        "coraplex",
        "krrood",
        "semantic_digital_twin",
    }
