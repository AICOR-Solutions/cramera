"""
Reading the surface shaders of bound materials.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from pxr import Sdf, Usd, UsdGeom, UsdShade
from typing_extensions import Dict, Optional

from cramera_usd.scene.log import ConversionLog
from cramera_usd.scene.materials import (
    AuthoredMaterial,
    ColorSpace,
    MaterialSource,
    ShaderInputValue,
    TextureChannel,
    TextureFile,
)
from cramera_usd.stage.frame import StageFrame
from cramera_usd.stage.values import StageValue

# %% stage vocabulary


class DisplayPrimvar(StrEnum):
    """
    The primvars that shade geometry without a bound material.
    """

    COLOR = "displayColor"
    """
    The colour of geometry without a material.
    """

    OPACITY = "displayOpacity"
    """
    The opacity of geometry without a material.
    """


class ShaderIdentifier(StrEnum):
    """
    Shader identifiers the reader recognises in ``info:id``.
    """

    TEXTURE = "UsdUVTexture"
    """
    The USD texture reader feeding a preview surface input.
    """


class RenderContext(StrEnum):
    """
    The material render contexts the reader asks for a surface shader.
    """

    MATERIAL_DEFINITION_LANGUAGE = "mdl"
    """
    NVIDIA MDL, which Isaac Sim's Omni materials use.
    """


class TextureInput(StrEnum):
    """
    The UsdUVTexture inputs the reader follows.
    """

    FILE = "file"
    """
    The image file.
    """

    COLOR_SPACE = "sourceColorSpace"
    """
    The declared colour space of the image.
    """


class DisplayMaterialName(StrEnum):
    """
    The separators of the generated name of a display-colour material.
    """

    PART = "/"
    """
    Between the parts of the name.
    """

    VALUE = "="
    """
    Between a primvar name and its value.
    """


# %% reader


@dataclass
class MaterialReader:
    """
    Reads the surface shader of bound materials into :class:`AuthoredMaterial`.
    """

    frame: StageFrame
    """
    The stage frame, for the read time.
    """

    log: ConversionLog
    """
    The log collecting unresolved textures.
    """

    materials: Dict[str, AuthoredMaterial] = field(default_factory=dict)
    """
    The materials read so far, by name.
    """

    def material_of(self, prim: Usd.Prim) -> str:
        """
        :param prim: A geometry prim or a geometry subset prim.
        :return: The name of the material shading the prim, read on first use.
        """
        material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
        if not material:
            return self.display_color_material(prim)
        name = material.GetPath().pathString
        if name not in self.materials:
            self.materials[name] = self.read(material)
        return name

    def display_color_material(self, prim: Usd.Prim) -> str:
        """
        :param prim: A geometry prim, or a subset whose parent carries the primvars.
        :return: The name of the material standing for the prim's display colour and
            opacity.
        """
        geometry = prim if prim.IsA(UsdGeom.Gprim) else prim.GetParent()
        primvars = UsdGeom.PrimvarsAPI(geometry)
        inputs: Dict[str, ShaderInputValue] = {}
        for primvar_name in DisplayPrimvar:
            primvar = primvars.GetPrimvar(primvar_name)
            values = primvar.ComputeFlattened(self.frame.time) if primvar else None
            if values is not None and len(values) > 0:
                first = values[0]
                inputs[primvar_name] = (
                    tuple(float(component) for component in first)
                    if primvar_name is DisplayPrimvar.COLOR
                    else float(first)
                )
        name = DisplayMaterialName.PART.join(
            [DisplayPrimvar.COLOR]
            + [
                f"{key}{DisplayMaterialName.VALUE}{value}"
                for key, value in sorted(inputs.items())
            ]
        )
        self.materials.setdefault(
            name, AuthoredMaterial(name, MaterialSource.DISPLAY_COLOR, inputs)
        )
        return name

    def read(self, material: UsdShade.Material) -> AuthoredMaterial:
        """
        :param material: A bound material.
        :return: The inputs of its surface shader, the MDL one preferred.
        """
        name = material.GetPath().pathString
        shader, _, _ = material.ComputeSurfaceSource(
            RenderContext.MATERIAL_DEFINITION_LANGUAGE
        )
        if not shader:
            shader, _, _ = material.ComputeSurfaceSource()
        if not shader:
            return AuthoredMaterial(name, MaterialSource.UNKNOWN)
        identifier = self.identifier_of(shader)
        inputs = {
            shader_input.GetBaseName(): value
            for shader_input in shader.GetInputs()
            if (value := self.input_value(shader_input)) is not None
        }
        return AuthoredMaterial(
            name, MaterialSource.of_identifier(identifier), inputs, identifier
        )

    @staticmethod
    def identifier_of(shader: UsdShade.Shader) -> str:
        """
        :param shader: A surface shader.
        :return: The shader's MDL sub-identifier (or MDL file stem), else its
            ``info:id``, else an empty text.
        """
        context = RenderContext.MATERIAL_DEFINITION_LANGUAGE
        sub_identifier = shader.GetSourceAssetSubIdentifier(context)
        if sub_identifier:
            return sub_identifier
        asset = shader.GetSourceAsset(context)
        if asset and asset.path:
            return Path(asset.path).stem
        return shader.GetIdAttr().Get() or ""

    def input_value(self, shader_input: UsdShade.Input) -> Optional[ShaderInputValue]:
        """
        :param shader_input: A shader input.
        :return: The input's value, following connections to material interface inputs
            and to UsdUVTexture readers, or None for a value the mappings cannot use.
        """
        attributes = shader_input.GetValueProducingAttributes()
        if not attributes:
            return None
        attribute = attributes[0]
        if UsdShade.Output.IsOutput(attribute):
            return self.connected_texture(attribute)
        value = attribute.Get(self.frame.time)
        if isinstance(value, Sdf.AssetPath):
            return self.texture_file(
                value, attribute.GetColorSpace(), TextureChannel.RGB
            )
        return StageValue(value).shader_value()

    def connected_texture(self, output: Usd.Attribute) -> Optional[TextureFile]:
        """
        :param output: A connected shader output attribute.
        :return: The texture the output provides, or None when it is no UsdUVTexture
            output with a file.
        """
        shader = UsdShade.Shader(output.GetPrim())
        if shader.GetIdAttr().Get() != ShaderIdentifier.TEXTURE:
            return None
        file_input = shader.GetInput(TextureInput.FILE)
        color_space_input = shader.GetInput(TextureInput.COLOR_SPACE)
        asset = file_input.Get(self.frame.time) if file_input else None
        if not isinstance(asset, Sdf.AssetPath):
            return None
        channel = TextureChannel.of_output(UsdShade.Output(output).GetBaseName())
        color_space = color_space_input.Get() if color_space_input else ""
        return self.texture_file(asset, color_space or "", channel)

    def texture_file(
        self, asset: Sdf.AssetPath, color_space: str, channel: TextureChannel
    ) -> Optional[TextureFile]:
        """
        :param asset: An authored asset path.
        :param color_space: The declared colour space, possibly empty.
        :param channel: The channels read.
        :return: The resolved texture file, or None for an empty asset path and for one
            that does not resolve to a file, which the log records.
        """
        if not asset.path:
            return None
        if not asset.resolvedPath or not Path(asset.resolvedPath).is_file():
            self.log.miss_texture(asset.path)
            return None
        return TextureFile(
            Path(asset.resolvedPath), ColorSpace.of_name(color_space), channel
        )
