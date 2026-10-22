"""
Reading composed USD stages into the neutral description of a converted stage.
"""

from __future__ import annotations


import numpy
import pytest
from pxr import Usd, UsdGeom, UsdLux, UsdPhysics

from cramera_protocol.bundle.conversion_report import (
    DetachedBody,
    EnvironmentArticulation,
    ExcludedPrim,
    ExclusionReason,
    SkipReason,
)
from cramera_protocol.bundle.semantics import SemanticNamespace
from cramera_usd.exceptions import (
    PrimNotFound,
    RobotExcluded,
    SelectedPrimLeftOut,
    StageNotFound,
    StageUnreadable,
    VariantNotFound,
)
from cramera_usd.names import GeneratedName
from cramera_usd.scene.kinematics import JointKind
from cramera_usd.scene.lights import LightKind
from cramera_usd.scene.materials import MaterialSource
from cramera_usd.scene.stage import ConvertedStage
from cramera_usd.stage.materials import DisplayPrimvar
from cramera_usd.stage.reader import StageReader
from cramera_usd.stage.robots import ENTITY_TYPE_ATTRIBUTE, PrimExclusion
from cramera_usd.stage.variants import VariantSelection

from .dataset.stages import (
    TEXTURES,
    Stage,
    authored_joint_paths,
    lies_in,
    link_holding,
    mesh_paths,
    open_stage,
    read,
    reproduces_link_frames,
    world_points,
)

# %% geometry and materials


class TestTexturedQuad:
    """
    An OmniPBR quad with three textures and semantic attributes.
    """

    @pytest.fixture(scope="class")
    @classmethod
    def converted(cls) -> ConvertedStage:
        return read(Stage.TEXTURED_QUAD)

    def test_texture_coordinates_are_kept_as_authored(self, converted):
        stage = open_stage(Stage.TEXTURED_QUAD)
        authored = numpy.asarray(
            UsdGeom.PrimvarsAPI(stage.GetPrimAtPath("/World/Decal"))
            .GetPrimvar("st")
            .Get()
        )
        geometry = link_holding(converted, "/World/Decal").meshes[0].geometry
        assert numpy.array_equal(
            geometry.texture_coordinates[geometry.triangles.ravel()],
            authored[[0, 1, 2, 0, 2, 3]],
        )

    def test_material_inputs_resolve_textures(self, converted):
        material = converted.materials["/World/Looks/DecalPaint"]
        assert material.source is MaterialSource.OMNI_PBR
        assert material.inputs["diffuse_texture"].path == TEXTURES / "albedo.png"
        assert material.inputs["diffuse_tint"] == (0.5, 1.0, 1.0)
        assert TEXTURES / "roughness.png" in converted.used_files

    def test_semantic_attributes_are_grouped_by_namespace(self, converted):
        semantics = {item.path: item for item in converted.semantics}
        assert semantics["/World/Decal"].attributes == {
            SemanticNamespace.SEMANTIC_DIGITAL_TWIN: {"class": "AprilTag", "tagId": 7}
        }
        assert (
            semantics["/World/Decal"].link
            == link_holding(converted, "/World/Decal").name
        )


def test_scaled_cube_keeps_its_authored_extent():
    converted = read(Stage.GLASS_PANE)
    stage = open_stage(Stage.GLASS_PANE)
    bounds = (
        UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
        .ComputeWorldBound(stage.GetPrimAtPath("/World/Pane"))
        .ComputeAlignedRange()
    )
    points = world_points(link_holding(converted, "/World/Pane"), "/World/Pane")
    assert numpy.allclose(points.min(axis=0), bounds.GetMin())
    assert numpy.allclose(points.max(axis=0), bounds.GetMax())


def test_y_up_centimetre_stage_becomes_z_up_metres():
    converted = read(Stage.Y_UP_CENTIMETRES)
    stage = open_stage(Stage.Y_UP_CENTIMETRES)
    authored = numpy.asarray(
        UsdGeom.Mesh(stage.GetPrimAtPath("/World/Marker")).GetPointsAttr().Get()
    )
    scale = UsdGeom.GetStageMetersPerUnit(stage)
    points = world_points(link_holding(converted, "/World/Marker"), "/World/Marker")
    assert numpy.allclose(points[:, 2], authored[:, 1] * scale)
    assert numpy.allclose(points[:, 0], authored[:, 0] * scale)
    assert numpy.allclose(points[:, 1], -authored[:, 2] * scale)


