"""
Mapping of authored USD shaders onto glTF metallic-roughness materials.
"""

from __future__ import annotations

import io
from dataclasses import replace

import numpy
import pytest
from PIL import Image
from typing_extensions import Any

from cramera_usd.materials.channels import (
    ColorOpacityTexture,
    FlippedNormalTexture,
    RoughnessMetallicTexture,
    ScalarChannel,
    SrgbTransfer,
)
from cramera_usd.materials.emission import EmissionScale
from cramera_usd.materials.fallbacks import DisplayColorMapping, UnknownShaderMapping
from cramera_usd.materials.images import TextureImage, TextureSizeLimit
from cramera_usd.materials.mapper import MaterialMapper
from cramera_usd.materials.mapping import RoughnessMetallicPacking, TangentFlipInput
from cramera_usd.materials.omni_glass import OmniGlassInput
from cramera_usd.materials.omni_pbr import (
    OmniPhysicallyBasedInput,
    OmniPhysicallyBasedMapping,
)
from cramera_usd.materials.omni_surface import OmniSurfaceInput, OmniSurfaceMapping
from cramera_usd.materials.physically_based import (
    BLACK,
    AlphaMode,
    PhysicallyBasedMaterial,
    TextureTransform,
)
from cramera_usd.materials.preview_surface import PreviewSurfaceInput
from cramera_usd.materials.transmission import NORMAL_INCIDENCE
from cramera_usd.materials.transmission import TransmissionBlending
from cramera_usd.scene.materials import (
    AuthoredMaterial,
    ColorSpace,
    MaterialSource,
    TextureChannel,
    TextureFile,
    TextureTile,
    TileGrid,
)

from .dataset.stages import TEXTURES


def texture(name: str, color_space: ColorSpace = ColorSpace.RAW) -> TextureFile:
    """
    A fixture texture.

    :param name: The file name in the texture fixtures.
    :param color_space: The declared colour space.
    """
    return TextureFile(TEXTURES / name, color_space)


def pixels(name: str) -> numpy.ndarray:
    """
    The pixel values of a fixture texture.

    :param name: The file name in the texture fixtures.
    """
    return numpy.asarray(Image.open(TEXTURES / name))


