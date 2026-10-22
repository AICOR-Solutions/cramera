"""
Transmissive surfaces drawn as alpha-blended, reflecting approximations, for viewers
that cannot refract.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy
from PIL import Image
from scipy.integrate import quad
from typing_extensions import Optional

from cramera_usd.materials.channels import (
    ScalarChannel,
    SrgbTransfer,
    TextureChannelReader,
)
from cramera_usd.materials.physically_based import (
    AlphaMode,
    PhysicallyBasedMaterial,
)
from cramera_usd.scene.materials import TextureChannel, TextureFile

# %% constants

COLOR_CHANNELS = (TextureChannel.RED, TextureChannel.GREEN, TextureChannel.BLUE)
"""
The channels of a colour texture, in order.
"""

UNPOLARIZED_AVERAGE = 2.0
"""
The number of polarizations whose reflectances average to the reflectance of unpolarized
light.
"""

COSINE_WEIGHT = 2.0
"""
The normalization of the cosine-weighted hemisphere, ``2 * cosine`` integrating to one
over cosines from 0 to 1.
"""

# %% blending


@dataclass
class TransmissionBlending:
    """
    Approximates a transmissive surface by an alpha-blended one.

    Each drawn face stands for one interface of the material.

    Its alpha covers all but the light behind it that the interface passes along the
    line of sight in every colour channel, ``weight * (1 - R) * min(tint) * (1 -
    scattering * frosting)``, where ``R`` is the interface's reflectance averaged over
    all directions, since one alpha holds for every view. The tint is the base colour
    factor times the average colour of the base colour texture, and the frosting is the
    roughness averaged over the surface. Its colour is chosen so that, in front of
    surroundings as bright as what it reflects, the blend shows what the interface
    sends towards the eye: the reflection ``R`` plus the tinted rest ``(1 - R) *
    tint``. The transmitted share of the surface reflects without diffusing, so it is
    drawn metallic.

    .. note:: A closed solid such as a pane is drawn with its front and back faces, so
        the light behind it is covered twice, as it crosses two interfaces; a
        thin-walled plane crosses one. Volume absorption depends on the path length
        through the solid, which a material does not know, and is not drawn.

    .. note:: A base colour texture keeps multiplying the drawn colour, so the colour
        is exact at the texture's average colour; where that would need a factor above
        one, the factor is one.
    """

    frosted_scattering: float = 1.0
    """
    The share of the transmitted light that a fully frosted surface (roughness one)
    scatters out of the line of sight; less frosting scatters proportionally less.
    """

    transfer: SrgbTransfer = field(default_factory=SrgbTransfer)
    """
    The decoding of base colour textures into linear light.
    """

    def approximate(self, material: PhysicallyBasedMaterial) -> PhysicallyBasedMaterial:
        """
        :param material: A material as authored, its base colour tinting the
            transmitted light and its roughness frosting it.
        :return: The blended, double-sided material drawn in place of a transmissive
            one; any other material as it is.
        """
        if not material.transmissive:
            return material
        texture_color = self.texture_color(material.base_color_texture)
        tint = (
            numpy.asarray(material.base_color_factor[: len(COLOR_CHANNELS)])
            * texture_color
        )
        reflectance = self.reflectance(material.index_of_refraction)
        see_through = self.see_through(material, tint)
        shown = (
            tint
            if see_through >= 1.0
            else (reflectance + (1.0 - reflectance) * tint - see_through)
            / (1.0 - see_through)
        )
        factor = numpy.minimum(
            numpy.divide(
                shown,
                texture_color,
                out=numpy.zeros(len(COLOR_CHANNELS)),
                where=texture_color > 0.0,
            ),
            1.0,
        )
        return self.reflecting(
            replace(
                material,
                base_color_factor=(
                    *(float(component) for component in factor),
                    material.base_color_factor[TextureChannel.ALPHA.image_index]
                    * (1.0 - see_through),
                ),
                alpha_mode=AlphaMode.BLEND,
                double_sided=True,
            )
        )

    def see_through(
        self, material: PhysicallyBasedMaterial, tint: numpy.ndarray
    ) -> float:
        """
        :param material: A transmissive material.
        :param tint: The linear colour the material tints the transmitted light with.
        :return: The share of the light behind one face of the material that the face
            passes along the line of sight.
        """
        return float(
            material.transmission
            * (1.0 - self.reflectance(material.index_of_refraction))
            * numpy.min(tint)
            * (1.0 - self.frosted_scattering * self.frosting(material))
        )

    @staticmethod
    def frosting(material: PhysicallyBasedMaterial) -> float:
        """
        :param material: A material.
        :return: Its roughness averaged over its surface: the roughness factor times
            the average of the roughness texture.
        """
        texture = material.metallic_roughness_texture
        if texture is None:
            return material.roughness_factor
        return material.roughness_factor * texture.roughness.average()

    def texture_color(self, texture: Optional[TextureFile]) -> numpy.ndarray:
        """
        :param texture: A base colour texture, or None.
        :return: Its average linear colour, decoded from sRGB as glTF viewers decode
            it, or white without a texture.
        """
        if texture is None:
            return numpy.ones(len(COLOR_CHANNELS))
        reader = TextureChannelReader(Image.open(texture.path))
        encoded = numpy.stack([reader.values(channel) for channel in COLOR_CHANNELS])
        return (
            self.transfer.decoded(encoded).reshape(len(COLOR_CHANNELS), -1).mean(axis=1)
        )

    @staticmethod
    def reflecting(material: PhysicallyBasedMaterial) -> PhysicallyBasedMaterial:
        """
        :param material: A transmissive material.
        :return: The material with the transmitted share of its surface metallic:
            every metalness ``m`` becomes ``m + transmission * (1 - m)``.
        """
        share = material.transmission
        texture = material.metallic_roughness_texture
        if texture is None:
            return replace(
                material,
                metallic_factor=ScalarChannel(material.metallic_factor)
                .mixed_with(1.0, share)
                .constant,
            )
        metallic = texture.metallic.mixed_with(
            0.0, 1.0 - material.metallic_factor
        ).mixed_with(1.0, share)
        if not texture.roughness.textured and not metallic.textured:
            return replace(
                material,
                roughness_factor=material.roughness_factor * texture.roughness.constant,
                metallic_factor=metallic.constant,
                metallic_roughness_texture=None,
            )
        return replace(
            material,
            metallic_factor=1.0,
            metallic_roughness_texture=replace(texture, metallic=metallic),
        )

    @classmethod
    def reflectance(cls, index_of_refraction: float) -> float:
        """
        :param index_of_refraction: The index of refraction of the material.
        :return: The reflectance of an interface between air and the material for
            light from all directions: the Fresnel reflectance averaged over the
            cosine-weighted hemisphere of directions of incidence.
        """
        average, _ = quad(
            lambda cosine: COSINE_WEIGHT
            * cosine
            * cls.fresnel_reflectance(cosine, index_of_refraction),
            0.0,
            1.0,
        )
        return average

    @staticmethod
    def fresnel_reflectance(cosine: float, index_of_refraction: float) -> float:
        """
        :param cosine: The cosine of the angle of incidence, above zero.
        :param index_of_refraction: The index of refraction of the material.
        :return: The share of unpolarized light from air that an interface with the
            material reflects (Fresnel equations).
        """
        refracted_sine_squared = (1.0 - cosine**2) / index_of_refraction**2
        refracted_cosine = numpy.sqrt(max(0.0, 1.0 - refracted_sine_squared))
        perpendicular = (cosine - index_of_refraction * refracted_cosine) / (
            cosine + index_of_refraction * refracted_cosine
        )
        parallel = (index_of_refraction * cosine - refracted_cosine) / (
            index_of_refraction * cosine + refracted_cosine
        )
        return float(perpendicular**2 + parallel**2) / UNPOLARIZED_AVERAGE