def test_unbound_geometry_is_shaded_by_its_display_colour():
    converted = read(Stage.Y_UP_CENTIMETRES)
    stage = open_stage(Stage.Y_UP_CENTIMETRES)
    authored = (
        UsdGeom.PrimvarsAPI(stage.GetPrimAtPath("/World/Marker"))
        .GetPrimvar(DisplayPrimvar.COLOR)
        .Get()[0]
    )
    mesh = link_holding(converted, "/World/Marker").meshes[0]
    material = converted.materials[mesh.material]
    assert material.source is MaterialSource.DISPLAY_COLOR
    assert material.inputs[DisplayPrimvar.COLOR] == pytest.approx(tuple(authored))


def test_instance_proxies_are_converted_per_instance():
    converted = read(Stage.INSTANCED_BOLTS)
    first = world_points(
        link_holding(converted, "/World/BoltA/Head"), "/World/BoltA/Head"
    )
    second = world_points(
        link_holding(converted, "/World/BoltB/Head"), "/World/BoltB/Head"
    )
    assert numpy.allclose(second - first, [1.0, 0.0, 0.0])
    assert {link.path for link in converted.links} == {
        "/World",
        "/World/BoltA",
        "/World/BoltB",
    }


def test_guide_proxy_invisible_and_unsupported_prims_are_skipped():
    converted = read(Stage.HIDDEN_PRIMS)
    assert mesh_paths(converted) == {"/World/Visible"}
    assert dict(converted.log.skipped) == {
        SkipReason.GUIDE_PURPOSE: 1,
        SkipReason.PROXY_PURPOSE: 1,
        SkipReason.INVISIBLE: 2,
        SkipReason.UNSUPPORTED_GEOMETRY: 1,
    }


def test_selected_prims_limit_the_conversion():
    assert mesh_paths(read(Stage.GLASS_PANE, "/World/Frame")) == {"/World/Frame"}


def test_nested_selections_convert_each_prim_once():
    converted = read(Stage.GLASS_PANE, "/World", "/World/Frame")
    paths = [mesh.path for link in converted.links for mesh in link.meshes]
    assert sorted(paths) == ["/World/Frame", "/World/Pane"]


def test_missing_stage_and_prim_are_refused(dataset):
    with pytest.raises(StageNotFound):
        StageReader(dataset / "missing.usda").read()
    with pytest.raises(PrimNotFound):
        read(Stage.GLASS_PANE, "/World/Nothing")


def test_a_file_that_is_no_stage_is_refused(dataset):
    with pytest.raises(StageUnreadable):
        StageReader(dataset / "two_joint_arm_record.json").read()


def test_bounds_hold_every_point_and_the_dense_core():
    converted = read(Stage.GLASS_PANE)
    points = numpy.concatenate(
        [
            world_points(link, mesh.path)
            for link in converted.links
            for mesh in link.meshes
        ]
    )
    assert converted.bounds.minimum == pytest.approx(points.min(axis=0))
    assert converted.bounds.diagonal >= converted.central_bounds.diagonal


# %% joints


