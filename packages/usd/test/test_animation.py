"""
Playback of recorded body motion: joint values recovered from body world poses, the
robot as a model of its own, moving free bodies as objects, recorded steps as segments,
and the forward kinematics check of all of it.
"""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree
from dataclasses import replace
from pathlib import Path

import numpy
import pytest
from pxr import Usd, UsdGeom

from cramera_protocol.bundle.conversion_report import ConversionReport
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.residuals import ResidualKind, ResidualsTable
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.bundle.semantics import Semantics
from cramera_protocol.bundle.trajectory import Trajectory
from cramera_usd.animation.animation import SceneAnimation
from cramera_usd.animation.animator import ENVIRONMENT_MODEL, SceneAnimator
from cramera_usd.animation.deviation import ResidualTolerance
from cramera_usd.animation.link_tree import LinkTree
from cramera_usd.animation.robot_naming import RobotNaming
from cramera_usd.animation.run_record import PlaybackClock, RecordedRun, StepSegment
from cramera_usd.animation.trace import BodyTrace, TraceArray
from cramera_usd.commands.import_scene import (
    DEFAULT_FRAMES_PER_SECOND,
    ImportOption,
)
from cramera_usd.exceptions import RobotRootNotFound, TraceIncomplete, TraceNotFound
from cramera_usd.geometry.transforms import RigidTransform, TransformTrack
from cramera_usd.names import NameSeparator, PrimPath
from cramera_usd.scene.kinematics import Link
from cramera_usd.scene.stage import ConvertedStage
from cramera_usd.stage.reader import StageReader
from cramera_usd.urdf import UrdfAttribute, UrdfTag

from .dataset.runs import (
    ARM,
    CRATE,
    LOWER,
    PHYSICS,
    PUCK,
    RECORD,
    SHOULDER,
    SLIDE,
    TRACE,
    UPPER,
    convert_arm,
    load,
)
from .dataset.stages import Stage

# %% helpers


def joint_name(converted: ConvertedStage, path: str) -> str:
    """
    :param converted: The converted stage.
    :param path: A joint prim's path.
    :return: The converted name of the joint.
    """
    return next(joint.name for joint in converted.joints if joint.path == path)


def link_name(converted: ConvertedStage, path: str) -> str:
    """
    :param converted: The converted stage.
    :param path: A prim's path.
    :return: The converted name of the link standing for the prim.
    """
    return next(link.name for link in converted.links if link.path == path)


def authored(stage: Usd.Stage, path: str, operation: str, seconds: float) -> object:
    """
    :param stage: The arm stage.
    :param path: A prim's path.
    :param operation: An xform operation's attribute name.
    :param seconds: A time in seconds.
    :return: The value the operation takes at the time.
    """
    return (
        stage.GetPrimAtPath(path)
        .GetAttribute(operation)
        .Get(Usd.TimeCode(seconds * stage.GetTimeCodesPerSecond()))
    )


def world_pose(stage: Usd.Stage, path: str, seconds: float) -> RigidTransform:
    """
    :param stage: The arm stage.
    :param path: A prim's path.
    :param seconds: A time in seconds.
    :return: The prim's rigid world pose at the time, as the stage composes it.
    """
    cache = UsdGeom.XformCache(Usd.TimeCode(seconds * stage.GetTimeCodesPerSecond()))
    matrix = numpy.array(cache.GetLocalToWorldTransform(stage.GetPrimAtPath(path))).T
    return RigidTransform.rigid_part(matrix)


def displaced(trace: BodyTrace, path: str, frame: int, distance: float) -> BodyTrace:
    """
    :param trace: A trace.
    :param path: A recorded body.
    :param frame: A frame.
    :param distance: How far to lift the body at that frame, in metres.
    :return: The trace with the body lifted at the frame.
    """
    matrices = trace.poses[path].matrices.copy()
    matrices[frame, 2, 3] += distance
    return replace(trace, poses={**trace.poses, path: TransformTrack(matrices)})


