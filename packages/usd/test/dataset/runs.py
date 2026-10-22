"""
The recorded run of the two-joint arm, and helpers converting it.
"""

from __future__ import annotations

import json
from pathlib import Path

from typing_extensions import Any

from cramera_usd.commands.import_scene import ImportOption, main
from cramera_usd.stage.variants import VariantSelection

from .stages import DATASET, Stage

# %% recorded run

TRACE = DATASET / "two_joint_arm_trace.npz"
"""
The arm's body world poses at 2 Hz, in the twin recorder's format.
"""

RECORD = DATASET / "two_joint_arm_record.json"
"""
The recorded steps of the arm's run, on the recorder's clock.
"""

# %% prims

ARM = "/World/Arm"
"""
The arm's root prim.
"""

PHYSICS = VariantSelection(ARM, "Physics", "physics")
"""
The variant holding the arm's rigid bodies and joints.
"""

SHOULDER = "/World/Arm/Joints/Shoulder"
"""
The arm's hinge.
"""

SLIDE = "/World/Arm/Joints/Slide"
"""
The arm's slide.
"""

UPPER = "/World/Arm/Base/Upper"
"""
The body the shoulder turns.
"""

LOWER = "/World/Arm/Base/Upper/Lower"
"""
The body the slide moves.
"""

PUCK = "/World/Puck"
"""
A free body pushed around during the run.
"""

CRATE = "/World/Crate"
"""
A free body that rests during the run.
"""

# %% conversion


def convert(stage: Stage, scenes: Path, name: str, *options: str) -> Path:
    """
    Run ``cramera-import`` on a test stage.

    :param stage: The test stage.
    :param scenes: The scenes directory.
    :param name: The bundle name.
    :param options: Further command line options.
    :return: The bundle directory.
    """
    main(
        [
            str(stage.path),
            ImportOption.NAME,
            name,
            ImportOption.OUT,
            str(scenes),
            *options,
        ]
    )
    return scenes / name


def convert_arm(scenes: Path, name: str, *options: str) -> Path:
    """
    Run ``cramera-import`` on the arm with its physics variant selected.

    :param scenes: The scenes directory.
    :param name: The bundle name.
    :param options: Further command line options.
    :return: The bundle directory.
    """
    return convert(
        Stage.TWO_JOINT_ARM,
        scenes,
        name,
        ImportOption.VARIANT,
        PHYSICS.prim_path,
        PHYSICS.variant_set,
        PHYSICS.variant,
        *options,
    )


def load(path: Path) -> Any:
    """
    :param path: A JSON file.
    :return: Its decoded content.
    """
    return json.loads(path.read_text(encoding="utf-8"))
