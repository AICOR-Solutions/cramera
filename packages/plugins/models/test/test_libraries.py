"""
Finding out whether the circuit libraries are installed, and the workbench that follows
from it.
"""

from __future__ import annotations

from importlib.machinery import ModuleSpec

import pytest

from cramera_models.exceptions import CircuitLibrariesMissing
from cramera_models.libraries import CircuitLibraries, CircuitLibrary
from cramera_models.workbench import UnavailableWorkbench, WorkbenchChoice
from cramera_protocol.models import (
    ModelUpload,
    ModeRequest,
    PosteriorRequest,
    ProbabilityRequest,
)

# %% finders


def found_with_origin(name: str) -> ModuleSpec:
    """
    :param name: A module name.
    :return: The specification of a module with code of its own.
    """
    return ModuleSpec(name, loader=None, origin=f"/site-packages/{name}/__init__.py")


def found_as_namespace(name: str) -> ModuleSpec:
    """
    :param name: A module name.
    :return: The specification of a directory that only shares the name.
    """
    return ModuleSpec(name, loader=None, origin=None)


def plotly_missing(name: str) -> ModuleSpec | None:
    """
    :param name: A module name.
    :return: No specification for plotly, a module with code for the others.
    """
    return None if name == CircuitLibrary.PLOTLY else found_with_origin(name)


# %% libraries


def test_nothing_is_missing_when_every_module_is_found():
    assert CircuitLibraries(finder=found_with_origin).missing() == []


def test_a_module_that_is_not_found_is_missing():
    assert CircuitLibraries(finder=plotly_missing).missing() == [CircuitLibrary.PLOTLY]


def test_a_directory_sharing_a_module_name_is_not_the_module():
    assert CircuitLibraries(finder=found_as_namespace).missing() == list(CircuitLibrary)


# %% choice


def test_without_the_libraries_the_workbench_names_them():
    workbench = WorkbenchChoice(CircuitLibraries(finder=plotly_missing)).workbench()
    assert workbench == UnavailableWorkbench([CircuitLibrary.PLOTLY])


def test_with_the_libraries_the_circuit_workbench_is_chosen(mimic_workbench_module):
    workbench = WorkbenchChoice(CircuitLibraries(finder=found_with_origin)).workbench()
    assert isinstance(workbench, mimic_workbench_module.CircuitWorkbench)


@pytest.mark.parametrize(
    "ask",
    [
        lambda workbench: workbench.state(),
        lambda workbench: workbench.load(ModelUpload(name="a.json", text="{}")),
        lambda workbench: workbench.probability(ProbabilityRequest()),
        lambda workbench: workbench.posterior(PosteriorRequest(variables=[])),
        lambda workbench: workbench.mode(ModeRequest()),
    ],
)
def test_every_question_to_an_unavailable_workbench_names_the_missing_modules(ask):
    with pytest.raises(CircuitLibrariesMissing) as refused:
        ask(UnavailableWorkbench([CircuitLibrary.PLOTLY]))
    assert refused.value.modules == [CircuitLibrary.PLOTLY]