def udim(stem: str, *tiles: int) -> TextureFile:
    """
    A fixture UDIM set.

    :param stem: The file name in the texture fixtures before the tile number.
    :param tiles: The tile numbers of the set.
    """
    paths = [TEXTURES / f"{stem}.{tile}.png" for tile in tiles]
    return TextureFile(
        paths[0],
        tiles=tuple(
            TextureTile(path, (tile - 1001) % 10, (tile - 1001) // 10)
            for path, tile in zip(paths, tiles)
        ),
    )


def decoded(data: bytes) -> numpy.ndarray:
    """
    :param data: An encoded image.
    :return: Its pixel values.
    """
    return numpy.asarray(Image.open(io.BytesIO(data)))


# %% OmniPBR


class TestOmniPhysicallyBasedMapping:
    """
    OmniPBR's albedo, roughness, metalness, emission and tiling.
    """

    def test_untextured_material_uses_omnipbr_defaults(self):
        mapping = OmniPhysicallyBasedMapping()
        material = mapping.map(
            AuthoredMaterial("/Looks/Default", MaterialSource.OMNI_PBR)
        )
        assert material.base_color_factor == (*mapping.diffuse_color, 1.0)
        assert material.roughness_factor == mapping.roughness
        assert material.metallic_factor == 0.0
        assert material.metallic_roughness_texture is None

    def test_diffuse_texture_replaces_the_constant_and_keeps_the_tint(self):
        tint = (0.5, 1.0, 1.0)
        albedo = texture("albedo.png", ColorSpace.SRGB)
        material = OmniPhysicallyBasedMapping().map(
            AuthoredMaterial(
                "/Looks/Decal",
                MaterialSource.OMNI_PBR,
                {
                    OmniPhysicallyBasedInput.DIFFUSE_TEXTURE: albedo,
                    OmniPhysicallyBasedInput.DIFFUSE_TINT: tint,
                    OmniPhysicallyBasedInput.DIFFUSE_COLOR: (0.9, 0.1, 0.1),
                },
            )
        )
        assert material.base_color_texture == albedo
        assert material.base_color_factor == (*tint, 1.0)

    def test_textured_roughness_and_metalness_share_one_packed_texture(self):
        roughness = texture("roughness.png")
        metallic = texture("metallic.png")
        material = OmniPhysicallyBasedMapping().map(
            AuthoredMaterial(
                "/Looks/Steel",
                MaterialSource.OMNI_PBR,
                {
                    OmniPhysicallyBasedInput.ROUGHNESS_TEXTURE: roughness,
                    OmniPhysicallyBasedInput.ROUGHNESS_INFLUENCE: 1.0,
                    OmniPhysicallyBasedInput.METALLIC_TEXTURE: metallic,
                    OmniPhysicallyBasedInput.METALLIC_INFLUENCE: 1.0,
                },
            )
        )
        assert material.metallic_roughness_texture == RoughnessMetallicTexture(
            ScalarChannel(0.5, roughness, 1.0), ScalarChannel(0.0, metallic, 1.0)
        )
        assert (material.roughness_factor, material.metallic_factor) == (1.0, 1.0)

    def test_roughness_texture_without_influence_keeps_the_constant(self):
        material = OmniPhysicallyBasedMapping().map(
            AuthoredMaterial(
                "/Looks/Matte",
                MaterialSource.OMNI_PBR,
                {
                    OmniPhysicallyBasedInput.ROUGHNESS: 0.7,
                    OmniPhysicallyBasedInput.ROUGHNESS_TEXTURE: texture(
                        "roughness.png"
                    ),
                },
            )
        )
        assert material.metallic_roughness_texture is None
        assert material.roughness_factor == 0.7

    def test_emission_above_the_reference_moves_into_the_strength(self):
        mapping = OmniPhysicallyBasedMapping()
        intensity = 3.0 * mapping.emission.reference_intensity
        material = mapping.map(
            AuthoredMaterial(
                "/Looks/Screen",
                MaterialSource.OMNI_PBR,
                {
                    OmniPhysicallyBasedInput.ENABLE_EMISSION: True,
                    OmniPhysicallyBasedInput.EMISSIVE_COLOR: (1.0, 0.5, 0.0),
                    OmniPhysicallyBasedInput.EMISSIVE_INTENSITY: intensity,
                },
            )
        )
        assert material.emissive_factor == (1.0, 0.5, 0.0)
        assert material.emissive_strength == 3.0

    def test_disabled_emission_emits_nothing(self):
        material = OmniPhysicallyBasedMapping().map(
            AuthoredMaterial(
                "/Looks/Off",
                MaterialSource.OMNI_PBR,
                {OmniPhysicallyBasedInput.EMISSIVE_INTENSITY: 4000.0},
            )
        )
        assert material.emissive_factor == (0.0, 0.0, 0.0)

    def test_tiling_becomes_a_texture_transform_in_flipped_coordinates(self):
        material = OmniPhysicallyBasedMapping().map(
            AuthoredMaterial(
                "/Looks/Tiles",
                MaterialSource.OMNI_PBR,
                {
                    OmniPhysicallyBasedInput.TEXTURE_SCALE: (4.0, 2.0),
                    OmniPhysicallyBasedInput.TEXTURE_TRANSLATE: (0.25, 0.5),
                },
            )
        )
        assert material.texture_transform == TextureTransform(
            offset=(0.25, 1.0 - 2.0 - 0.5), scale=(4.0, 2.0)
        )

    def test_specular_level_scales_the_reflectance_at_normal_incidence(self):
        mapping = OmniPhysicallyBasedMapping()
        level = mapping.neutral_specular_level / 4.0
        material = mapping.map(
            AuthoredMaterial(
                "/Looks/Matte",
                MaterialSource.OMNI_PBR,
                {OmniPhysicallyBasedInput.SPECULAR_LEVEL: level},
            )
        )
        assert material.specular_color_factor == (0.25, 0.25, 0.25)
        assert material.unmapped_inputs == ()

    def test_neutral_specular_level_keeps_the_reflectance_of_the_index_of_refraction(
        self,
    ):
        mapping = OmniPhysicallyBasedMapping()
        material = mapping.map(
            AuthoredMaterial(
                "/Looks/Plastic",
                MaterialSource.OMNI_PBR,
                {
                    OmniPhysicallyBasedInput.SPECULAR_LEVEL: (
                        mapping.neutral_specular_level
                    )
                },
            )
        )
        assert (
            material.specular_color_factor
            == PhysicallyBasedMaterial("default").specular_color_factor
        )

    def test_opacity_texture_becomes_the_alpha_of_the_diffuse_texture(self):
        albedo = texture("albedo.png", ColorSpace.SRGB)
        opacity = texture("roughness.png")
        material = OmniPhysicallyBasedMapping().map(
            AuthoredMaterial(
                "/Looks/Leaf",
                MaterialSource.OMNI_PBR,
                {
                    OmniPhysicallyBasedInput.DIFFUSE_TEXTURE: albedo,
                    OmniPhysicallyBasedInput.ENABLE_OPACITY: True,
                    OmniPhysicallyBasedInput.ENABLE_OPACITY_TEXTURE: True,
                    OmniPhysicallyBasedInput.OPACITY_TEXTURE: opacity,
                },
            )
        )
        assert material.base_color_texture == ColorOpacityTexture(albedo, opacity)
        assert material.base_color_factor[3] == 1.0
        assert material.alpha_mode is AlphaMode.BLEND
        assert material.unmapped_inputs == ()

    def test_opacity_texture_of_disabled_opacity_is_not_drawn(self):
        albedo = texture("albedo.png", ColorSpace.SRGB)
        material = OmniPhysicallyBasedMapping().map(
            AuthoredMaterial(
                "/Looks/Leaf",
                MaterialSource.OMNI_PBR,
                {
                    OmniPhysicallyBasedInput.DIFFUSE_TEXTURE: albedo,
                    OmniPhysicallyBasedInput.ENABLE_OPACITY_TEXTURE: True,
                    OmniPhysicallyBasedInput.OPACITY_TEXTURE: texture("roughness.png"),
                },
            )
        )
        assert material.base_color_texture == albedo
        assert material.alpha_mode is AlphaMode.OPAQUE
        assert material.unmapped_inputs == ()

    def test_opacity_constant_of_disabled_opacity_has_no_effect(self):
        material = OmniPhysicallyBasedMapping().map(
            AuthoredMaterial(
                "/Looks/Chrome",
                MaterialSource.OMNI_PBR,
                {OmniPhysicallyBasedInput.OPACITY: 0.3},
            )
        )
        assert material.base_color_factor[3] == 1.0
        assert material.alpha_mode is AlphaMode.OPAQUE
        assert material.unmapped_inputs == ()

    def test_default_tangents_keep_the_normal_map_as_authored(self):
        normal = texture("albedo.png")
        material = OmniPhysicallyBasedMapping().map(
            AuthoredMaterial(
                "/Looks/Chrome",
                MaterialSource.OMNI_PBR,
                {
                    OmniPhysicallyBasedInput.NORMAL_TEXTURE: normal,
                    TangentFlipInput.FLIP_U: False,
                    TangentFlipInput.FLIP_V: True,
                },
            )
        )
        assert material.normal_texture == normal
        assert material.normal_scale == 1.0
        assert material.unmapped_inputs == ()

    def test_tangent_flipped_along_v_flips_the_green_channel(self):
        normal = texture("albedo.png")
        material = OmniPhysicallyBasedMapping().map(
            AuthoredMaterial(
                "/Looks/Chrome",
                MaterialSource.OMNI_PBR,
                {
                    OmniPhysicallyBasedInput.NORMAL_TEXTURE: normal,
                    OmniPhysicallyBasedInput.BUMP_FACTOR: 0.8,
                    TangentFlipInput.FLIP_V: False,
                },
            )
        )
        assert material.normal_texture == FlippedNormalTexture(normal, False, True)
        assert material.normal_scale == 0.8
        assert material.unmapped_inputs == ()

    def test_tangents_flipped_along_both_axes_negate_the_strength(self):
        normal = texture("albedo.png")
        material = OmniPhysicallyBasedMapping().map(
            AuthoredMaterial(
                "/Looks/Chrome",
                MaterialSource.OMNI_PBR,
                {
                    OmniPhysicallyBasedInput.NORMAL_TEXTURE: normal,
                    OmniPhysicallyBasedInput.BUMP_FACTOR: 0.8,
                    TangentFlipInput.FLIP_U: True,
                    TangentFlipInput.FLIP_V: False,
                },
            )
        )
        assert material.normal_texture == normal
        assert material.normal_scale == -0.8

    def test_unknown_authored_inputs_are_listed(self):
        material = OmniPhysicallyBasedMapping().map(
            AuthoredMaterial(
                "/Looks/Bright",
                MaterialSource.OMNI_PBR,
                {
                    OmniPhysicallyBasedInput.ALBEDO_BRIGHTNESS: 1.4,
                    OmniPhysicallyBasedInput.SPECULAR_LEVEL: 0.5,
                },
            )
        )
        assert material.unmapped_inputs == (OmniPhysicallyBasedInput.ALBEDO_BRIGHTNESS,)


# %% packed texture


class TestRoughnessMetallicTexture:
    """
    Greyscale roughness and metalness images packed into glTF's green and blue channels.
    """

    def test_green_holds_roughness_and_blue_holds_metalness(self):
        packed = RoughnessMetallicTexture(
            ScalarChannel(0.5, texture("roughness.png")),
            ScalarChannel(0.0, texture("metallic.png")),
        )
        image = numpy.asarray(Image.open(io.BytesIO(packed.encode(TextureSizeLimit()))))
        assert numpy.array_equal(image[..., 1], pixels("roughness.png"))
        assert numpy.array_equal(image[..., 2], pixels("metallic.png"))

    def test_influence_blends_the_texture_with_the_constant(self):
        packed = RoughnessMetallicTexture(
            ScalarChannel(1.0, texture("roughness.png"), 0.25),
            ScalarChannel(0.0),
        )
        image = numpy.asarray(Image.open(io.BytesIO(packed.encode(TextureSizeLimit()))))
        expected = numpy.round(0.75 * 255.0 + 0.25 * pixels("roughness.png"))
        assert numpy.array_equal(image[..., 1], expected)
        assert numpy.array_equal(image[..., 2], numpy.zeros_like(expected))

    def test_a_single_channel_of_a_colour_image_is_read(self):
        channel = ScalarChannel(
            0.0, TextureFile(TEXTURES / "albedo.png", channel=TextureChannel.GREEN)
        )
        values = channel.texel_values(None)
        assert numpy.array_equal(values * 255.0, pixels("albedo.png")[..., 1])


# %% normal map with a flipped tangent


def test_flipped_normal_texture_inverts_the_flipped_component_only():
    flipped = decoded(
        FlippedNormalTexture(
            TextureFile(TEXTURES / "tiles_normal.1001.png"), False, True
        ).encode(TextureSizeLimit())
    )
    authored = pixels("tiles_normal.1001.png")
    assert numpy.array_equal(flipped[..., 0], authored[..., 0])
    assert numpy.array_equal(flipped[..., 1], 255 - authored[..., 1])
    assert numpy.array_equal(flipped[..., 2], authored[..., 2])


# %% texture images


class TestTextureImage:
    """
    The pixels of a texture file, the atlas of a UDIM set, and the size limit.
    """

    def test_tile_1002_sits_right_of_tile_1001(self):
        atlas = numpy.asarray(TextureImage(udim("tiles_albedo", 1001, 1002)).opened())
        assert atlas.shape[:2] == (2, 4)
        assert numpy.array_equal(atlas[:, :2], pixels("tiles_albedo.1001.png"))
        assert numpy.array_equal(atlas[:, 2:], pixels("tiles_albedo.1002.png"))

    def test_second_row_of_tiles_sits_on_top(self):
        texture_file = TextureFile(
            TEXTURES / "tiles_albedo.1001.png",
            tiles=(
                TextureTile(TEXTURES / "tiles_albedo.1001.png", 0, 0),
                TextureTile(TEXTURES / "tiles_albedo.1002.png", 0, 1),
            ),
        )
        atlas = numpy.asarray(TextureImage(texture_file).opened())
        assert texture_file.grid == TileGrid(1, 2)
        assert numpy.array_equal(atlas[:2], pixels("tiles_albedo.1002.png"))
        assert numpy.array_equal(atlas[2:], pixels("tiles_albedo.1001.png"))

    def test_square_without_a_tile_is_black(self):
        atlas = numpy.asarray(TextureImage(udim("tiles_albedo", 1002)).opened())
        assert numpy.array_equal(atlas[:, :2], numpy.zeros((2, 2, 3)))
        assert numpy.array_equal(atlas[:, 2:], pixels("tiles_albedo.1002.png"))

    def test_single_image_repeats_in_every_square_of_a_grid(self):
        image = numpy.asarray(
            TextureImage(texture("albedo.png")).opened(TileGrid(2, 1))
        )
        assert numpy.array_equal(image[:, :4], pixels("albedo.png"))
        assert numpy.array_equal(image[:, 4:], pixels("albedo.png"))

    def test_every_tile_is_a_file_of_the_texture(self):
        texture_file = udim("tiles_albedo", 1001, 1002)
        assert texture_file.files == (
            TEXTURES / "tiles_albedo.1001.png",
            TEXTURES / "tiles_albedo.1002.png",
        )
        assert texture("albedo.png").files == (TEXTURES / "albedo.png",)

    @pytest.mark.parametrize(
        ("longest_side", "size", "fitted"),
        [
            (1024, (4096, 2048), (1024, 512)),
            (1024, (1024, 300), (1024, 300)),
            (None, (8192, 4096), (8192, 4096)),
        ],
    )
    def test_size_limit_scales_the_longer_side_keeping_the_aspect(
        self, longest_side, size, fitted
    ):
        assert TextureSizeLimit(longest_side).fitted(size) == fitted

    def test_packed_texture_of_a_udim_set_is_its_atlas(self):
        packed = RoughnessMetallicTexture(
            ScalarChannel(
                0.0,
                replace(udim("tiles_normal", 1001, 1002), channel=TextureChannel.GREEN),
            ),
            ScalarChannel(0.0, texture("metallic.png")),
        )
        image = decoded(packed.encode(TextureSizeLimit()))
        assert packed.grid == TileGrid(2, 1)
        assert numpy.array_equal(
            image[..., 1],
            numpy.hstack(
                [
                    pixels("tiles_normal.1001.png")[..., 1],
                    pixels("tiles_normal.1002.png")[..., 1],
                ]
            ),
        )

    def test_packed_texture_is_scaled_down_to_the_limit(self):
        packed = RoughnessMetallicTexture(
            ScalarChannel(0.0, texture("roughness.png")), ScalarChannel(0.0)
        )
        assert decoded(packed.encode(TextureSizeLimit(2))).shape[:2] == (2, 2)


class TestAtlasTransform:
    """
    The texture coordinates that read a UDIM set's atlas.
    """

    @staticmethod
    def applied(transform: TextureTransform, point: Any) -> numpy.ndarray:
        """
        :param transform: A change of glTF texture coordinates.
        :param point: glTF texture coordinates.
        :return: The changed coordinates.
        """
        return numpy.asarray(transform.offset) + numpy.asarray(
            transform.scale
        ) * numpy.asarray(point)

    def test_atlas_is_read_where_the_tiles_are(self):
        grid = TileGrid(2, 2)
        usd_point = (1.25, 1.75)
        gltf_point = (usd_point[0], 1.0 - usd_point[1])
        read = self.applied(TextureTransform.onto_atlas(grid), gltf_point)
        column, row = 1, 1
        within_tile = (usd_point[0] - column, usd_point[1] - row)
        from_top_left = (
            (column + within_tile[0]) / grid.columns,
            (grid.rows - 1 - row + 1.0 - within_tile[1]) / grid.rows,
        )
        assert numpy.allclose(read, from_top_left)

    def test_material_tiling_is_applied_before_the_atlas(self):
        tiling = TextureTransform(offset=(0.0, -2.0), scale=(3.0, 3.0))
        atlas = TextureTransform.onto_atlas(TileGrid(2, 1))
        point = (0.3, 0.6)
        assert numpy.allclose(
            self.applied(tiling.then(atlas), point),
            self.applied(atlas, self.applied(tiling, point)),
        )


# %% transmission drawn by blending


def hemispherical_reflectance(index_of_refraction: float) -> float:
    """
    The closed form of the Fresnel reflectance of unpolarized light, averaged over the
    cosine-weighted hemisphere of directions of incidence from air.

    :param index_of_refraction: The index of refraction of the material.
    """
    index = index_of_refraction
    return (
        0.5
        + (index - 1) * (3 * index + 1) / (6 * (index + 1) ** 2)
        + index**2
        * (index**2 - 1) ** 2
        / (index**2 + 1) ** 3
        * numpy.log((index - 1) / (index + 1))
        - 2 * index**3 * (index**2 + 2 * index - 1) / ((index**2 + 1) * (index**4 - 1))
        + 8
        * index**4
        * (index**4 + 1)
        / ((index**2 + 1) * (index**4 - 1) ** 2)
        * numpy.log(index)
    )


def transmissive(**properties: Any) -> PhysicallyBasedMaterial:
    """
    A fully transmissive, smooth, colourless surface with an index of refraction of one,
    changed by the given properties.

    :param properties: The material properties that differ.
    """
    return replace(
        PhysicallyBasedMaterial(
            "/Looks/Glass",
            roughness_factor=0.0,
            transmission=1.0,
            index_of_refraction=1.0,
        ),
        **properties,
    )


def smoked_tint() -> tuple[float, float, float]:
    """
    The average linear colour of the smoked fixture texture, decoded from sRGB.
    """
    decoded = SrgbTransfer().decoded(pixels("smoke.png") / 255.0)
    return tuple(float(value) for value in decoded.mean(axis=(0, 1)))


class TestTransmissionBlending:
    """
    Transmissive surfaces drawn as alpha-blended, reflecting approximations.
    """

    @pytest.mark.parametrize("index_of_refraction", [1.33, 1.5, 1.52, 1.59, 2.4])
    def test_reflectance_is_the_fresnel_reflectance_averaged_over_the_hemisphere(
        self, index_of_refraction
    ):
        assert TransmissionBlending.reflectance(index_of_refraction) == pytest.approx(
            hemispherical_reflectance(index_of_refraction)
        )

    def test_clear_colourless_glass_covers_the_light_it_reflects(self):
        blended = TransmissionBlending().approximate(
            transmissive(index_of_refraction=1.5)
        )
        assert blended.base_color_factor[3] == pytest.approx(
            hemispherical_reflectance(1.5)
        )

    def test_tint_covers_what_its_least_transmitted_channel_absorbs(self):
        blended = TransmissionBlending().approximate(
            transmissive(base_color_factor=(0.5, 0.8, 1.0, 1.0))
        )
        assert blended.base_color_factor[3] == pytest.approx(0.5)

    def test_specular_colour_scales_the_reflected_share_of_the_drawn_colour(self):
        blending = TransmissionBlending()
        tint = numpy.array([0.5, 0.8, 1.0])
        specular = numpy.array([0.1, 0.2, 0.3])
        glass = transmissive(
            base_color_factor=(*tint, 1.0),
            index_of_refraction=1.5,
            specular_color_factor=tuple(specular),
        )
        blended = blending.approximate(glass)
        reflectance = blending.reflectance(glass.index_of_refraction)
        see_through = blending.see_through(glass, tint)
        assert blended.base_color_factor[:3] == pytest.approx(
            (specular * reflectance + (1.0 - reflectance) * tint - see_through)
            / (1.0 - see_through)
        )

    def test_frosting_scatters_its_share_out_of_the_line_of_sight(self):
        blended = TransmissionBlending(frosted_scattering=0.5).approximate(
            transmissive(roughness_factor=0.4)
        )
        assert blended.base_color_factor[3] == pytest.approx(0.2)

    def test_light_the_surface_does_not_transmit_is_covered(self):
        blended = TransmissionBlending().approximate(transmissive(transmission=0.25))
        assert blended.base_color_factor[3] == pytest.approx(0.75)

    def test_cut_out_coverage_scales_the_opacity(self):
        blending = TransmissionBlending()
        whole = blending.approximate(transmissive(index_of_refraction=1.5))
        cut = blending.approximate(
            transmissive(
                index_of_refraction=1.5, base_color_factor=(1.0, 1.0, 1.0, 0.5)
            )
        )
        assert cut.base_color_factor[3] == pytest.approx(
            0.5 * whole.base_color_factor[3]
        )

    def test_blend_shows_reflection_and_tinted_transmission_of_even_surroundings(
        self,
    ):
        tint = (0.65, 0.33, 0.06)
        blended = TransmissionBlending().approximate(
            transmissive(index_of_refraction=1.52, base_color_factor=(*tint, 1.0))
        )
        reflectance = TransmissionBlending.reflectance(1.52)
        alpha = blended.base_color_factor[3]
        assert [
            alpha * color + (1.0 - alpha) for color in blended.base_color_factor[:3]
        ] == pytest.approx(
            [reflectance + (1.0 - reflectance) * component for component in tint]
        )

    def test_blended_surface_reflects_without_diffusing(self):
        roughness = texture("roughness.png")
        blended = TransmissionBlending().approximate(
            transmissive(
                metallic_roughness_texture=RoughnessMetallicTexture(
                    ScalarChannel(0.0, roughness), ScalarChannel(0.0)
                )
            )
        )
        assert blended.metallic_factor == 1.0
        assert blended.metallic_roughness_texture == RoughnessMetallicTexture(
            ScalarChannel(0.0, roughness), ScalarChannel(1.0)
        )

    def test_blended_surface_is_drawn_from_both_sides(self):
        blended = TransmissionBlending().approximate(transmissive())
        assert blended.alpha_mode is AlphaMode.BLEND
        assert blended.double_sided

    def test_opaque_surface_is_drawn_as_it_is(self):
        opaque = PhysicallyBasedMaterial("/Looks/Paint")
        assert TransmissionBlending().approximate(opaque) is opaque

    def test_frosting_of_a_packed_constant_roughness_is_that_constant(self):
        packed = RoughnessMetallicPacking(
            ScalarChannel(0.0), ScalarChannel(0.0, texture("metallic.png"))
        ).apply(transmissive(index_of_refraction=1.5))
        blended = TransmissionBlending().approximate(packed)
        assert blended.base_color_factor[3] == pytest.approx(
            hemispherical_reflectance(1.5)
        )

    def test_frosting_of_a_roughness_texture_is_its_average_texel(self):
        packed = RoughnessMetallicPacking(
            ScalarChannel(0.0, texture("roughness.png")), ScalarChannel(0.0)
        ).apply(transmissive())
        blended = TransmissionBlending().approximate(packed)
        assert blended.base_color_factor[3] == pytest.approx(
            pixels("roughness.png").mean() / 255.0
        )

    def test_transmitted_share_of_a_surface_is_metallic(self):
        authored, share = 0.2, 0.1
        blended = TransmissionBlending().approximate(
            transmissive(transmission=share, metallic_factor=authored)
        )
        assert blended.metallic_factor == pytest.approx(
            authored + share * (1.0 - authored)
        )

    def test_metalness_texture_of_a_partly_transmissive_surface_moves_towards_metal(
        self,
    ):
        share = 0.25
        packed = RoughnessMetallicPacking(
            ScalarChannel(0.3), ScalarChannel(0.0, texture("metallic.png"))
        ).apply(transmissive(transmission=share))
        blended = TransmissionBlending().approximate(packed)
        image = numpy.asarray(
            Image.open(
                io.BytesIO(
                    blended.metallic_roughness_texture.encode(TextureSizeLimit())
                )
            )
        )
        assert numpy.array_equal(
            image[..., 2],
            numpy.round((1.0 - share) * pixels("metallic.png") + share * 255.0),
        )

    def test_tint_texture_covers_like_its_average_colour(self):
        blending = TransmissionBlending()
        textured = blending.approximate(
            transmissive(
                index_of_refraction=1.5,
                base_color_texture=texture("smoke.png", ColorSpace.SRGB),
            )
        )
        flat = blending.approximate(
            transmissive(
                index_of_refraction=1.5, base_color_factor=(*smoked_tint(), 1.0)
            )
        )
        assert textured.base_color_factor[3] == pytest.approx(flat.base_color_factor[3])

    def test_tint_texture_shows_the_blended_colour_at_its_average_texel(self):
        blending = TransmissionBlending()
        textured = blending.approximate(
            transmissive(
                index_of_refraction=1.5,
                base_color_texture=texture("smoke.png", ColorSpace.SRGB),
            )
        )
        flat = blending.approximate(
            transmissive(
                index_of_refraction=1.5, base_color_factor=(*smoked_tint(), 1.0)
            )
        )
        assert [
            factor * tint
            for factor, tint in zip(textured.base_color_factor[:3], smoked_tint())
        ] == pytest.approx(flat.base_color_factor[:3])


def test_srgb_decoding_follows_iec_61966_2_1():
    decoded = SrgbTransfer().decoded(numpy.array([0.0, 0.04045, 0.5, 1.0]))
    assert decoded == pytest.approx([0.0, 0.0031308, 0.2140411, 1.0], abs=1e-7)


# %% OmniSurface, OmniGlass, preview surface


def test_omnisurface_base_colour_is_scaled_by_the_default_diffuse_weight():
    mapping = OmniSurfaceMapping()
    color = (0.6, 0.6, 0.5)
    material = mapping.map(
        AuthoredMaterial(
            "/Looks/Steel",
            MaterialSource.OMNI_SURFACE,
            {
                OmniSurfaceInput.DIFFUSE_COLOR: color,
                OmniSurfaceInput.METALNESS: 1.0,
                OmniSurfaceInput.COAT_WEIGHT: 0.5,
            },
        )
    )
    assert material.base_color_factor == (
        *(component * mapping.diffuse_weight for component in color),
        1.0,
    )
    assert material.metallic_factor == 1.0
    assert material.roughness_factor == mapping.roughness
    assert (material.clearcoat, material.clearcoat_roughness) == (
        0.5,
        mapping.coat_roughness,
    )


def test_omnisurface_roughness_image_replaces_the_constant():
    roughness = texture("roughness.png")
    material = OmniSurfaceMapping().map(
        AuthoredMaterial(
            "/Looks/Brushed",
            MaterialSource.OMNI_SURFACE,
            {
                OmniSurfaceInput.ROUGHNESS_IMAGE: roughness,
                OmniSurfaceInput.METALNESS: 1.0,
            },
        )
    )
    assert material.metallic_roughness_texture.roughness.texture == roughness
    assert material.metallic_roughness_texture.metallic == ScalarChannel(1.0)


def test_clear_omnisurface_glass_covers_only_the_light_it_reflects():
    material = OmniSurfaceMapping().map(
        AuthoredMaterial(
            "/Looks/Glass",
            MaterialSource.OMNI_SURFACE,
            {
                OmniSurfaceInput.ENABLE_TRANSMISSION: True,
                OmniSurfaceInput.TRANSMISSION_WEIGHT: 1.0,
                OmniSurfaceInput.ROUGHNESS: 0.0,
            },
        )
    )
    blended = TransmissionBlending().approximate(material)
    assert blended.base_color_factor[3] == pytest.approx(
        hemispherical_reflectance(material.index_of_refraction)
    )


def test_omnisurface_transmission_colour_tints_the_transmitted_share():
    mapping = OmniSurfaceMapping()
    diffuse, transmitted, share = (0.8, 0.1, 0.1), (0.2, 0.4, 1.0), 0.25
    material = mapping.map(
        AuthoredMaterial(
            "/Looks/Tinted",
            MaterialSource.OMNI_SURFACE,
            {
                OmniSurfaceInput.DIFFUSE_COLOR: diffuse,
                OmniSurfaceInput.ENABLE_TRANSMISSION: True,
                OmniSurfaceInput.TRANSMISSION_WEIGHT: share,
                OmniSurfaceInput.TRANSMISSION_COLOR: transmitted,
            },
        )
    )
    assert material.base_color_factor[:3] == pytest.approx(
        [
            (1.0 - share) * mapping.diffuse_weight * diffuse_component
            + share * transmitted_component
            for diffuse_component, transmitted_component in zip(diffuse, transmitted)
        ]
    )


def test_omnisurface_transmission_image_tints_a_mostly_transmissive_surface():
    smoke = texture("smoke.png", ColorSpace.SRGB)
    material = OmniSurfaceMapping().map(
        AuthoredMaterial(
            "/Looks/Smoked",
            MaterialSource.OMNI_SURFACE,
            {
                OmniSurfaceInput.DIFFUSE_IMAGE: texture("albedo.png", ColorSpace.SRGB),
                OmniSurfaceInput.ENABLE_TRANSMISSION: True,
                OmniSurfaceInput.TRANSMISSION_WEIGHT: 1.0,
                OmniSurfaceInput.TRANSMISSION_COLOR_IMAGE: smoke,
            },
        )
    )
    assert material.base_color_texture == smoke


def test_omniglass_transmits_blends_and_refracts():
    color = (0.9, 0.95, 1.0)
    material = MaterialMapper().map(
        AuthoredMaterial(
            "/Looks/Glass",
            MaterialSource.OMNI_GLASS,
            {
                OmniGlassInput.COLOR: color,
                OmniGlassInput.INDEX_OF_REFRACTION: 1.52,
                OmniGlassInput.FROSTING: 0.1,
            },
        )
    )
    assert material.transmission == 1.0
    assert material.index_of_refraction == 1.52
    assert material.roughness_factor == 0.1
    assert material.base_color_factor == (*color, 1.0)
    assert material.alpha_mode is AlphaMode.BLEND
    assert material.double_sided


def test_omniglass_colour_texture_replaces_the_glass_colour():
    smoke = texture("smoke.png", ColorSpace.SRGB)
    material = MaterialMapper().map(
        AuthoredMaterial(
            "/Looks/Smoked",
            MaterialSource.OMNI_GLASS,
            {
                OmniGlassInput.COLOR: (0.9, 0.95, 1.0),
                OmniGlassInput.COLOR_TEXTURE: smoke,
            },
        )
    )
    assert material.base_color_texture == smoke
    assert material.base_color_factor == (1.0, 1.0, 1.0, 1.0)


def test_omniglass_reflection_colour_scales_its_reflection():
    reflection = (0.1, 0.2, 0.3)
    material = MaterialMapper().map(
        AuthoredMaterial(
            "/Looks/Pane",
            MaterialSource.OMNI_GLASS,
            {OmniGlassInput.REFLECTION_COLOR: reflection},
        )
    )
    assert material.specular_color_factor == reflection
    assert material.unmapped_inputs == ()


def test_omniglass_cut_out_opacity_scales_its_coverage():
    material = MaterialMapper().map(
        AuthoredMaterial(
            "/Looks/Pane",
            MaterialSource.OMNI_GLASS,
            {OmniGlassInput.ENABLE_OPACITY: True, OmniGlassInput.CUTOUT_OPACITY: 0.4},
        )
    )
    assert material.base_color_factor[3] == 0.4
    assert material.unmapped_inputs == ()


def test_omniglass_enabled_opacity_without_a_cut_out_keeps_the_whole_pane():
    material = MaterialMapper().map(
        AuthoredMaterial(
            "/Looks/Pane",
            MaterialSource.OMNI_GLASS,
            {OmniGlassInput.ENABLE_OPACITY: True},
        )
    )
    assert material.base_color_factor[3] == 1.0
    assert material.unmapped_inputs == ()


def test_omniglass_unscaled_texture_coordinates_are_not_reported():
    material = MaterialMapper().map(
        AuthoredMaterial(
            "/Looks/Pane",
            MaterialSource.OMNI_GLASS,
            {OmniGlassInput.TEXTURE_SCALE: (1.0, 1.0)},
        )
    )
    assert material.unmapped_inputs == ()


def test_omniglass_hidden_texture_switch_is_not_reported():
    material = MaterialMapper().map(
        AuthoredMaterial(
            "/Looks/Smoked",
            MaterialSource.OMNI_GLASS,
            {
                OmniGlassInput.USE_COLOR_TEXTURE: True,
                OmniGlassInput.COLOR_TEXTURE: texture("smoke.png", ColorSpace.SRGB),
            },
        )
    )
    assert material.unmapped_inputs == ()


def test_omniglass_tangent_flips_without_a_normal_map_have_no_effect():
    material = MaterialMapper().map(
        AuthoredMaterial(
            "/Looks/Glass",
            MaterialSource.OMNI_GLASS,
            {TangentFlipInput.FLIP_U: False, TangentFlipInput.FLIP_V: False},
        )
    )
    assert material.normal_texture is None
    assert material.unmapped_inputs == ()


def test_omniglass_tangent_flipped_along_v_flips_the_green_channel():
    normal = texture("albedo.png")
    material = MaterialMapper().map(
        AuthoredMaterial(
            "/Looks/Glass",
            MaterialSource.OMNI_GLASS,
            {OmniGlassInput.NORMAL_TEXTURE: normal, TangentFlipInput.FLIP_V: False},
        )
    )
    assert material.normal_texture == FlippedNormalTexture(normal, False, True)


def test_preview_surface_opacity_blends_and_texture_replaces_colour():
    albedo = texture("albedo.png", ColorSpace.SRGB)
    material = MaterialMapper().map(
        AuthoredMaterial(
            "/Looks/Label",
            MaterialSource.PREVIEW_SURFACE,
            {
                PreviewSurfaceInput.DIFFUSE_COLOR: albedo,
                PreviewSurfaceInput.OPACITY: 0.4,
                PreviewSurfaceInput.METALLIC: 0.2,
            },
        )
    )
    assert material.base_color_texture == albedo
    assert material.base_color_factor == (1.0, 1.0, 1.0, 0.4)
    assert material.alpha_mode is AlphaMode.BLEND
    assert material.metallic_factor == 0.2


def test_preview_surface_specular_workflow_scales_the_reflectance_of_the_index_of_refraction():
    specular = (0.02, 0.04, 0.08)
    material = MaterialMapper().map(
        AuthoredMaterial(
            "/Looks/Glaze",
            MaterialSource.PREVIEW_SURFACE,
            {
                PreviewSurfaceInput.USE_SPECULAR_WORKFLOW: 1,
                PreviewSurfaceInput.SPECULAR_COLOR: specular,
                PreviewSurfaceInput.METALLIC: 0.7,
            },
        )
    )
    reflectance = TransmissionBlending.fresnel_reflectance(
        NORMAL_INCIDENCE, material.index_of_refraction
    )
    assert material.specular_color_factor == pytest.approx(
        tuple(channel / reflectance for channel in specular)
    )
    assert material.metallic_factor == 0.0
    assert material.unmapped_inputs == ()


def test_preview_surface_specular_workflow_without_specular_colour_reflects_nothing_head_on():
    material = MaterialMapper().map(
        AuthoredMaterial(
            "/Looks/Cup",
            MaterialSource.PREVIEW_SURFACE,
            {PreviewSurfaceInput.USE_SPECULAR_WORKFLOW: 1},
        )
    )
    assert material.specular_color_factor == BLACK
    assert material.unmapped_inputs == ()


def test_unbound_geometry_without_display_colour_is_fallback_grey():
    mapping = DisplayColorMapping()
    material = mapping.map(
        AuthoredMaterial("displayColor", MaterialSource.DISPLAY_COLOR)
    )
    assert material.base_color_factor == (*mapping.fallback_color, 1.0)


def test_unknown_shader_is_magenta_and_reported():
    mapping = UnknownShaderMapping()
    material = mapping.map(
        AuthoredMaterial(
            "/Looks/Car", MaterialSource.UNKNOWN, {"paint_flake": 0.3}, "CarPaint"
        )
    )
    assert material.base_color_factor == (*mapping.warning_color, 1.0)
    assert material.unmapped_inputs == ("CarPaint", "paint_flake")


@pytest.mark.parametrize("ratio", [0.25, 1.0, 4.0])
def test_emission_scale_preserves_the_emitted_colour(ratio):
    scale = EmissionScale()
    color = (0.5, 0.25, 1.0)
    emission = scale.emission(color, ratio * scale.reference_intensity)
    assert max(emission.factor) <= 1.0
    assert numpy.allclose(
        numpy.array(emission.factor) * emission.strength, numpy.array(color) * ratio
    )