class TestJointedCabinet:
    """
    A cabinet whose door, drawer, flap and wheel are jointed to its body.
    """

    @pytest.fixture(scope="class")
    @classmethod
    def converted(cls) -> ConvertedStage:
        return read(Stage.JOINTED_CABINET)

    @staticmethod
    def joint(converted, path):
        return next(joint for joint in converted.joints if joint.path == path)

    def test_joint_kinds_follow_the_usd_joint_types(self, converted):
        kinds = {
            joint.path: joint.motion.kind
            for joint in converted.joints
            if joint.path.startswith("/World/Cabinet/Joints")
        }
        assert kinds == {
            "/World/Cabinet/Joints/RootJoint": JointKind.FIXED,
            "/World/Cabinet/Joints/DoorHinge": JointKind.REVOLUTE,
            "/World/Cabinet/Joints/DrawerSlide": JointKind.PRISMATIC,
            "/World/Cabinet/Joints/WheelSpin": JointKind.CONTINUOUS,
            "/World/Cabinet/Joints/FlapHinge": JointKind.REVOLUTE,
        }

    def test_disabled_joint_yields_to_the_enabled_joint_of_its_body(self, converted):
        assert converted.log.skipped_examples[SkipReason.LOOP_CLOSING_JOINT] == [
            "/World/Cabinet/Joints/DrawerLock"
        ]

    def test_disabled_joint_still_moves_its_only_body(self, converted):
        flap = self.joint(converted, "/World/Cabinet/Joints/FlapHinge")
        assert not flap.enabled
        assert flap in converted.movable_joints

    def test_initial_values_are_recovered_from_body_poses(self, converted):
        stage = open_stage(Stage.JOINTED_CABINET)
        door_angle = (
            UsdGeom.Xformable(stage.GetPrimAtPath("/World/Cabinet/Door"))
            .GetOrderedXformOps()[1]
            .Get()
        )
        drawer = (
            UsdGeom.Xformable(stage.GetPrimAtPath("/World/Cabinet/Drawer"))
            .GetOrderedXformOps()[0]
            .Get()
        )
        slide = UsdPhysics.PrismaticJoint(
            stage.GetPrimAtPath("/World/Cabinet/Joints/DrawerSlide")
        )
        assert self.joint(
            converted, "/World/Cabinet/Joints/DoorHinge"
        ).initial_value == pytest.approx(numpy.radians(door_angle))
        assert self.joint(
            converted, "/World/Cabinet/Joints/DrawerSlide"
        ).initial_value == pytest.approx(drawer[0] - slide.GetLocalPos0Attr().Get()[0])
        assert self.joint(
            converted, "/World/Cabinet/Joints/WheelSpin"
        ).initial_value == pytest.approx(0.0)

    def test_limits_are_converted_to_radians_and_metres(self, converted):
        stage = open_stage(Stage.JOINTED_CABINET)
        hinge = UsdPhysics.RevoluteJoint(
            stage.GetPrimAtPath("/World/Cabinet/Joints/DoorHinge")
        )
        motion = self.joint(converted, "/World/Cabinet/Joints/DoorHinge").motion
        assert (motion.lower, motion.upper) == pytest.approx(
            (
                numpy.radians(hinge.GetLowerLimitAttr().Get()),
                numpy.radians(hinge.GetUpperLimitAttr().Get()),
            )
        )
        spin = self.joint(converted, "/World/Cabinet/Joints/WheelSpin").motion
        assert (spin.lower, spin.upper) == (None, None)

    def test_joint_tree_reproduces_every_link_frame(self, converted):
        assert reproduces_link_frames(converted)

    def test_geometry_keeps_its_authored_world_position(self, converted):
        stage = open_stage(Stage.JOINTED_CABINET)
        bounds = (
            UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
            .ComputeWorldBound(stage.GetPrimAtPath("/World/Cabinet/Door/Leaf"))
            .ComputeAlignedRange()
        )
        points = world_points(
            link_holding(converted, "/World/Cabinet/Door/Leaf"),
            "/World/Cabinet/Door/Leaf",
        )
        assert numpy.allclose(points.min(axis=0), bounds.GetMin())
        assert numpy.allclose(points.max(axis=0), bounds.GetMax())

    def test_rigid_body_without_joint_is_free_and_attached_to_its_asset(
        self, converted
    ):
        links = {link.path: link for link in converted.links}
        assert links["/World/Cabinet/Bin"].free
        assert not links["/World/Cabinet/Body"].free
        attachment = next(
            joint
            for joint in converted.joints
            if joint.child == links["/World/Cabinet/Bin"].name
        )
        assert (attachment.motion.kind, attachment.parent) == (
            JointKind.FIXED,
            links["/World/Cabinet"].name,
        )

    def test_joint_to_the_world_hangs_from_the_enclosing_asset(self, converted):
        links = {link.path: link for link in converted.links}
        root_joint = self.joint(converted, "/World/Cabinet/Joints/RootJoint")
        assert root_joint.parent == links["/World/Cabinet"].name
        cabinet = next(
            joint
            for joint in converted.joints
            if joint.child == links["/World/Cabinet"].name
        )
        assert cabinet.parent == converted.root_link

    def test_asset_semantics_belong_to_the_asset_link(self, converted):
        semantics = {item.path: item for item in converted.semantics}
        links = {link.path: link for link in converted.links}
        assert semantics["/World/Cabinet"].link == links["/World/Cabinet"].name

    def test_inherited_material_binding_is_used(self, converted):
        mesh = link_holding(converted, "/World/Cabinet/Body/Shell").meshes[0]
        assert (
            converted.materials[mesh.material].source is MaterialSource.PREVIEW_SURFACE
        )

    def test_names_are_unique_and_drop_the_default_prim(self, converted):
        names = [link.name for link in converted.links]
        assert len(names) == len(set(names))
        assert "Cabinet__Door" in names
        assert converted.root_link == "World"


