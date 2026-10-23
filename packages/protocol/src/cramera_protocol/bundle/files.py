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

    RECORDED_ANSWERS = "recorded_answers.json"
    """
    The answers of the bundle's ready-made questions and its graph views, recorded for
    viewers that cannot answer them.
    """


class ScenesDirectoryFile(StrEnum):
    """
    The files of a scenes directory next to its bundles.
    """

    INDEX = "index.json"
    """
    The list of bundles the viewer's pickers offer.
    """


# %% meshes


class MeshFormat(StrEnum):
    """
    The mesh file formats bundles hold, by the suffix their files carry.
    """

    STL = ".stl"
    """
    Stereolithography: geometry only; colour comes from the URDF material.
    """

    OBJ = ".obj"
    """
    Wavefront OBJ, which names its material library on an ``mtllib`` line.
    """

    MATERIAL_LIBRARY = ".mtl"
    """
    The material library of an OBJ mesh.
    """

    COLLADA = ".dae"
    """
    COLLADA, which references its textures from inside the document.
    """

    GLB = ".glb"
    """
    Binary glTF: geometry, materials and textures in one file.
    """

    GLTF = ".gltf"
    """
    GlTF with separate buffers and textures.
    """
