"""
Selecting this package's live visualization as coraplex's cramera backend.

coraplex's ``WorldVisualization`` starts its cramera backend by importing
``LiveVisualization`` from the module ``cramera.live.visualization`` and creating it
with ``world=``. A registration puts a module of that name in place for as long as it is
entered, so a demo that selects the backend runs unchanged.
"""

from __future__ import annotations

import os
import sys
import types
from dataclasses import dataclass, field
from enum import StrEnum

from typing_extensions import Callable, Optional

from cramera_cram.visualization import LiveVisualization

# %% names


class CoraplexBackend(StrEnum):
    """
    The names coraplex selects and imports its cramera backend by.
    """

    VARIABLE = "CORAPLEX_VISUALIZATION"
    """
    The environment variable naming the backend.
    """

    VALUE = "cramera"
    """
    The value selecting the cramera backend.
    """

    MODULE = "cramera.live.visualization"
    """
    The module coraplex imports the backend class from.
    """

    CLASS = "LiveVisualization"
    """
    The class coraplex creates with ``world=`` and starts.
    """


VisualizationFactory = Callable[..., LiveVisualization]
"""
Creates the visualization of a world, called as ``factory(world=world)``.
"""

# %% registration


@dataclass
class CoraplexBackendRegistration:
    """
    Selects the cramera backend and makes coraplex create its visualizations through a
    factory while entered; leaving restores the environment variable and the module.
    """

    factory: VisualizationFactory = LiveVisualization
    """
    Creates each visualization coraplex asks for.
    """

    previous_selection: Optional[str] = field(default=None, init=False)
    """
    The value the environment variable had before, if any.
    """

    previous_module: Optional[types.ModuleType] = field(default=None, init=False)
    """
    The module the registration replaced, if any.
    """

    def __enter__(self) -> CoraplexBackendRegistration:
        self.previous_selection = os.environ.get(CoraplexBackend.VARIABLE)
        self.previous_module = sys.modules.get(CoraplexBackend.MODULE)
        module = types.ModuleType(CoraplexBackend.MODULE, __doc__)
        vars(module)[CoraplexBackend.CLASS] = self.factory
        sys.modules[CoraplexBackend.MODULE] = module
        os.environ[CoraplexBackend.VARIABLE] = CoraplexBackend.VALUE
        return self

    def __exit__(self, *exception: object) -> None:
        sys.modules.pop(CoraplexBackend.MODULE, None)
        if self.previous_module is not None:
            sys.modules[CoraplexBackend.MODULE] = self.previous_module
        os.environ.pop(CoraplexBackend.VARIABLE, None)
        if self.previous_selection is not None:
            os.environ[CoraplexBackend.VARIABLE] = self.previous_selection
