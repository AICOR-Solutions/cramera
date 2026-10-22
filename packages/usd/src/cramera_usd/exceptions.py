"""
Errors raised while converting a stage, exporting a bundle or auditing a twin.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from typing_extensions import List

from cramera_protocol.bundle.conversion_report import ExcludedPrim, ExclusionReason

# %% base


@dataclass
class ConversionError(Exception):
    """
    A stage, option or file the converter cannot work with.
    """

    def __post_init__(self) -> None:
        """
        Pass the error's message on to :class:`Exception`.
        """
        super().__init__(self.message())

    def message(self) -> str:
        """
        :return: The sentences a person reads when this error is raised: what is wrong
            and how to correct it.
        """
        return type(self).__name__


# %% stage access


@dataclass
class StageNotFound(ConversionError):
    """
    The stage file to convert does not exist.
    """

    path: Path
    """
    The stage file that was asked for.
    """

    def message(self) -> str:
        return (
            f"No USD stage at {self.path}. "
            "Pass the path of an existing .usd, .usda or .usdc file."
        )


@dataclass
class StageUnreadable(ConversionError):
    """
    The file exists but is of a type USD does not read.
    """

    path: Path
    """
    The file that was given as a stage.
    """

    def message(self) -> str:
        return (
            f"{self.path} is not a USD stage. Pass a .usd, .usda or .usdc file, or "
            "another layer format USD reads."
        )


@dataclass
class PrimNotFound(ConversionError):
    """
    A prim selected for conversion, or excluded from it, does not exist on the composed
    stage.
    """

    path: str
    """
    The prim path that was asked for.
    """

    def message(self) -> str:
        return (
            f"The stage has no active prim at {self.path}. "
            "Name an existing prim path, for example /World."
        )


@dataclass
class RobotExcluded(ConversionError):
    """
    The robot to convert as a model of its own lies in a subtree excluded from the
    conversion.
    """

    robot_path: str
    """
    The prim chosen as the robot.
    """

    excluded_path: str
    """
    The excluded prim holding it.
    """

    def message(self) -> str:
        return (
            f"The robot {self.robot_path} lies in the excluded subtree "
            f"{self.excluded_path}. Exclude the prims beside the robot instead of a "
            "prim holding it."
        )


@dataclass
class SelectedPrimLeftOut(ConversionError):
    """
    A prim selected for conversion is, or lies below, a prim the conversion leaves out:

    a robot the stage marks, or an excluded prim.
    """

    prim_path: str
    """
    The selected prim.
    """

    left_out: ExcludedPrim
    """
    The outermost prim holding it that the conversion leaves out, and why.
    """

    def message(self) -> str:
        if self.prim_path == self.left_out.path:
            problem = (
                f"The selected prim {self.prim_path} is left out of the conversion "
                f"({self.left_out.reason})."
            )
        else:
            problem = (
                f"The selected prim {self.prim_path} lies in {self.left_out.path}, "
                f"which the conversion leaves out ({self.left_out.reason})."
            )
        if self.left_out.reason is ExclusionReason.REQUESTED:
            return (
                f"{problem} Exclude the prims beside the selected prim instead of a "
                "prim holding it."
            )
        return (
            f"{problem} Select environment prims beside the robot. To convert the "
            "robot as well, keep the stage's robots or convert this one as the "
            "scene's robot model."
        )


# %% stage variants


@dataclass
class VariantNotFound(ConversionError):
    """
    A variant selection names a prim, variant set or variant the stage does not have.
    """

    prim_path: str
    """
    The prim whose variant set was to be selected.
    """

    variant_set: str
    """
    The name of the variant set.
    """

    variant: str
    """
    The variant that was to be selected.
    """

    def message(self) -> str:
        return (
            f"The stage has no variant {self.variant!r} in the variant set "
            f"{self.variant_set!r} of {self.prim_path}. Select a variant the prim's "
            "variant set offers, for example with usdview's variant menu."
        )


# %% animation sources


@dataclass
class TraceNotFound(ConversionError):
    """
    The recorded body trace to animate the scene with does not exist.
    """

    path: Path
    """
    The trace file that was asked for.
    """

    def message(self) -> str:
        return (
            f"No body trace at {self.path}. Pass the .npz file the twin's recorder "
            "wrote, or leave out the trace to sample the stage's time samples."
        )


@dataclass
class TraceIncomplete(ConversionError):
    """
    The body trace lacks arrays every trace carries.
    """

    path: Path
    """
    The trace file.
    """

    missing: List[str]
    """
    The names of the arrays that are not in the file.
    """

    def message(self) -> str:
        return (
            f"The body trace {self.path} has no {', '.join(self.missing)}. Record the "
            "trace again; it needs the body paths, positions, scalar-first "
            "quaternions and the sample rate."
        )


@dataclass
class RobotRootNotFound(ConversionError):
    """
    The prim chosen as the robot holds no link, or several links none of which holds all
    the others.
    """

    path: str
    """
    The prim chosen as the robot.
    """

    candidates: List[str]
    """
    The names of the topmost links below the prim.
    """

    def message(self) -> str:
        if not self.candidates:
            problem = f"No converted link stands for {self.path} or lies below it."
        else:
            problem = (
                f"{self.path} holds several separate links: "
                f"{', '.join(self.candidates)}."
            )
        return (
            f"{problem} Choose the prim of the robot's root link, such as the robot "
            "asset or its articulation root body."
        )


# %% export


@dataclass
class ViewerNotInstalled(ConversionError):
    """
    A screenshot was asked for, but the viewer package that takes it is not installed.
    """

    distribution: str
    """
    The distribution that provides the screenshot.
    """

    def message(self) -> str:
        return (
            f"A screenshot needs the viewer: install {self.distribution} (the "
            "'viewer' extra of cramera-usd) or leave out the screenshot."
        )


@dataclass
class PublicationNotListed(ConversionError):
    """
    A published bundle is not listed in the scenes index as the export expected.
    """

    index: Path
    """
    The scenes index.
    """

    name: str
    """
    The published bundle.
    """

    def message(self) -> str:
        return (
            f"{self.index} does not list {self.name} as expected after publishing; "
            "check the index and the bundle's scene.json."
        )