class TestJointNamingOnlyItsFirstBody:
    """
    A door hinged to the world by a joint that names only ``physics:body0``.
    """

    @pytest.fixture(scope="class")
    @classmethod
    def converted(cls) -> ConvertedStage:
        return read(Stage.BODY0_HINGE)

    def test_value_keeps_the_sign_usd_measures_the_second_frame_with(self, converted):
        stage = open_stage(Stage.BODY0_HINGE)
        opened = (
            UsdGeom.Xformable(stage.GetPrimAtPath("/World/Door"))
            .GetOrderedXformOps()[1]
            .Get()
        )
        hinge = next(
            joint for joint in converted.joints if joint.path == "/World/Hinge"
        )
        assert hinge.initial_value == pytest.approx(-numpy.radians(opened))
        assert hinge.motion.lower <= hinge.initial_value <= hinge.motion.upper

    def test_joint_tree_reproduces_the_door(self, converted):
        assert reproduces_link_frames(converted)


class TestHingeOpenedPastHalfATurn:
    """
    A lid opened past half a turn on a hinge limited to three quarters of a turn.
    """

    @pytest.fixture(scope="class")
    @classmethod
    def converted(cls) -> ConvertedStage:
        return read(Stage.WIDE_HINGE)

    def test_value_lies_within_the_limits(self, converted):
        stage = open_stage(Stage.WIDE_HINGE)
        opened = (
            UsdGeom.Xformable(stage.GetPrimAtPath("/World/Lid"))
            .GetOrderedXformOps()[1]
            .Get()
        )
        hinge = next(
            joint for joint in converted.joints if joint.path == "/World/Hinge"
        )
        assert hinge.initial_value == pytest.approx(numpy.radians(opened))

    def test_joint_tree_reproduces_the_lid(self, converted):
        assert reproduces_link_frames(converted)


def test_stage_without_default_prim_roots_its_links_in_the_world():
    converted = read(Stage.NO_DEFAULT_PRIM)
    assert converted.root_link == GeneratedName.WORLD
    assert [joint.parent for joint in converted.joints] == [GeneratedName.WORLD]


def test_unsupported_joint_type_is_written_fixed_with_a_warning():
    converted = read(Stage.SPHERICAL_JOINT)
    assert len(converted.log.warnings) == 1
    assert all(not joint.movable for joint in converted.joints)


def test_variant_selection_brings_the_joints_without_touching_the_file():
    selection = VariantSelection("/World/Arm", "Physics", "physics")
    before = Stage.TWO_JOINT_ARM.path.read_bytes()
    plain = StageReader(Stage.TWO_JOINT_ARM.path).read()
    selected = StageReader(
        Stage.TWO_JOINT_ARM.path, variant_selections=[selection]
    ).read()
    assert plain.movable_joints == []
    assert len(selected.movable_joints) == 2
    assert Stage.TWO_JOINT_ARM.path.read_bytes() == before


def test_unknown_variant_is_refused():
    selection = VariantSelection("/World/Arm", "Physics", "rigid")
    with pytest.raises(VariantNotFound):
        StageReader(Stage.TWO_JOINT_ARM.path, variant_selections=[selection]).read()


# %% robots and excluded prims


def read_robot_markers(exclusion: PrimExclusion) -> ConvertedStage:
    """
    :param exclusion: The prims to leave out.
    :return: The robot marker stage converted under the exclusion.
    """
    return StageReader(Stage.ROBOT_MARKERS.path, exclusion=exclusion).read()


