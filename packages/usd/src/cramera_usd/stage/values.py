"""
Values read from a stage, as plain Python and JSON values.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy
from pxr import Gf, Sdf
from typing_extensions import Any, Optional

from cramera_usd.scene.materials import ShaderInputValue

# %% values


@dataclass
class StageValue:
    """
    Converts a value read from a stage into a plain Python value.
    """

    value: Any
    """
    The value as ``pxr`` returns it.
    """

    def shader_value(self) -> Optional[ShaderInputValue]:
        """
        :return: The value as a shader input: a number, flag, token or tuple of numbers,
            or None for a value of another kind.
        """
        if isinstance(self.value, (bool, int, float, str)):
            return self.value
        if self.value is None:
            return None
        converted = self.json_value()
        if isinstance(converted, list) and all(
            isinstance(item, (int, float)) for item in converted
        ):
            return tuple(float(item) for item in converted)
        return None

    def json_value(self) -> Any:
        """
        :return: The value as JSON: arrays and vectors become lists, asset paths their
            path, quaternions their real part followed by their imaginary part.
        """
        value = self.value
        if isinstance(value, (bool, int, float, str)) or value is None:
            return value
        if isinstance(value, Sdf.AssetPath):
            return value.path
        if isinstance(value, (Gf.Quatd, Gf.Quatf, Gf.Quath)):
            return [
                float(value.GetReal()),
                *(float(component) for component in value.GetImaginary()),
            ]
        if isinstance(value, Iterable):
            return [StageValue(item).json_value() for item in value]
        return numpy.asarray(value).tolist()
