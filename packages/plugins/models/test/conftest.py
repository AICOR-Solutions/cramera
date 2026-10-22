"""
Shared fixtures of the models plugin's tests.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest
from typing_extensions import Callable, Iterator

from cramera.application import ViewerApplication
from cramera.http.origin import OriginPolicy
from cramera.http.server import RequestAnswerer
from cramera.locations import DataLocations
from cramera.scenes import SceneCatalog
from cramera_models.libraries import CircuitLibraries
from cramera_models.plugin import ModelsPlugin
from cramera_models.workbench import Workbench, WorkbenchModule
from cramera_protocol.models import ModelUpload

from .dataset.circuit_library_mimic import CircuitLibraryMimic
from .dataset.recording_workbench import GivenWorkbenchChoice

DATASET = Path(__file__).parent / "dataset"
"""
The directory holding the circuit files and the questions.
"""

QUESTIONS = DATASET / "questions"
"""
The directory holding the request bodies.
"""


@pytest.fixture
def dataset() -> Path:
    """
    :return: The directory holding the circuit files and the questions.
    """
    return DATASET


@pytest.fixture
def question() -> Callable[[str], bytes]:
    """
    :return: Reads a request body of the questions directory by file name.
    """
    return lambda name: (QUESTIONS / name).read_bytes()


@pytest.fixture
def upload_of() -> Callable[[str], ModelUpload]:
    """
    :return: Makes the upload of a circuit file of the dataset by file name.
    """
    return lambda name: ModelUpload(
        name=name, text=(DATASET / name).read_text(encoding="utf-8")
    )


@pytest.fixture
def answerer_of(tmp_path: Path) -> Callable[[Workbench], RequestAnswerer]:
    """
    :return: Builds the viewer's request answerer with the models plugin answering
        from the given workbench, and no scenes.
    """

    def answerer(workbench: Workbench) -> RequestAnswerer:
        application = ViewerApplication(
            catalog=SceneCatalog([]),
            locations=DataLocations(data=tmp_path, shared_scenes=None),
            plugins=[ModelsPlugin(choice=GivenWorkbenchChoice(given=workbench))],
        )
        return RequestAnswerer(router=application.router(), policy=OriginPolicy())

    return answerer


# %% workbench modules


@pytest.fixture
def mimic_workbench_module(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """
    :return: The circuit workbench module imported over the library mimic; the
        modules it replaced are restored afterwards.
    """
    for name, module in CircuitLibraryMimic().modules().items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.delitem(sys.modules, WorkbenchModule.CIRCUITS, raising=False)
    yield importlib.import_module(WorkbenchModule.CIRCUITS)
    sys.modules.pop(WorkbenchModule.CIRCUITS, None)


@pytest.fixture
def circuit_workbench_module() -> ModuleType:
    """
    :return: The circuit workbench module over the installed libraries; the test is
        skipped where they are missing.
    """
    missing = CircuitLibraries().missing()
    if missing:
        pytest.skip(f"the circuit libraries {missing} are not installed")
    return importlib.import_module(WorkbenchModule.CIRCUITS)