class TestMarkedRobotsAreLeftOut:
    """
    Without being asked to keep them, the robots a stage marks are not converted.
    """

    @pytest.fixture(scope="class")
    @classmethod
    def converted(cls) -> ConvertedStage:
        return read_robot_markers(PrimExclusion())

    def test_robots_are_reported_with_the_mark_found(self, converted):
        assert converted.log.excluded == [
            ExcludedPrim(
                path="/World/Robots/Rover", reason=ExclusionReason.ISAAC_ROBOT_SCHEMA
            ),
            ExcludedPrim(
                path="/World/Robots/Walker", reason=ExclusionReason.ROBOT_ENTITY_TYPE
            ),
        ]

    def test_only_the_environment_geometry_is_converted(self, converted):
        assert mesh_paths(converted) == {
            "/World/Floor",
            "/World/Robots/Pedestal/Column",
            "/World/Cell/Bench",
            "/World/Cart/Tray",
            "/World/Hook/Bar",
        }

    def test_no_link_stands_for_a_prim_of_a_robot(self, converted):
        robots = [excluded.path for excluded in converted.log.excluded]
        assert [
            link.path for link in converted.links if lies_in(link.path, robots)
        ] == []

    def test_joints_to_robot_prims_are_skipped(self, converted):
        assert converted.log.skipped_examples[SkipReason.JOINT_TO_EXCLUDED_PRIM] == [
            "/World/Joints/Tow",
            "/World/Joints/Dock",
            "/World/Joints/Grip",
        ]
        assert authored_joint_paths(converted) == set()

    def test_every_joint_connects_converted_links(self, converted):
        names = {link.name for link in converted.links}
        assert all(
            joint.parent in names and joint.child in names for joint in converted.joints
        )

    def test_body_towed_by_a_robot_is_free_on_the_world(self, converted):
        cart = next(link for link in converted.links if link.path == "/World/Cart")
        joint = next(joint for joint in converted.joints if joint.child == cart.name)
        assert (joint.parent, joint.motion.kind, cart.free) == (
            converted.root_link,
            JointKind.FIXED,
            True,
        )

    def test_prim_held_only_by_a_robot_is_static_geometry(self, converted):
        hook = next(link for link in converted.links if link.path == "/World/Hook")
        joint = next(joint for joint in converted.joints if joint.child == hook.name)
        assert (joint.parent, joint.generated, hook.free) == (
            converted.root_link,
            True,
            False,
        )

    def test_cameras_and_semantics_of_robots_are_left_out(self, converted):
        assert converted.cameras == []
        assert [item.path for item in converted.semantics] == ["/World/Cell"]

    def test_bodies_that_hung_from_a_robot_are_reported_detached(self, converted):
        assert converted.log.detached == [
            DetachedBody(
                body="/World/Hook",
                parent_body="/World/Robots/Walker",
                joint="/World/Joints/Grip",
            ),
            DetachedBody(
                body="/World/Cart",
                parent_body="/World/Robots/Rover/Chassis",
                joint="/World/Joints/Tow",
            ),
        ]


def test_entity_type_mark_is_the_attribute_the_stage_authors():
    stage = open_stage(Stage.ROBOT_MARKERS)
    assert stage.GetPrimAtPath("/World/Robots/Walker").HasAttribute(
        ENTITY_TYPE_ATTRIBUTE
    )


def test_excluded_prim_leaves_out_its_subtree():
    converted = read_robot_markers(PrimExclusion(excluded_paths=["/World/Robots"]))
    assert converted.log.excluded == [
        ExcludedPrim(path="/World/Robots", reason=ExclusionReason.REQUESTED)
    ]
    assert mesh_paths(converted) == {
        "/World/Floor",
        "/World/Cell/Bench",
        "/World/Cart/Tray",
        "/World/Hook/Bar",
    }


def test_kept_robots_stay_in_the_environment():
    kept = read_robot_markers(PrimExclusion(keep_robots=True))
    assert kept.log.excluded == []
    assert mesh_paths(kept) == {
        "/World/Floor",
        "/World/Robots/Rover/Chassis/Body",
        "/World/Robots/Rover/Chassis/Wheel/Tyre",
        "/World/Robots/Walker/Torso",
        "/World/Robots/Pedestal/Column",
        "/World/Cell/Bench",
        "/World/Cart/Tray",
        "/World/Hook/Bar",
    }
    assert authored_joint_paths(kept) == {
        "/World/Robots/Rover/Joints/WheelJoint",
        "/World/Joints/Tow",
        "/World/Joints/Dock",
        "/World/Joints/Grip",
    }


