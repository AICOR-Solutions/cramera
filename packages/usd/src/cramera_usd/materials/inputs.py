"""
Typed access to the authored inputs of a material.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from typing_extensions import Dict, Optional, Set, Tuple

from cramera_usd.materials.physically_based import WHITE, LinearColor
from cramera_usd.scene.materials import (
    AuthoredMaterial,
    ShaderInputValue,
    TextureFile,
)

# %% constants

COLOR_COMPONENTS = 3
"""
The number of components of a colour input.
"""

VECTOR_COMPONENTS = 2
"""
The number of components of a two-component input.
"""

# %% colours


@dataclass(frozen=True)
class TexturedColor:
    """
    A linear colour factor multiplied with an optional sRGB colour texture, as glTF
    gives a base colour.
    """

    factor: LinearColor
    """
    The linear colour, multiplying the texture when there is one.
    """

    texture: Optional[TextureFile] = None
    """
    The colour texture, or None for the factor alone.
    """

    def scaled(self, scale: float) -> TexturedColor:
        """
        :param scale: A multiplier.
        :return: The colour with its factor multiplied.
        """
        return replace(
            self, factor=tuple(component * scale for component in self.factor)
        )

    def mixed_with(self, other: TexturedColor, share: float) -> TexturedColor:
        """
        :param other: A colour to blend in.
        :param share: The share of the other colour, between 0 and 1.
        :return: The blend; only one texture can be drawn, so it keeps the texture of
            the colour with the larger share.
        """
        return TexturedColor(
            tuple(
                (1.0 - share) * own + share * blended
                for own, blended in zip(self.factor, other.factor)
            ),
            other.texture if share > 1.0 - share else self.texture,
        )


# %% inputs


@dataclass
class ShaderInputs:
    """
    Typed access to a material's authored inputs, keeping track of what was read.
    """

    material: AuthoredMaterial
    """
    The material whose inputs are read.
    """

    read: Set[str] = field(default_factory=set)
    """
    The names of the inputs a mapping asked for.
    """

    def number(self, name: str, default: float) -> float:
        """
        :param name: An input name.
        :param default: The shader's default for the input.
        :return: The input as a number, or the default when it is unset or no number.
        """
        self.read.add(name)
        value = self.material.inputs.get(name, default)
        return float(value) if isinstance(value, (bool, int, float)) else default

    def flag(self, name: str, default: bool) -> bool:
        """
        :param name: An input name.
        :param default: The shader's default for the input.
        :return: The input as a flag.
        """
        return bool(self.number(name, float(default)))

    def color(self, name: str, default: LinearColor) -> LinearColor:
        """
        :param name: An input name.
        :param default: The shader's default for the input.
        :return: The input as a colour, or the default when it is unset or no colour.
        """
        self.read.add(name)
        value = self.material.inputs.get(name, default)
        if not isinstance(value, tuple) or len(value) < COLOR_COMPONENTS:
            return default
        return float(value[0]), float(value[1]), float(value[2])

    def vector(self, name: str, default: Tuple[float, float]) -> Tuple[float, float]:
        """
        :param name: An input name.
        :param default: The shader's default for the input.
        :return: The input as two numbers, or the default when it is unset or no
            vector.
        """
        self.read.add(name)
        value = self.material.inputs.get(name, default)
        if not isinstance(value, tuple) or len(value) < VECTOR_COMPONENTS:
            return default
        return float(value[0]), float(value[1])

    def texture(self, name: str) -> Optional[TextureFile]:
        """
        :param name: An input name.
        :return: The input's texture, or None when it is unset or unresolved.
        """
        self.read.add(name)
        value = self.material.inputs.get(name)
        return value if isinstance(value, TextureFile) else None

    def textured_color(
        self, color_name: str, texture_name: str, default: LinearColor
    ) -> TexturedColor:
        """
        :param color_name: The name of a constant colour input.
        :param texture_name: The name of the texture input replacing it.
        :param default: The shader's default for the constant.
        :return: The texture when one is set, else the constant.
        """
        texture = self.texture(texture_name)
        if texture is not None:
            return TexturedColor(WHITE, texture)
        return TexturedColor(self.color(color_name, default))

    def unmapped(self, neutral: Dict[str, ShaderInputValue]) -> Tuple[str, ...]:
        """
        :param neutral: Inputs a mapping may ignore while they hold these values.
        :return: The authored inputs that were never read and differ from their neutral
            value, sorted.
        """
        return tuple(
            sorted(
                name
                for name, value in self.material.inputs.items()
                if name not in self.read
                and not (name in neutral and neutral[name] == value)
            )
        )