@pytest.fixture(scope="module")
def stage() -> Usd.Stage:
    return Usd.Stage.Open(str(Stage.TWO_JOINT_ARM.path))


@pytest.fixture(scope="module")
def converted() -> ConvertedStage:
    return StageReader(Stage.TWO_JOINT_ARM.path, variant_selections=[PHYSICS]).read()


@pytest.fixture(scope="module")
def trace() -> BodyTrace:
    return BodyTrace.from_file(TRACE)


@pytest.fixture(scope="module")
def trace_times(trace) -> numpy.ndarray:
    return numpy.arange(trace.frame_count) / trace.frames_per_second


@pytest.fixture(scope="module")
def animation(converted, trace) -> SceneAnimation:
    return SceneAnimator(converted, trace).animate()


@pytest.fixture(scope="module")
def robot_animation(converted, trace) -> SceneAnimation:
    return SceneAnimator(converted, trace, robot_path=ARM).animate()


# %% trace file


def test_trace_poses_match_the_stage_with_scalar_first_quaternions(
    trace, trace_times, stage
):
    for frame, seconds in enumerate(trace_times):
        assert (
            trace.poses[PUCK]
            .at_frame(frame)
            .is_close(world_pose(stage, PUCK, seconds), 1e-9)
        )


def test_resampling_keeps_the_nearest_frames(trace):
    halved = trace.resampled(trace.frames_per_second / 2)
    assert halved.frames_per_second == trace.frames_per_second / 2
    assert halved.frame_count == (trace.frame_count + 1) // 2
    for frame in range(halved.frame_count):
        assert (
            halved.poses[LOWER]
            .at_frame(frame)
            .is_close(trace.poses[LOWER].at_frame(2 * frame), 0.0)
        )


def test_missing_trace_file_is_refused(tmp_path):
    with pytest.raises(TraceNotFound):
        BodyTrace.from_file(tmp_path / "missing.npz")


def test_trace_without_orientations_is_refused(tmp_path):
    recorded = numpy.load(TRACE)
    partial = tmp_path / "partial.npz"
    numpy.savez(
        partial,
        **{
            name: recorded[name]
            for name in recorded.files
            if name != TraceArray.QUATERNIONS
        },
    )
    with pytest.raises(TraceIncomplete) as refusal:
        BodyTrace.from_file(partial)
    assert refusal.value.missing == [TraceArray.QUATERNIONS]


# %% joint recovery


def test_disabled_joints_of_the_variant_still_drive_their_bodies(converted):
    assert all(not joint.enabled for joint in converted.movable_joints)


def test_joint_values_follow_the_authored_motion(
    animation, converted, stage, trace_times
):
    shoulder = animation.joint_values[joint_name(converted, SHOULDER)]
    slide = animation.joint_values[joint_name(converted, SLIDE)]
    assert shoulder == pytest.approx(
        [
            numpy.radians(authored(stage, UPPER, "xformOp:rotateZ", seconds))
            for seconds in trace_times
        ],
        abs=1e-6,
    )
    assert slide == pytest.approx(
        [
            authored(stage, LOWER, "xformOp:translate", seconds)[0]
            - authored(stage, LOWER, "xformOp:translate", 0.0)[0]
            for seconds in trace_times
        ],
        abs=1e-6,
    )


def test_angle_past_half_a_turn_stays_within_the_joint_limits(
    animation, converted, stage, trace_times
):
    joint = next(joint for joint in converted.joints if joint.path == SHOULDER)
    values = animation.joint_values[joint.name]
    assert values.min() >= joint.motion.lower
    assert values.max() <= joint.motion.upper
    last = numpy.radians(authored(stage, UPPER, "xformOp:rotateZ", trace_times[-1]))
    assert values[-1] == pytest.approx(last, abs=1e-6)