def test_robot_converted_as_its_own_model_is_kept():
    converted = read_robot_markers(PrimExclusion(robot_path="/World/Robots/Rover"))
    assert converted.log.excluded == [
        ExcludedPrim(
            path="/World/Robots/Walker", reason=ExclusionReason.ROBOT_ENTITY_TYPE
        )
    ]
    assert "/World/Robots/Rover/Chassis/Body" in mesh_paths(converted)


def test_robot_root_link_below_the_marked_prim_keeps_its_robot():
    converted = read_robot_markers(
        PrimExclusion(robot_path="/World/Robots/Rover/Chassis")
    )
    assert [excluded.path for excluded in converted.log.excluded] == [
        "/World/Robots/Walker"
    ]


def test_missing_excluded_prim_is_refused():
    with pytest.raises(PrimNotFound):
        read_robot_markers(PrimExclusion(excluded_paths=["/World/Nothing"]))


def test_robot_inside_an_excluded_prim_is_refused():
    with pytest.raises(RobotExcluded):
        read_robot_markers(
            PrimExclusion(
                excluded_paths=["/World/Robots"], robot_path="/World/Robots/Rover"
            )
        )


@pytest.mark.parametrize(
    "prim_path, left_out",
    [
        (
            "/World/Robots/Rover",
            ExcludedPrim(
                path="/World/Robots/Rover", reason=ExclusionReason.ISAAC_ROBOT_SCHEMA
            ),
        ),
        (
            "/World/Robots/Rover/Chassis",
            ExcludedPrim(
                path="/World/Robots/Rover", reason=ExclusionReason.ISAAC_ROBOT_SCHEMA
            ),
        ),
        (
            "/World/Robots/Walker/Torso",
            ExcludedPrim(
                path="/World/Robots/Walker", reason=ExclusionReason.ROBOT_ENTITY_TYPE
            ),
        ),
    ],
)
def test_selected_prim_in_a_marked_robot_is_refused(prim_path, left_out):
    with pytest.raises(SelectedPrimLeftOut) as refused:
        StageReader(Stage.ROBOT_MARKERS.path, [prim_path]).read()
    assert (refused.value.prim_path, refused.value.left_out) == (prim_path, left_out)


def test_selected_prim_in_an_excluded_prim_is_refused():
    with pytest.raises(SelectedPrimLeftOut) as refused:
        StageReader(
            Stage.ROBOT_MARKERS.path,
            ["/World/Robots/Pedestal"],
            exclusion=PrimExclusion(excluded_paths=["/World/Robots"]),
        ).read()
    assert refused.value.left_out == ExcludedPrim(
        path="/World/Robots", reason=ExclusionReason.REQUESTED
    )


@pytest.mark.parametrize(
    "exclusion",
    [PrimExclusion(keep_robots=True), PrimExclusion(robot_path="/World/Robots/Rover")],
)
def test_selected_prim_in_a_kept_robot_is_converted(exclusion):
    converted = StageReader(
        Stage.ROBOT_MARKERS.path, ["/World/Robots/Rover/Chassis"], exclusion=exclusion
    ).read()
    assert mesh_paths(converted) == {
        "/World/Robots/Rover/Chassis/Body",
        "/World/Robots/Rover/Chassis/Wheel/Tyre",
    }


def test_joints_to_robots_beside_the_selected_prims_are_skipped():
    whole_stage = read_robot_markers(PrimExclusion())
    robots = [excluded.path for excluded in whole_stage.log.excluded]
    converted = StageReader(
        Stage.ROBOT_MARKERS.path, ["/World/Cart", "/World/Hook", "/World/Joints"]
    ).read()
    assert (
        converted.log.skipped_examples[SkipReason.JOINT_TO_EXCLUDED_PRIM]
        == whole_stage.log.skipped_examples[SkipReason.JOINT_TO_EXCLUDED_PRIM]
    )
    assert authored_joint_paths(converted) == set()
    assert [link.path for link in converted.links if lies_in(link.path, robots)] == []
    assert converted.log.detached == whole_stage.log.detached


# %% robot parts and articulations the stage leaves unmarked


