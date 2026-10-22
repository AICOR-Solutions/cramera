"""
Turning recorded body poses into the playback of a converted stage: joint values, the
robot's base pose, objects and segments, checked by replaying them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

import numpy
from typing_extensions import Dict, List, Optional

from cramera_protocol.bundle.residuals import ResidualKind
from cramera_usd.animation.animation import SceneAnimation
from cramera_usd.animation.deviation import PoseDeviation, ResidualTolerance
from cramera_usd.animation.link_tree import BodyPoses, JointMotion, LinkTree
from cramera_usd.animation.models import (
    NO_MODEL,
    AnimatedObject,
    KinematicModel,
    LinkPlacement,
    RobotModel,
)
from cramera_usd.animation.residuals import Residual
from cramera_usd.animation.robot_naming import RobotNaming
from cramera_usd.animation.run_record import PlaybackClock, RecordedRun
from cramera_usd.animation.trace import BodyTrace
from cramera_usd.exceptions import RobotRootNotFound
from cramera_usd.geometry.transforms import RigidTransform, TransformTrack
from cramera_usd.names import PrimPath, UniqueNames
from cramera_usd.scene.kinematics import Joint, Link
from cramera_usd.scene.stage import ConvertedStage

# %% constants

ENVIRONMENT_MODEL = "environment"
"""
The name of the model holding every link that is neither the robot nor a free object.
"""

JOINT_VALUE_DECIMALS = 6
"""
The decimals kept of recovered joint values.
"""

# %% replay


@dataclass
class Replay:
    """
    The world pose of every link when the recovered joint values are played back.
    """

    link_poses: Dict[str, TransformTrack] = field(default_factory=dict)
    """
    The world pose of each link frame per frame, by converted link name.
    """

    detached: List[str] = field(default_factory=list)
    """
    The links whose recorded motion the kinematic tree does not reproduce, played back
    by their world poses instead, parents before children.
    """


# %% robot


@dataclass
class RobotRoot:
    """
    Finds the robot's root link among the converted links.
    """

    tree: LinkTree
    """
    The links of the converted stage.
    """

    path: str
    """
    The prim of the robot's root link, or a prim holding exactly one topmost link.
    """

    def link(self) -> Link:
        """
        :return: The link standing for the prim, else the one topmost link below it.
        :raises RobotRootNotFound: When the prim holds no link or several topmost
            links.
        """
        exact = self.tree.links_by_path.get(self.path)
        if exact is not None and exact.name in self.tree.parent_joints:
            return exact
        below = [
            link
            for link in self.tree.stage.links
            if PrimPath(self.path).strictly_holds(link.path)
        ]
        names = {link.name for link in below}
        topmost = [
            link
            for link in below
            if self.tree.parent_joints[link.name].parent not in names
        ]
        if len(topmost) != 1:
            raise RobotRootNotFound(self.path, [link.name for link in topmost])
        return topmost[0]


# %% animator


@dataclass
class SceneAnimator:
    """
    Turns recorded body poses into the playback of a converted stage, checked by
    replaying them.
    """

    stage: ConvertedStage
    """
    The converted stage.
    """

    trace: BodyTrace
    """
    The recorded body poses, at the playback rate.
    """

    robot_path: Optional[str] = None
    """
    The prim of the robot's root link (or a prim holding exactly one topmost link), or
    None for a scene without a robot.
    """

    run: Optional[RecordedRun] = None
    """
    The recorded steps to label the playback with, or None.
    """

    tolerance: ResidualTolerance = field(default_factory=ResidualTolerance)
    """
    How far the replay may stray from the recording.
    """

    environment_name: str = ENVIRONMENT_MODEL
    """
    The environment model's name.
    """

    decimals: int = JOINT_VALUE_DECIMALS
    """
    The decimals kept of joint values.
    """

    @cached_property
    def tree(self) -> LinkTree:
        """
        The links of the converted stage as a tree.
        """
        return LinkTree(self.stage)

    @cached_property
    def body_poses(self) -> BodyPoses:
        """
        The world pose track of every link's prim.
        """
        return BodyPoses.of_stage(self.trace, self.stage)

    @cached_property
    def motions(self) -> Dict[str, JointMotion]:
        """
        The recovered motion of every movable joint, by converted joint name.
        """
        return {
            joint.name: JointMotion.recover(
                joint,
                self.body_poses.of(joint.parent_body),
                self.body_poses.of(joint.child_body),
                self.decimals,
            )
            for joint in self.stage.movable_joints
        }

    @cached_property
    def robot_root(self) -> Optional[Link]:
        """
        The robot's root link, or None without a robot.
        """
        if self.robot_path is None:
            return None
        return RobotRoot(self.tree, self.robot_path).link()

    @cached_property
    def robot_links(self) -> List[str]:
        """
        The names of the robot's links, the root first.
        """
        if self.robot_root is None:
            return []
        return self.tree.subtree(self.robot_root.name)

    @cached_property
    def robot_naming(self) -> Optional[RobotNaming]:
        """
        The robot's own names of its links and joints, or None without a robot.
        """
        if self.robot_root is None:
            return None
        return RobotNaming(self.tree, self.robot_links)

    def animate(self) -> SceneAnimation:
        """
        :return: The recovered, replayed and checked playback.
        """
        replay = self.replay()
        robot = None if self.robot_naming is None else self.robot_naming.model()
        objects = self.objects(replay)
        placements = self.placements(robot, objects, replay)
        environment = self.environment(replay)
        frame_count = self.trace.frame_count
        clock = PlaybackClock(self.trace.frames_per_second, frame_count)
        return SceneAnimation(
            frames_per_second=self.trace.frames_per_second,
            frame_count=frame_count,
            models=[environment] if robot is None else [environment, robot],
            joint_values=self.joint_values(environment, robot),
            base=None if robot is None else replay.link_poses[self.robot_root.name],
            objects=objects,
            segments=[] if self.run is None else self.run.segments(clock),
            body_residuals=self.body_residuals(replay, placements),
            joint_residuals=self.joint_residuals(placements),
            placements=placements,
            untracked_bodies=[
                path for path in self.trace.poses if path not in self.tree.links_by_path
            ],
            tolerance=self.tolerance,
            source=self.trace.source,
        )

    def replay(self) -> Replay:
        """
        :return: The recovered joint values played back from the root, the robot's
            root link from its base pose; an environment link whose recorded pose the
            tree misses, and everything below it, is detached and follows its
            recording.
        """
        replay = Replay()
        for link in self.stage.links:
            joint = self.tree.parent_joints.get(link.name)
            if joint is None:
                replay.link_poses[link.name] = TransformTrack.constant(
                    RigidTransform(), self.trace.frame_count
                )
                continue
            if self.robot_root is not None and link.name == self.robot_root.name:
                replay.link_poses[link.name] = self.base_poses(link, joint, replay)
                continue
            replay.link_poses[link.name] = self.child_poses(joint, replay)
            if link.name in self.robot_links:
                continue
            recorded = self.recorded_link_poses(link)
            missed = recorded is not None and not PoseDeviation.between(
                replay.link_poses[link.name], recorded
            ).within(self.tolerance)
            if joint.parent in replay.detached or missed:
                replay.detached.append(link.name)
            if missed:
                replay.link_poses[link.name] = recorded
        return replay

    def child_poses(self, joint: Joint, replay: Replay) -> TransformTrack:
        """
        :param joint: A joint.
        :param replay: The replay so far, holding the joint's parent link.
        :return: The world poses of the joint's child link.
        """
        values = (
            self.motions[joint.name].values
            if joint.movable
            else numpy.zeros(self.trace.frame_count)
        )
        return (
            replay.link_poses[joint.parent] @ joint.origin
        ) @ joint.motion.transforms(values)

    def base_poses(self, root: Link, joint: Joint, replay: Replay) -> TransformTrack:
        """
        :param root: The robot's root link.
        :param joint: The joint holding the root link.
        :param replay: The replay so far, holding the root's parent link.
        :return: The world poses of the robot's root link: from the first recorded link
            rigidly attached to it (the root itself included), else from its parent
            link.
        """
        offsets = {root.name: RigidTransform()}
        for name in self.tree.subtree(root.name):
            if name not in offsets:
                continue
            recorded = self.recorded_link_poses(self.tree.links[name])
            if recorded is not None:
                return recorded @ offsets[name].inverse()
            for child in self.tree.children[name]:
                child_joint = self.tree.parent_joints[child]
                if not child_joint.movable:
                    offsets[child] = offsets[name] @ child_joint.origin
        return self.child_poses(joint, replay)

    def recorded_link_poses(self, link: Link) -> Optional[TransformTrack]:
        """
        :param link: A link.
        :return: The recorded world poses of the link frame, or None when its prim was
            not recorded.
        """
        if link.path not in self.trace.poses:
            return None
        return self.trace.poses[link.path] @ link.prim_to_link

    def objects(self, replay: Replay) -> List[AnimatedObject]:
        """
        :param replay: The replay.
        :return: The detached links with geometry, keyed by their prim names (numbered
            where they repeat).
        """
        detached = [
            self.tree.links[name]
            for name in replay.detached
            if self.tree.links[name].meshes
        ]
        keys = UniqueNames().claim_each(
            {link.name: PrimPath(link.path).name for link in detached}
        )
        return [
            AnimatedObject(keys[link.name], link, replay.link_poses[link.name])
            for link in detached
        ]

    def environment(self, replay: Replay) -> KinematicModel:
        """
        :param replay: The replay.
        :return: The links and joints that are neither the robot's nor detached.
        """
        left_out = set(self.robot_links) | set(replay.detached)
        links = [link for link in self.stage.links if link.name not in left_out]
        kept = {link.name for link in links}
        joints = [joint for joint in self.stage.joints if joint.child in kept]
        return KinematicModel(self.environment_name, links, joints)

    def placements(
        self,
        robot: Optional[RobotModel],
        objects: List[AnimatedObject],
        replay: Replay,
    ) -> Dict[str, LinkPlacement]:
        """
        :param robot: The robot model, or None.
        :param objects: The objects.
        :param replay: The replay.
        :return: Where each converted link ended up, by converted link name.
        """
        placements = {
            link.name: LinkPlacement(self.environment_name, link.name)
            for link in self.stage.links
            if link.name not in replay.detached
        }
        if robot is not None:
            for original, renamed in zip(self.robot_links, robot.links):
                placements[original] = LinkPlacement(robot.name, renamed.name)
        for moving in objects:
            placements[moving.link.name] = LinkPlacement(moving.key, moving.key)
        return placements

    def joint_values(
        self, environment: KinematicModel, robot: Optional[RobotModel]
    ) -> Dict[str, numpy.ndarray]:
        """
        :param environment: The environment model.
        :param robot: The robot model, or None.
        :return: The value per frame of every movable joint of the models, by
            trajectory key.
        """
        values = {
            environment.key_of(joint): self.motions[joint.name].values
            for joint in environment.movable_joints
        }
        if robot is None:
            return values
        for original, renamed in zip(self.robot_naming.joints, robot.joints):
            if renamed.movable:
                values[robot.key_of(renamed)] = self.motions[original.name].values
        return values

    def body_residuals(
        self, replay: Replay, placements: Dict[str, LinkPlacement]
    ) -> List[Residual]:
        """
        :param replay: The replay.
        :param placements: Where each link ended up.
        :return: How far each recorded body that a link stands for is replayed from its
            recording.
        """
        residuals = []
        for path, recorded in self.trace.poses.items():
            link = self.tree.links_by_path.get(path)
            if link is None:
                continue
            replayed = replay.link_poses[link.name] @ link.prim_to_link.inverse()
            residuals.append(
                Residual(
                    ResidualKind.BODY,
                    path,
                    placements.get(link.name, LinkPlacement(NO_MODEL, link.name)),
                    PoseDeviation.between(recorded, replayed),
                    self.tolerance,
                )
            )
        return residuals

    def joint_residuals(self, placements: Dict[str, LinkPlacement]) -> List[Residual]:
        """
        :param placements: Where each link ended up.
        :return: How much recorded motion each movable joint cannot make.
        """
        names = {} if self.robot_naming is None else self.robot_naming.joint_names
        residuals = []
        for joint in self.stage.movable_joints:
            child = placements.get(joint.child, LinkPlacement(NO_MODEL, joint.child))
            residuals.append(
                Residual(
                    ResidualKind.JOINT,
                    joint.path,
                    LinkPlacement(child.model, names.get(joint.name, joint.name)),
                    self.motions[joint.name].off_axis,
                    self.tolerance,
                )
            )
        return residuals
