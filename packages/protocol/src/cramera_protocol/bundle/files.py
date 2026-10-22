"""
The files of a scene bundle and of a scenes directory.
"""

from __future__ import annotations

from enum import StrEnum

# %% files


class BundleFile(StrEnum):
    """
    The files and directories of a scene bundle, relative to the bundle directory.
    """

    SCENE = "scene.json"
    """
    The scene description the viewer loads first.
    """

    TRAJECTORY = "trajectory.json"
    """
    Joint values and poses per frame.
    """

    STATECHARTS = "statecharts.json"
    """
    The motion statecharts a recorded run went through.
    """

    ENVIRONMENT = "environment.urdf"
    """
    The links and joints of a converted stage.
    """

    MESHES = "meshes"
    """
    The directory holding the meshes of the bundle's models.
    """

    OBJECT_MESHES = "meshes/objects"
    """
    The directory holding one mesh per free object.
    """

    SEMANTICS = "semantics.json"
    """
    The semantic attributes of converted stage prims.
    """

    LIGHTING = "lighting.json"
    """
    The sun, dome and ceiling panels of a converted stage.
    """

    CONVERSION_REPORT = "conversion_report.json"
    """
    What a conversion read, wrote and left out.
    """

    RESIDUALS = "residuals.csv"
    """
    How far a replayed conversion strays from its recording, per body and joint.
    """

    ACCEPTANCE_METRICS = "acceptance_metrics.json"
    """
    The measured outcome of a recorded task demo.
    """


class ScenesDirectoryFile(StrEnum):
    """
    The files of a scenes directory next to its bundles.
    """

    INDEX = "index.json"
    """
    The list of bundles the viewer's pickers offer.
    """
