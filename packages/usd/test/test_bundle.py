"""
``cramera-import`` end to end: a test stage in, a complete scene bundle out.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import numpy
import pytest
from PIL import Image
from pxr import UsdGeom

from cramera_protocol.bundle.conversion_report import (
    ConversionReport,
    ExclusionReason,
    SkipReason,
)
from cramera_protocol.bundle.files import (
    BundleFile,
    MeshFormat,
    ScenesDirectoryFile,
)
from cramera_protocol.bundle.index import InvalidSceneName, SceneIndex
from cramera_protocol.bundle.lighting import Lighting
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.bundle.semantics import (
    LengthUnit,
    SemanticNamespace,
    Semantics,
    UpAxis,
)
from cramera_protocol.bundle.trajectory import Trajectory
from cramera_protocol.version import CURRENT_VERSION
from cramera_usd.animation.animator import ENVIRONMENT_MODEL
from cramera_usd.bundle.camera import SceneCamera
from cramera_usd.bundle.layout import Decimals
from cramera_usd.bundle.scene import DEFAULT_EXPOSURE
from cramera_usd.commands.import_scene import ImportOption, main
from cramera_usd.distribution import Distribution
from cramera_usd.exceptions import SelectedPrimLeftOut
from cramera_usd.gltf.format import AttributeName, GltfKey, MaterialKey
from cramera_usd.materials.mapper import MaterialMapper
from cramera_usd.materials.omni_pbr import OmniPhysicallyBasedInput
from cramera_usd.materials.physically_based import AlphaMode
from cramera_usd.materials.transmission import TransmissionBlending
from cramera_usd.stage.reader import StageReader
from cramera_usd.stage.robots import PrimExclusion
from cramera_usd.urdf import UrdfAttribute, UrdfTag

from .dataset.glb import GlbContent
from .dataset.runs import convert, load
from .dataset.stages import TEXTURES, Stage, open_stage, read

# %% helpers


def scene_of(bundle: Path) -> SceneDescription:
    """
    :param bundle: A bundle directory.
    :return: Its scene description.
    """
    return SceneDescription.from_json(load(bundle / BundleFile.SCENE))


def report_of(bundle: Path) -> ConversionReport:
    """
    :param bundle: A bundle directory.
    :return: Its conversion report.
    """
    return ConversionReport.from_json(load(bundle / BundleFile.CONVERSION_REPORT))


# %% scene files


class TestCabinetBundle:
    """
    The bundle of the jointed cabinet.
    """

    @pytest.fixture(scope="class")
    @classmethod
    def bundle(cls, tmp_path_factory) -> Path:
        return convert(
            Stage.JOINTED_CABINET, tmp_path_factory.mktemp("scenes"), "cabinet"
        )

    def test_scene_declares_one_environment_model_keeping_its_materials(self, bundle):
        scene = scene_of(bundle)
        converted = read(Stage.JOINTED_CABINET)
        (model,) = scene.models
        assert (model.name, model.urdf, model.prefix, model.robot) == (
            ENVIRONMENT_MODEL,
            BundleFile.ENVIRONMENT,
            "",
            False,
        )
        assert model.links == len(converted.links)
        assert model.movable_joints == [
            joint.name for joint in converted.movable_joints
        ]
        assert model.preserve_materials is True
        assert scene.source.converter == Distribution.CONVERTER.version()
        assert scene.format_version == CURRENT_VERSION

    def test_scene_is_labelled_with_the_stage_file_without_labels(self, bundle):
        scene = scene_of(bundle)
        assert scene.environment_name == scene.task == Stage.JOINTED_CABINET.value
        assert scene.robot is None

    def test_rendering_turns_off_the_viewer_floor_and_points_at_the_lighting(
        self, bundle
    ):
        rendering = scene_of(bundle).rendering
        assert rendering.ground_plane is False
        assert rendering.ambient_occlusion is False
        assert rendering.environment == BundleFile.LIGHTING
        assert (bundle / rendering.environment).is_file()

    def test_rendering_keeps_the_default_exposure_and_shadows_the_dense_core(
        self, bundle
    ):
        rendering = scene_of(bundle).rendering
        converted = read(Stage.JOINTED_CABINET)
        assert rendering.exposure == DEFAULT_EXPOSURE
        assert rendering.shadow_bounds == converted.central_bounds.to_protocol(
            Decimals.POSITION
        )

    def test_static_trajectory_holds_the_initial_joint_values(self, bundle):
        trajectory = Trajectory.from_json(load(bundle / BundleFile.TRAJECTORY))
        converted = read(Stage.JOINTED_CABINET)
        assert trajectory.frames == [
            {joint.name: joint.initial_value for joint in converted.movable_joints}
        ]
        assert len(trajectory.base) == len(trajectory.objects) == 1

    def test_urdf_links_reference_existing_meshes(self, bundle):
        robot = ElementTree.parse(bundle / BundleFile.ENVIRONMENT).getroot()
        files = [mesh.get(UrdfAttribute.FILENAME) for mesh in robot.iter(UrdfTag.MESH)]
        assert files and all((bundle / file).is_file() for file in files)
        assert sorted(
            bundle.joinpath(BundleFile.MESHES).glob(f"*{MeshFormat.GLB}")
        ) == (sorted(bundle / file for file in files))

    def test_index_lists_the_scene(self, bundle):
        index = SceneIndex.from_json(load(bundle.parent / ScenesDirectoryFile.INDEX))
        assert [entry.name for entry in index.scenes] == [bundle.name]
        assert index.default == bundle.name

    def test_report_lists_skipped_joints(self, bundle):
        assert report_of(bundle).skipped_examples[SkipReason.LOOP_CLOSING_JOINT] == [
            "/World/Cabinet/Joints/DrawerLock"
        ]

    def test_report_counts_what_was_written(self, bundle):
        report = report_of(bundle)
        converted = read(Stage.JOINTED_CABINET)
        assert report.counts == {
            str(key): count for key, count in converted.log.counts.items()
        }
        assert report.animation is None


def test_reconversion_removes_meshes_of_vanished_links(tmp_path):
    stale = tmp_path / "quad" / BundleFile.MESHES / f"Gone{MeshFormat.GLB}"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"glTF")
    convert(Stage.TEXTURED_QUAD, tmp_path, "quad")
    assert not stale.exists()


def test_camera_options_set_the_initial_view(tmp_path):
    position, target, field_of_view = [1.0, -2.0, 1.5], [0.0, 0.0, 0.5], 40.0
    bundle = convert(
        Stage.GLASS_PANE,
        tmp_path,
        "pane",
        ImportOption.CAMERA_POSITION,
        *map(str, position),
        ImportOption.CAMERA_TARGET,
        *map(str, target),
        ImportOption.CAMERA_FIELD_OF_VIEW,
        str(field_of_view),
    )
    camera = scene_of(bundle).camera
    assert camera.position.to_json() == position
    assert camera.target.to_json() == target
    assert camera.field_of_view == field_of_view
    converted = read(Stage.GLASS_PANE)
    framing = SceneCamera.framing(converted.central_bounds, converted.bounds)
    assert camera.far == round(framing.far, Decimals.CLIP_DISTANCE)


@pytest.mark.parametrize(
    "options",
    [
        [ImportOption.CAMERA_POSITION, "1", "-2", "1.5"],
        [ImportOption.CAMERA_TARGET, "0", "0", "0.5"],
        [ImportOption.CAMERA_FIELD_OF_VIEW, "40"],
    ],
)
def test_camera_options_without_position_and_target_are_refused(tmp_path, options):
    with pytest.raises(SystemExit):
        convert(Stage.GLASS_PANE, tmp_path, "pane", *options)
    assert not (tmp_path / "pane").exists()


def test_exposure_option_sets_the_tone_mapping_exposure(tmp_path):
    exposure = 1.3
    bundle = convert(
        Stage.GLASS_PANE, tmp_path, "pane", ImportOption.EXPOSURE, str(exposure)
    )
    assert scene_of(bundle).rendering.exposure == exposure


def test_labels_name_the_scene_in_the_picker(tmp_path):
    environment, task = "Glazing workshop", "One pane"
    bundle = convert(
        Stage.GLASS_PANE,
        tmp_path,
        "pane",
        ImportOption.ENVIRONMENT_NAME,
        environment,
        ImportOption.TASK,
        task,
    )
    scene = scene_of(bundle)
    assert (scene.environment_name, scene.task) == (environment, task)


def test_first_authored_camera_gives_the_initial_view(tmp_path):
    bundle = convert(Stage.LIT_ROOM, tmp_path, "room")
    camera = scene_of(bundle).camera
    stage = open_stage(Stage.LIT_ROOM)
    authored = UsdGeom.Camera(stage.GetPrimAtPath("/World/Overview"))
    position = authored.GetLocalTransformation().ExtractTranslation()
    vertical = numpy.degrees(
        2.0
        * numpy.arctan(
            authored.GetVerticalApertureAttr().Get()
            / 2.0
            / authored.GetFocalLengthAttr().Get()
        )
    )
    assert camera.position.to_json() == pytest.approx(list(position))
    assert camera.field_of_view == pytest.approx(vertical, abs=1e-3)
    looking = numpy.array(camera.target.to_json()) - numpy.array(position)
    assert looking / numpy.linalg.norm(looking) == pytest.approx(
        [0.0, 1.0, 0.0], abs=1e-6
    )


def test_invalid_bundle_name_writes_nothing(tmp_path):
    with pytest.raises(InvalidSceneName):
        convert(Stage.GLASS_PANE, tmp_path, "two words")
    assert list(tmp_path.iterdir()) == []


# %% robots and excluded prims


def test_report_lists_the_robots_left_out_with_the_mark_found(tmp_path):
    bundle = convert(Stage.ROBOT_MARKERS, tmp_path, "cell")
    assert [(item.path, item.reason) for item in report_of(bundle).excluded] == [
        ("/World/Robots/Rover", ExclusionReason.ISAAC_ROBOT_SCHEMA),
        ("/World/Robots/Walker", ExclusionReason.ROBOT_ENTITY_TYPE),
    ]


def test_urdf_joints_connect_the_links_it_declares(tmp_path):
    bundle = convert(Stage.ROBOT_MARKERS, tmp_path, "cell")
    robot = ElementTree.parse(bundle / BundleFile.ENVIRONMENT).getroot()
    links = {link.get(UrdfAttribute.NAME) for link in robot.iter(UrdfTag.LINK)}
    connected = {
        element.get(UrdfAttribute.LINK)
        for joint in robot.iter(UrdfTag.JOINT)
        for element in [joint.find(UrdfTag.PARENT), joint.find(UrdfTag.CHILD)]
    }
    assert connected <= links
    assert len(links) == len(read(Stage.ROBOT_MARKERS).links)


def test_exclude_option_leaves_out_a_subtree(tmp_path):
    bundle = convert(
        Stage.ROBOT_MARKERS, tmp_path, "cell", ImportOption.EXCLUDE, "/World/Robots"
    )
    assert [(item.path, item.reason) for item in report_of(bundle).excluded] == [
        ("/World/Robots", ExclusionReason.REQUESTED)
    ]
    semantics = Semantics.from_json(load(bundle / BundleFile.SEMANTICS))
    assert list(semantics.prims) == ["/World/Cell"]


def test_keep_robots_option_keeps_the_marked_robots_in_the_environment(tmp_path):
    bundle = convert(Stage.ROBOT_MARKERS, tmp_path, "cell", ImportOption.KEEP_ROBOTS)
    kept = StageReader(
        Stage.ROBOT_MARKERS.path, exclusion=PrimExclusion(keep_robots=True)
    ).read()
    assert report_of(bundle).excluded == []
    (model,) = scene_of(bundle).models
    assert model.links == len(kept.links)


def test_robot_option_keeps_its_robot_as_a_model_of_its_own(tmp_path):
    bundle = convert(
        Stage.ROBOT_MARKERS, tmp_path, "cell", ImportOption.ROBOT, "/World/Robots/Rover"
    )
    scene = scene_of(bundle)
    assert [model.robot for model in scene.models] == [False, True]
    assert (bundle / scene.models[1].urdf).is_file()
    assert [item.path for item in report_of(bundle).excluded] == [
        "/World/Robots/Walker"
    ]


def test_prim_option_inside_a_robot_writes_no_bundle(tmp_path):
    with pytest.raises(SelectedPrimLeftOut):
        convert(
            Stage.ROBOT_MARKERS,
            tmp_path,
            "rover",
            ImportOption.PRIM,
            "/World/Robots/Rover/Chassis",
        )
    assert list(tmp_path.iterdir()) == []


def test_report_lists_the_bodies_detached_from_left_out_robots(tmp_path):
    bundle = convert(Stage.DETACHED_GRIPPER, tmp_path, "gripper")
    converted = StageReader(Stage.DETACHED_GRIPPER.path).read()
    assert report_of(bundle).detached == converted.log.detached


def test_report_lists_the_articulations_kept_in_the_environment(tmp_path):
    bundle = convert(Stage.UNMARKED_ARTICULATION, tmp_path, "articulations")
    converted = StageReader(Stage.UNMARKED_ARTICULATION.path).read()
    assert report_of(bundle).articulations == converted.log.articulations


def printed_summary(stage: Stage, scenes: Path, capsys) -> str:
    """
    :param stage: A test stage.
    :param scenes: The scenes directory.
    :param capsys: The captured output.
    :return: What ``cramera-import`` printed for the stage.
    """
    convert(stage, scenes, Path(stage.value).stem)
    return capsys.readouterr().out


def test_summary_names_every_detached_body_and_its_joint(tmp_path, capsys):
    printed = printed_summary(Stage.DETACHED_GRIPPER, tmp_path, capsys)
    detached = StageReader(Stage.DETACHED_GRIPPER.path).read().log.detached
    assert all(item.body in printed and item.joint in printed for item in detached)


def test_summary_names_every_articulation_kept_in_the_environment(tmp_path, capsys):
    printed = printed_summary(Stage.UNMARKED_ARTICULATION, tmp_path, capsys)
    articulations = (
        StageReader(Stage.UNMARKED_ARTICULATION.path).read().log.articulations
    )
    assert all(item.path in printed for item in articulations)


def test_summary_prints_the_warnings(tmp_path, capsys):
    printed = printed_summary(Stage.SPHERICAL_JOINT, tmp_path, capsys)
    warnings = read(Stage.SPHERICAL_JOINT).log.warnings
    assert len(warnings) == 1
    assert all(warning in printed for warning in warnings)


# %% meshes


def test_textured_quad_glb_flips_v_and_packs_roughness_with_metalness(tmp_path):
    bundle = convert(Stage.TEXTURED_QUAD, tmp_path, "quad")
    stage = open_stage(Stage.TEXTURED_QUAD)
    authored = numpy.asarray(
        UsdGeom.PrimvarsAPI(stage.GetPrimAtPath("/World/Decal")).GetPrimvar("st").Get()
    )
    (glb,) = bundle.joinpath(BundleFile.MESHES).glob(f"*{MeshFormat.GLB}")
    content = GlbContent.of_bytes(glb.read_bytes())
    primitive = content.primitive(0)
    coordinates = content.accessor(
        primitive[GltfKey.ATTRIBUTES][AttributeName.TEXTURE_COORDINATES]
    )
    assert sorted(map(tuple, coordinates)) == sorted(
        (first, 1.0 - second) for first, second in authored
    )
    material = content.document[GltfKey.MATERIALS][primitive[GltfKey.MATERIAL]]
    texture = content.document[GltfKey.TEXTURES][
        material[MaterialKey.METALLIC_ROUGHNESS][
            MaterialKey.METALLIC_ROUGHNESS_TEXTURE
        ][GltfKey.INDEX]
    ]
    packed = numpy.asarray(
        Image.open(io.BytesIO(content.embedded(texture[GltfKey.SOURCE])))
    )
    assert numpy.array_equal(
        packed[..., 1], numpy.asarray(Image.open(TEXTURES / "roughness.png"))
    )
    assert numpy.array_equal(
        packed[..., 2], numpy.asarray(Image.open(TEXTURES / "metallic.png"))
    )


def test_glass_glb_is_blended_without_transmission_extension(tmp_path):
    bundle = convert(Stage.GLASS_PANE, tmp_path, "pane")
    converted = read(Stage.GLASS_PANE)
    pane = next(link for link in converted.links if link.path == "/World/Pane")
    glass = MaterialMapper().map(converted.materials["/World/Looks/Glass"])
    drawn = TransmissionBlending().approximate(glass)
    glb = bundle / BundleFile.MESHES / f"{pane.name}{MeshFormat.GLB}"
    materials = GlbContent.of_bytes(glb.read_bytes()).document[GltfKey.MATERIALS]
    written = next(
        material for material in materials if material[GltfKey.NAME] == glass.name
    )
    assert written[MaterialKey.METALLIC_ROUGHNESS][
        MaterialKey.BASE_COLOR_FACTOR
    ] == list(drawn.base_color_factor)
    assert written[MaterialKey.ALPHA_MODE] == AlphaMode.BLEND
    assert written[MaterialKey.DOUBLE_SIDED] is True
    assert written[GltfKey.EXTRAS] == {
        MaterialKey.TRANSMISSION_FACTOR: glass.transmission,
        MaterialKey.INDEX_OF_REFRACTION: glass.index_of_refraction,
        MaterialKey.BASE_COLOR_FACTOR: list(glass.base_color_factor),
        MaterialKey.METALLIC_FACTOR: glass.metallic_factor,
    }
    assert GltfKey.EXTENSIONS not in written


def test_unmapped_material_inputs_are_reported(tmp_path):
    bundle = convert(Stage.TEXTURED_QUAD, tmp_path, "quad")
    assert report_of(bundle).unmapped_inputs == {
        "/World/Looks/DecalPaint": [OmniPhysicallyBasedInput.ALBEDO_BRIGHTNESS]
    }


def test_semantics_ride_on_the_glb_node_of_their_prim(tmp_path):
    bundle = convert(Stage.TEXTURED_QUAD, tmp_path, "quad")
    (glb,) = bundle.joinpath(BundleFile.MESHES).glob(f"*{MeshFormat.GLB}")
    (node,) = GlbContent.of_bytes(glb.read_bytes()).document[GltfKey.NODES]
    semantics = Semantics.from_json(load(bundle / BundleFile.SEMANTICS))
    assert (
        node[GltfKey.EXTRAS][SemanticNamespace.SEMANTIC_DIGITAL_TWIN]
        == semantics.prims["/World/Decal"].semantic_digital_twin
    )


# %% sidecars


def test_semantics_name_each_prims_link(tmp_path):
    bundle = convert(Stage.TEXTURED_QUAD, tmp_path, "quad")
    semantics = Semantics.from_json(load(bundle / BundleFile.SEMANTICS))
    converted = read(Stage.TEXTURED_QUAD)
    (decal,) = [link for link in converted.links if link.meshes]
    prim = semantics.prims["/World/Decal"]
    assert (prim.link, prim.model) == (decal.name, None)
    assert prim.semantic_digital_twin == {"class": "AprilTag", "tagId": 7}
    assert (semantics.units, semantics.up_axis) == (LengthUnit.METRES, UpAxis.Z)


def test_lighting_describes_sun_dome_and_panels(tmp_path):
    bundle = convert(Stage.LIT_ROOM, tmp_path, "room")
    lighting = Lighting.from_json(load(bundle / BundleFile.LIGHTING))
    converted = read(Stage.LIT_ROOM)
    (panel,) = lighting.panels
    stage_panel = next(
        light for light in converted.lights if light.path == "/World/Panel"
    )
    assert panel.normal.to_json() == pytest.approx(list(stage_panel.emission_direction))
    assert panel.center.to_json() == pytest.approx(list(stage_panel.pose.translation))
    sun = next(light for light in converted.lights if light.path == "/World/Sun")
    assert lighting.sun.direction.to_json() == pytest.approx(
        list(sun.emission_direction), abs=1e-4
    )
    dome = next(light for light in converted.lights if light.path == "/World/Sky")
    assert lighting.dome.intensity == dome.intensity


def test_a_stage_without_lights_writes_empty_lighting(tmp_path):
    bundle = convert(Stage.GLASS_PANE, tmp_path, "pane")
    lighting = Lighting.from_json(load(bundle / BundleFile.LIGHTING))
    assert (lighting.sun, lighting.dome, lighting.panels) == (None, None, [])


def test_missing_textures_are_reported_not_replaced(tmp_path):
    stage = tmp_path / "stage" / Stage.TEXTURED_QUAD.value
    stage.parent.mkdir()
    stage.write_bytes(Stage.TEXTURED_QUAD.path.read_bytes())
    scenes = tmp_path / "scenes"
    main([str(stage), ImportOption.NAME, "quad", ImportOption.OUT, str(scenes)])
    report = report_of(scenes / "quad")
    converted = read(Stage.TEXTURED_QUAD)
    authored = [path.name for path in converted.used_files if path.parent == TEXTURES]
    assert sorted(Path(texture).name for texture in report.missing_textures) == sorted(
        authored
    )
    assert scene_of(scenes / "quad").missing_assets == report.missing_textures