def test_motion_off_the_axis_is_reported_as_joint_residual(converted, trace):
    lift, frame = 0.002, 2
    animation = SceneAnimator(converted, displaced(trace, LOWER, frame, lift)).animate()
    residual = next(
        residual for residual in animation.joint_residuals if residual.path == SLIDE
    )
    assert residual.largest_distance == pytest.approx(lift, abs=1e-9)
    assert residual.frame == frame


# %% replay


def test_replay_reproduces_every_traced_body(animation, trace):
    assert sorted(residual.path for residual in animation.body_residuals) == sorted(
        trace.poses
    )
    for residual in animation.body_residuals:
        assert residual.largest_distance < 1e-6
        assert residual.largest_angle < 1e-6


def test_moving_free_body_becomes_an_object_with_its_traced_pose(
    animation, converted, trace
):
    (moving,) = animation.objects
    assert moving.link.path == PUCK
    assert moving.key == PrimPath(PUCK).name
    for frame in range(trace.frame_count):
        assert moving.poses.at_frame(frame).is_close(
            trace.poses[PUCK].at_frame(frame) @ moving.link.prim_to_link, 1e-9
        )
    environment = animation.models[0]
    assert link_name(converted, PUCK) not in [link.name for link in environment.links]


def test_resting_free_body_stays_in_the_environment(animation, converted):
    environment = animation.models[0]
    assert link_name(converted, CRATE) in [link.name for link in environment.links]


def test_tolerance_flags_a_body_the_replay_misses(converted, trace):
    animation = SceneAnimator(
        converted, displaced(trace, LOWER, 2, 0.002), robot_path=ARM
    ).animate()
    tolerance = ResidualTolerance()
    beyond = [
        residual.path
        for residual in animation.body_residuals
        if not residual.within(tolerance)
    ]
    assert beyond == [LOWER]
    assert [residual.path for residual in animation.beyond_tolerance()] == [
        LOWER,
        SLIDE,
    ]


def test_environment_body_the_replay_misses_falls_back_to_an_object(converted, trace):
    animation = SceneAnimator(converted, displaced(trace, LOWER, 2, 0.002)).animate()
    assert sorted(moving.link.path for moving in animation.objects) == [LOWER, PUCK]
    assert all(
        residual.within(ResidualTolerance()) for residual in animation.body_residuals
    )


def test_untraced_bodies_are_listed(converted, trace):
    stray = "/World/Elsewhere"
    extended = replace(trace, poses={**trace.poses, stray: trace.poses[PUCK]})
    animation = SceneAnimator(converted, extended).animate()
    assert animation.untracked_bodies == [stray]


# %% robot


def test_robot_is_a_model_of_its_own_named_after_its_prims(robot_animation):
    environment, robot = robot_animation.models
    expected = PrimPath(ARM).name.lower()
    assert (robot.name, robot.prefix, robot.robot) == (expected, expected, True)
    assert [link.name for link in robot.links] == [
        PrimPath(ARM).name,
        "Base",
        PrimPath(UPPER).name,
        PrimPath(LOWER).name,
    ]
    assert [joint.name for joint in robot.joints] == [
        "RootJoint",
        PrimPath(SHOULDER).name,
        PrimPath(SLIDE).name,
    ]
    robot_paths = {link.path for link in robot.links}
    assert not robot_paths & {link.path for link in environment.links}
    assert environment.name == ENVIRONMENT_MODEL


def test_robot_joint_values_are_keyed_by_the_robot_prefix(
    robot_animation, animation, converted
):
    robot = robot_animation.robot
    for path in (SHOULDER, SLIDE):
        key = f"{robot.prefix}{NameSeparator.MODEL_PREFIX}{PrimPath(path).name}"
        assert robot_animation.joint_values[key] == pytest.approx(
            animation.joint_values[joint_name(converted, path)]
        )


def test_robot_base_follows_its_root_prim(robot_animation, stage, trace_times):
    for frame, seconds in enumerate(trace_times):
        assert robot_animation.base.at_frame(frame).is_close(
            world_pose(stage, ARM, seconds), 1e-9
        )


