"""
Whether the libraries the workbench computes with are installed.

The decision is made by asking the import system whether it can find the modules, before
anything imports them. An absent library is then a value the plugin reads, not an import
error it has to catch, and the module that imports the libraries is only imported where
they are all found.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from enum import StrEnum
from importlib.machinery import ModuleSpec

from typing_extensions import Callable, List, Optional, Tuple

# %% libraries


class CircuitLibrary(StrEnum):
    """
    The top-level modules the workbench imports.
    """

    PROBABILISTIC_MODEL = "probabilistic_model"
    """
    Probabilistic circuits and their questions.
    """

    RANDOM_EVENTS = "random_events"
    """
    Variables, sets, intervals and events.
    """

    KRROOD = "krrood"
    """
    The JSON serializer circuit files are read with.
    """

    PLOTLY = "plotly"
    """
    The figures posteriors are drawn as.
    """


ModuleFinder = Callable[[str], Optional[ModuleSpec]]
"""
Finds a top-level module without importing it; :func:`importlib.util.find_spec` outside
of tests.
"""


@dataclass(frozen=True)
class CircuitLibraries:
    """
    Finds out which of the libraries are installed.
    """

    modules: Tuple[CircuitLibrary, ...] = tuple(CircuitLibrary)
    """
    The modules that must be installed.
    """

    finder: ModuleFinder = field(default=importlib.util.find_spec)
    """
    Finds a module without importing it.
    """

    def missing(self) -> List[str]:
        """
        :return: The modules that cannot be found, in the order of :attr:`modules`;
            a directory that only shares a module's name, which Python would import
            as an empty namespace package, does not count as the module.
        """
        return [
            module.value for module in self.modules if not self.is_installed(module)
        ]

    def is_installed(self, module: CircuitLibrary) -> bool:
        """
        :param module: A top-level module.
        :return: Whether a module with code of its own is found under that name.
        """
        specification = self.finder(module)
        return specification is not None and specification.origin is not None
