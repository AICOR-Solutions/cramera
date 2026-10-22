"""
Reading a composed USD stage into the neutral description of a converted stage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pxr import Usd
from typing_extensions import List, Optional

from cramera_usd.animation.trace import BodyTrace
from cramera_usd.exceptions import PrimNotFound, StageNotFound, StageUnreadable
from cramera_usd.scene.stage import ConvertedStage
from cramera_usd.stage.conversion import StageConversion
from cramera_usd.stage.frame import StageFrame
from cramera_usd.stage.motion import StageMotion
from cramera_usd.stage.robots import PrimExclusion
from cramera_usd.stage.variants import VariantSelection

# %% reader


@dataclass
class StageReader:
    """
    Reads a composed USD stage.
    """

    stage_path: Path
    """
    The stage file.
    """

    prim_paths: List[str] = field(default_factory=list)
    """
    The prims whose subtrees are converted; empty for the whole stage.
    """

    variant_selections: List[VariantSelection] = field(default_factory=list)
    """
    The variants selected in the stage's in-memory session layer before reading; the
    stage's files are never changed.
    """

    exclusion: PrimExclusion = field(default_factory=PrimExclusion)
    """
    The prims left out with their subtrees; by default the robots the stage marks.
    """

    composed: Optional[Usd.Stage] = field(default=None, init=False, repr=False)
    """
    The composed stage once it has been opened.
    """

    def open(self) -> Usd.Stage:
        """
        :return: The composed stage with all payloads loaded and the variants selected,
            opened on first use.
        :raises StageNotFound: When the stage file does not exist.
        :raises StageUnreadable: When the file is of a type USD does not read.
        """
        if self.composed is not None:
            return self.composed
        if not self.stage_path.is_file():
            raise StageNotFound(self.stage_path)
        if not Usd.Stage.IsSupportedFile(str(self.stage_path)):
            raise StageUnreadable(self.stage_path)
        stage = Usd.Stage.Open(str(self.stage_path), Usd.Stage.LoadAll)
        with Usd.EditContext(stage, stage.GetSessionLayer()):
            for selection in self.variant_selections:
                selection.apply(stage)
        self.composed = stage
        return stage

    def read(self) -> ConvertedStage:
        """
        :return: The neutral description of the selected part of the stage.
        """
        stage = self.open()
        frame = StageFrame.of_stage(stage)
        roots = self.selected_roots(stage)
        self.exclusion.validate(stage, roots, frame.time)
        return StageConversion(frame, roots, self.stage_path, self.exclusion).run()

    def motion(self, paths: List[str], frames_per_second: float) -> BodyTrace:
        """
        :param paths: The paths of the prims to sample.
        :param frames_per_second: The sample rate.
        :return: The world poses of the moving prims among them, sampled from the
            stage's time samples.
        """
        stage = self.open()
        return StageMotion(StageFrame.of_stage(stage), self.stage_path).trace(
            paths, frames_per_second
        )

    def selected_roots(self, stage: Usd.Stage) -> List[Usd.Prim]:
        """
        :param stage: The composed stage.
        :return: The prims whose subtrees are converted; a prim inside another selected
            prim's subtree is already covered by it.
        :raises PrimNotFound: When a selected prim does not exist.
        """
        if not self.prim_paths:
            return [stage.GetPseudoRoot()]
        roots = []
        for path in self.prim_paths:
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsActive():
                raise PrimNotFound(path)
            roots.append(prim)
        return [
            prim
            for prim in roots
            if not any(
                other != prim and prim.GetPath().HasPrefix(other.GetPath())
                for other in roots
            )
        ]