def test_robot_parts_group_links_below_their_common_prim(robot_animation):
    robot = robot_animation.robot
    assert robot.parts == {robot.name: ["Arm"], "Base": ["Base", "Upper", "Lower"]}


def test_robot_parts_follow_the_common_prim_prefix_only():
    links = [
        Link("Arm", "/World/Robot/Arm/Link", RigidTransform()),
        Link("Hand", "/World/Robot/Hand/Link", RigidTransform()),
    ]
    tree = LinkTree(ConvertedStage(Stage.TWO_JOINT_ARM.path, "Arm", links=links))
    naming = RobotNaming(tree, ["Arm", "Hand"])
    assert naming.parts("robot") == {
        "Arm": ["Link"],
        "Hand": [f"Link{NameSeparator.NUMBER}2"],
    }


def test_robot_replay_reproduces_every_traced_body(robot_animation):
    for residual in robot_animation.body_residuals:
        assert residual.largest_distance < 1e-6
        assert residual.largest_angle < 1e-6


def test_robot_prim_without_one_root_link_is_refused(converted, trace):
    with pytest.raises(RobotRootNotFound):
        SceneAnimator(converted, trace, robot_path="/World/Missing").animate()


def test_robot_prim_holding_its_root_link_finds_it(converted, trace):
    animation = SceneAnimator(converted, trace, robot_path="/World/Arm/Base").animate()
    assert animation.robot.base_link == "Base"


# %% segments


def test_steps_become_segments_on_the_trace_clock():
    run = RecordedRun.from_file(RECORD)
    assert run.segments(PlaybackClock(2.0, 7)) == [
        StepSegment("turn shoulder", 0, 2),
        StepSegment("extend slide", 2, 5),
        StepSegment("slide extended", 5, 5),
        StepSegment("settle", 5, 6),
    ]


# %% bundle