def test_robot_parts_beside_a_marked_robot_are_reported_with_their_moving_joints():
    converted = StageReader(Stage.DETACHED_GRIPPER.path).read()
    assert converted.log.detached == [
        DetachedBody(
            body="/World/Tote",
            parent_body="/World/Robots/Rover/Chassis",
            joint="/World/Robots/Rover/Joints/Carry",
        ),
        DetachedBody(
            body="/World/Robots/RoverGripper/Palm",
            parent_body="/World/Robots/Rover/Chassis",
            joint="/World/Robots/RoverGripper/Mount",
            movable_joints=["/World/Robots/RoverGripper/FingerSlide"],
        ),
    ]


def test_kept_robot_detaches_nothing():
    converted = StageReader(
        Stage.DETACHED_GRIPPER.path, exclusion=PrimExclusion(keep_robots=True)
    ).read()
    assert converted.log.detached == []


@pytest.mark.parametrize(
    "exclusion",
    [
        PrimExclusion(),
        PrimExclusion(keep_robots=True),
        PrimExclusion(robot_path="/World/Robots/Arm"),
    ],
)
def test_articulations_with_moving_joints_outside_robots_are_reported(exclusion):
    converted = StageReader(
        Stage.UNMARKED_ARTICULATION.path, exclusion=exclusion
    ).read()
    assert converted.log.articulations == [
        EnvironmentArticulation(
            path="/World/Robots/Amr",
            movable_joints=[
                "/World/Robots/Amr/Joints/DriveX",
                "/World/Robots/Amr/Joints/LidSlide",
            ],
        ),
        EnvironmentArticulation(
            path="/World/Cabinet", movable_joints=["/World/Cabinet/Joints/Hinge"]
        ),
        EnvironmentArticulation(
            path="/World/Lift/Mast", movable_joints=["/World/Lift/Joints/Raise"]
        ),
    ]


def test_excluded_articulation_is_not_reported():
    converted = StageReader(
        Stage.UNMARKED_ARTICULATION.path,
        exclusion=PrimExclusion(excluded_paths=["/World/Robots/Amr"]),
    ).read()
    assert [item.path for item in converted.log.articulations] == [
        "/World/Cabinet",
        "/World/Lift/Mast",
    ]


# %% lights and cameras


def test_lights_carry_direction_size_and_exposure():
    converted = read(Stage.LIT_ROOM)
    stage = open_stage(Stage.LIT_ROOM)
    lights = {light.kind: light for light in converted.lights}
    panel = UsdLux.RectLight(stage.GetPrimAtPath("/World/Panel"))
    rectangle = lights[LightKind.RECTANGLE]
    assert (
        rectangle.intensity
        == panel.GetIntensityAttr().Get() * 2 ** panel.GetExposureAttr().Get()
    )
    assert (rectangle.width, rectangle.height) == pytest.approx(
        (panel.GetWidthAttr().Get(), panel.GetHeightAttr().Get())
    )
    assert numpy.allclose(rectangle.emission_direction, [0.0, 0.0, -1.0])
    sun = UsdLux.DistantLight(stage.GetPrimAtPath("/World/Sun"))
    assert lights[LightKind.DISTANT].color_temperature == (
        sun.GetColorTemperatureAttr().Get()
    )
    assert lights[LightKind.DISTANT].angle == pytest.approx(sun.GetAngleAttr().Get())
    tilt = numpy.radians(30.0)
    assert numpy.allclose(
        lights[LightKind.DISTANT].emission_direction,
        [0.0, numpy.sin(tilt), -numpy.cos(tilt)],
    )
    dome = UsdLux.DomeLight(stage.GetPrimAtPath("/World/Sky"))
    assert lights[LightKind.DOME].color == pytest.approx(
        tuple(dome.GetColorAttr().Get())
    )


def test_cameras_carry_their_vertical_field_of_view():
    converted = read(Stage.LIT_ROOM)
    stage = open_stage(Stage.LIT_ROOM)
    camera = UsdGeom.Camera(stage.GetPrimAtPath("/World/Overview"))
    expected = numpy.degrees(
        2.0
        * numpy.arctan(
            camera.GetVerticalApertureAttr().Get()
            / 2.0
            / camera.GetFocalLengthAttr().Get()
        )
    )
    assert [item.vertical_field_of_view for item in converted.cameras] == pytest.approx(
        [expected]
    )


def test_ontology_and_twin_attributes_are_both_read():
    converted = read(Stage.ANNOTATED_LAB)
    namespaces = {
        namespace for item in converted.semantics for namespace in item.attributes
    }
    assert namespaces == set(SemanticNamespace)