class TestAnimatedBundle:
    """
    The bundle of the arm converted with its trace, robot and recorded steps.
    """

    @pytest.fixture(scope="class")
    @classmethod
    def bundle(cls, tmp_path_factory) -> Path:
        return convert_arm(
            tmp_path_factory.mktemp("scenes"),
            "arm",
            ImportOption.TRACE,
            str(TRACE),
            ImportOption.FRAMES_PER_SECOND,
            "2",
            ImportOption.ROBOT,
            ARM,
            ImportOption.RECORD,
            str(RECORD),
        )

    @staticmethod
    def scene(bundle: Path) -> SceneDescription:
        return SceneDescription.from_json(load(bundle / BundleFile.SCENE))

    def test_scene_declares_environment_and_robot_models(self, bundle):
        models = self.scene(bundle).models
        assert [(model.name, model.robot, model.prefix) for model in models] == [
            (ENVIRONMENT_MODEL, False, ""),
            ("arm", True, "arm"),
        ]
        assert models[1].movable_joints == ["Shoulder", "Slide"]
        assert all(model.preserve_materials for model in models)

    def test_scene_describes_the_robot(self, bundle):
        robot = self.scene(bundle).robot
        assert (robot.name, robot.prefix, robot.base_body) == ("arm", "arm", "Arm")
        assert robot.parts == {"arm": ["Arm"], "Base": ["Base", "Upper", "Lower"]}

    def test_robot_urdf_holds_its_links_with_existing_meshes(self, bundle):
        urdf = bundle / self.scene(bundle).models[1].urdf
        robot = ElementTree.parse(urdf).getroot()
        assert [link.get(UrdfAttribute.NAME) for link in robot.iter(UrdfTag.LINK)] == [
            "Arm",
            "Base",
            "Upper",
            "Lower",
        ]
        files = [mesh.get(UrdfAttribute.FILENAME) for mesh in robot.iter(UrdfTag.MESH)]
        assert files and all((bundle / file).is_file() for file in files)

    def test_moving_free_body_is_an_object_with_its_own_mesh(self, bundle):
        (entry,) = self.scene(bundle).objects
        assert entry.identifier == entry.key == PrimPath(PUCK).name
        assert (bundle / entry.mesh).is_file()
        assert entry.preserve_materials is True
        trajectory = Trajectory.from_json(load(bundle / BundleFile.TRAJECTORY))
        assert entry.spawn == trajectory.objects[0][entry.key]

    def test_trajectory_tracks_have_one_entry_per_frame(self, bundle):
        trajectory = Trajectory.from_json(load(bundle / BundleFile.TRAJECTORY))
        assert trajectory.frames_per_second == 2.0
        assert (
            len(trajectory.frames)
            == len(trajectory.base)
            == len(trajectory.objects)
            == BodyTrace.from_file(TRACE).frame_count
        )
        assert set(trajectory.frames[0]) == {"arm/Shoulder", "arm/Slide"}

    def test_steps_are_the_scene_segments(self, bundle):
        segments = self.scene(bundle).segments
        clock = PlaybackClock(2.0, BodyTrace.from_file(TRACE).frame_count)
        expected = RecordedRun.from_file(RECORD).segments(clock)
        assert [(segment.step, segment.start, segment.end) for segment in segments] == [
            (segment.step, segment.start, segment.end) for segment in expected
        ]

    def test_semantics_name_the_model_and_link_of_robot_and_object_prims(self, bundle):
        prims = Semantics.from_json(load(bundle / BundleFile.SEMANTICS)).prims
        assert (prims[UPPER].model, prims[UPPER].link) == ("arm", "Upper")
        assert (prims[PUCK].model, prims[PUCK].link) == ("Puck", "Puck")

    def test_residuals_list_every_traced_body_and_movable_joint(self, bundle):
        table = ResidualsTable.from_text(
            (bundle / BundleFile.RESIDUALS).read_bytes().decode("utf-8")
        )
        bodies = [row.path for row in table.rows if row.kind is ResidualKind.BODY]
        joints = [row.path for row in table.rows if row.kind is ResidualKind.JOINT]
        assert sorted(bodies) == sorted(BodyTrace.from_file(TRACE).poses)
        assert joints == [SHOULDER, SLIDE]
        assert all(row.within_tolerance for row in table.rows)

    def test_report_summarises_the_animation(self, bundle):
        report = ConversionReport.from_json(load(bundle / BundleFile.CONVERSION_REPORT))
        assert report.animation.frame_count == BodyTrace.from_file(TRACE).frame_count
        assert report.animation.source == str(TRACE)
        assert report.animation.beyond_tolerance == []
        assert report.animation.objects == [PrimPath(PUCK).name]


def test_time_samples_animate_the_stage_without_a_trace(tmp_path, stage, converted):
    bundle = convert_arm(tmp_path, "arm", ImportOption.FRAMES_PER_SECOND, "1")
    trajectory = Trajectory.from_json(load(bundle / BundleFile.TRAJECTORY))
    shoulder = joint_name(converted, SHOULDER)
    seconds = range(len(trajectory.frames))
    assert [frame[shoulder] for frame in trajectory.frames] == pytest.approx(
        [
            numpy.radians(authored(stage, UPPER, "xformOp:rotateZ", second))
            for second in seconds
        ],
        abs=1e-6,
    )
    report = ConversionReport.from_json(load(bundle / BundleFile.CONVERSION_REPORT))
    assert report.animation.source == str(Stage.TWO_JOINT_ARM.path)


def test_frame_rate_defaults_to_thirty(tmp_path, stage):
    bundle = convert_arm(tmp_path, "arm")
    trajectory = Trajectory.from_json(load(bundle / BundleFile.TRAJECTORY))
    seconds = (stage.GetEndTimeCode() - stage.GetStartTimeCode()) / (
        stage.GetTimeCodesPerSecond()
    )
    assert trajectory.frames_per_second == DEFAULT_FRAMES_PER_SECOND
    assert len(trajectory.frames) == round(seconds * DEFAULT_FRAMES_PER_SECOND) + 1
