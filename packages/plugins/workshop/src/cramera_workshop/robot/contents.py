"""
The screw box's loose contents while the PR2 carries it: a separate MuJoCo contact world
lets the screws slide and collide in a box that follows the native box's trajectory, and
their measured poses relative to that box are put into the native box's frame.

The coupling is one way: the contact forces do not act back on the robot or the native
box.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
from typing_extensions import TYPE_CHECKING, Dict, List, Optional, Tuple

from coraplex.plans.plan_callbacks import PlanCallback
from coraplex.plans.plan_node import ActionNode, PlanNode
from cramera_protocol.geometry import Pose
from cramera_workshop.acceptance import ContentsModel
from cramera_workshop.physics import WorkshopPhysics
from semantic_digital_twin.spatial_types import HomogeneousTransformationMatrix
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.connections import Connection6DoF
from semantic_digital_twin.world_description.world_entity import (
    Body,
    KinematicStructureEntity,
)

if TYPE_CHECKING:
    from coraplex.robot_plans.actions.base import ActionDescription
    from giskardpy.motion_statechart.motion_statechart import MotionStatechart

BOX_WALLS = 5
"""
The box's collision boxes: a floor and four walls.
"""

UNROTATED = (1.0, 0.0, 0.0, 0.0)
"""
MuJoCo's identity quaternion, scalar first.
"""

# %% failures


class CouplingProblem(StrEnum):
    """
    Why the contents cannot be coupled to the native box.
    """

    MISSING_BODIES = "A matching box and loose screws are required."
    """
    The contact world has no such box, or no screws were given.
    """

    REPEATED_SCREWS = "The contents must be distinct screws."
    """
    A screw was given twice.
    """

    UNDECLARED_SCREW = "Only the workshop's screws may be coupled."
    """
    A body is no screw of the workshop.
    """

    ATTACHED_SCREW = "The contents must stay free bodies in the box's frame."
    """
    A screw lost its free connection to the box or the world.
    """

    UNPREPARED = "Prepare the contents before the native plan is built."
    """
    The retrieval started without the contents being coupled.
    """

    INVALID_INTERVAL = "A contact interval must be positive, finite and at most 30 s."
    """
    The interval to simulate is not.
    """

    OPEN_BOX = "The box needs an unrotated floor and four unrotated wall boxes."
    """
    The box's collision shapes are not a floor and four walls.
    """

    UNSUPPORTED_SHAPE = (
        "The screws' collision shapes must be boxes, cylinders or spheres."
    )
    """
    A screw has a shape whose bounds are not computed.
    """

    ESCAPED = "Screws escaped the box"
    """
    A screw ended outside the box's cavity.
    """


@dataclass
class InvalidContentsCoupling(ValueError):
    """
    The native bodies cannot receive the measured contents' poses.
    """

    problem: CouplingProblem
    """
    Why.
    """

    escaped: Tuple[str, ...] = ()
    """
    The screws that ended outside the box, for :attr:`CouplingProblem.ESCAPED`.
    """

    def __str__(self) -> str:
        if not self.escaped:
            return self.problem.value
        return f"{self.problem.value}: {', '.join(self.escaped)}"


# %% measurements


@dataclass
class ContentsMeasurements:
    """
    What the contact world measured while the box was carried.
    """

    model: ContentsModel = ContentsModel.RELATIVE_CONTACT
    """
    The coupling.
    """

    ticks: int = 0
    """
    How many native control periods the contact world followed.
    """

    simulated_seconds: float = 0.0
    """
    The contact world's simulated time, settling included.
    """

    maximum_box_position_lag: float = 0.0
    """
    The largest distance between the native and the simulated box, in metres.
    """

    maximum_box_angular_lag: float = 0.0
    """
    The largest angle between the native and the simulated box, in radians.
    """

    maximum_relative_displacement: float = 0.0
    """
    The largest distance a screw slid in the box, in metres.
    """

    maximum_projection_correction: float = 0.0
    """
    The largest distance between a screw's projected and simulated positions, in metres.
    """

    retained_contents: bool = False
    """
    Whether every screw ended inside the box's cavity.
    """

    escaped_contents: Tuple[str, ...] = ()
    """
    The screws that ended outside it.
    """

    contents_count: int = 0
    """
    How many screws were simulated.
    """


@dataclass(frozen=True)
class CollisionBounds:
    """
    An axis-aligned box in a common frame.
    """

    lower: np.ndarray
    """
    The smallest coordinates.
    """

    upper: np.ndarray
    """
    The largest coordinates.
    """

    def contains(self, other: CollisionBounds, tolerance: float) -> bool:
        """
        :param other: Other bounds.
        :param tolerance: How far the other bounds may reach out, in metres.
        :return: Whether the other bounds lie inside these.
        """
        return bool(
            np.all(other.lower >= self.lower - tolerance)
            and np.all(other.upper <= self.upper + tolerance)
        )


def matrix_of(pose: np.ndarray) -> np.ndarray:
    """
    :param pose: A position and a quaternion with the scalar last.
    :return: The homogeneous transformation.
    """
    result = np.eye(4)
    result[:3, :3] = Rotation.from_quat(pose[3:]).as_matrix()
    result[:3, 3] = pose[:3]
    return result


# %% coupling


@dataclass
class WorkshopContents(PlanCallback):
    """
    Couples the box's loose screws to a separate contact world while one retrieval
    action runs: started explicitly before the plan is built, advanced on every native
    control tick, settled and checked when the action ends.
    """

    world: World = field(kw_only=True)
    """
    The native world; only the screws' free poses change in it.
    """

    physics: WorkshopPhysics = field(kw_only=True)
    """
    The separate contact world with the same box and screws.
    """

    box: Body = field(kw_only=True)
    """
    The native box, moved by the robot only.
    """

    contents: Tuple[Body, ...] = field(kw_only=True)
    """
    The native screws in it.
    """

    control_period: float = field(kw_only=True)
    """
    The simulated time of one native control tick, in seconds.
    """

    action: Optional[ActionDescription] = field(default=None, kw_only=True)
    """
    The retrieval action whose start and end bound the coupling.
    """

    initial_settle_seconds: float = field(default=0.25, kw_only=True)
    """
    How long the screws settle before the box is followed, in seconds.
    """

    final_settle_seconds: float = field(default=0.35, kw_only=True)
    """
    How long the screws settle where the box is set down, in seconds.
    """

    retention_tolerance: float = field(default=0.0005, kw_only=True)
    """
    How far a resting screw may reach into the box's walls, in metres.
    """

    longest_interval: float = field(default=30.0, kw_only=True)
    """
    The longest interval simulated at once, in seconds.
    """

    active: bool = field(default=False, init=False)
    """
    Whether native ticks advance the contact world.
    """

    measurements: ContentsMeasurements = field(
        default_factory=ContentsMeasurements, init=False
    )
    """
    What the contact world measured.
    """

    initial_relative_positions: Dict[str, np.ndarray] = field(
        default_factory=dict, init=False
    )
    """
    Each screw's position in the box after the initial settling.
    """

    @property
    def box_key(self) -> str:
        """
        :return: The box's name, the same in both worlds.
        """
        return str(self.box.name)

    def validate_contents(self) -> None:
        """
        :raises InvalidContentsCoupling: When the box or the screws do not match the
            contact world, or a screw lost its free connection.
        """
        if self.box_key not in self.physics.objects or not self.contents:
            raise InvalidContentsCoupling(CouplingProblem.MISSING_BODIES)
        names = [str(body.name) for body in self.contents]
        if len(set(names)) != len(names):
            raise InvalidContentsCoupling(CouplingProblem.REPEATED_SCREWS)
        parent = self.box if self.active else self.world.root
        for body, name in zip(self.contents, names):
            if name not in self.physics.thread.geometry.screws:
                raise InvalidContentsCoupling(CouplingProblem.UNDECLARED_SCREW)
            connection = body.parent_connection
            if (
                not isinstance(connection, Connection6DoF)
                or connection.parent is not parent
            ):
                raise InvalidContentsCoupling(CouplingProblem.ATTACHED_SCREW)

    def reparent_contents(self, parent: KinematicStructureEntity) -> None:
        """
        Move the screws below another parent, with their free connections and world
        poses kept, in one model change.

        :param parent: The new parent.
        """
        with self.world.batch_state_changes():
            with self.world.modify_world():
                for body in self.contents:
                    self.world.move_branch(
                        body, parent, enable_unsafe_inside_world_block=True
                    )

    def start(self) -> None:
        """
        Settle the screws, hold the simulated box and put the native screws below the
        native box; call before the native plan is built, since moving branches changes
        the degrees of freedom its goals bind.
        """
        if self.active:
            return
        self.validate_contents()
        self.measurements.contents_count = len(self.contents)
        self.simulate(self.initial_settle_seconds)
        self.physics.grab(self.box_key)
        self.reparent_contents(self.box)
        self.active = True
        box_T_world = np.linalg.inv(matrix_of(self.physics.pose(self.box_key)))
        self.initial_relative_positions = {
            str(body.name): (
                box_T_world @ matrix_of(self.physics.pose(str(body.name)))
            )[:3, 3].copy()
            for body in self.contents
        }
        self.publish_contents()

    def simulate(self, duration: float) -> None:
        """
        :param duration: The contact world's time to let pass, in seconds.
        """
        before = float(self.physics.world.data.time)
        self.physics.step(duration)
        self.measurements.simulated_seconds += (
            float(self.physics.world.data.time) - before
        )

    def advance(self, duration: float) -> None:
        """
        Follow the native box for one interval and put the screws' poses in it.

        :param duration: The interval, in seconds.
        :raises InvalidContentsCoupling: For an interval that is not positive, finite
            and short enough.
        """
        if not self.active:
            return
        if not math.isfinite(duration) or not 0 < duration <= self.longest_interval:
            raise InvalidContentsCoupling(CouplingProblem.INVALID_INTERVAL)
        self.validate_contents()
        self.physics.move(
            self.box_key, Pose(*self.box.global_pose.to_position_quaternion_list())
        )
        self.simulate(duration)
        self.measurements.ticks += 1
        self.publish_contents()

    def publish_contents(self) -> None:
        """
        Put the screws' measured poses relative to the simulated box into the native
        box's frame, without moving the native box.
        """
        self.validate_contents()
        native_world_T_box = self.box.global_pose.to_np()
        measured_world_T_box = matrix_of(self.physics.pose(self.box_key))
        box_T_measured_world = np.linalg.inv(measured_world_T_box)
        measurements = self.measurements
        measurements.maximum_box_position_lag = max(
            measurements.maximum_box_position_lag,
            float(
                np.linalg.norm(native_world_T_box[:3, 3] - measured_world_T_box[:3, 3])
            ),
        )
        measurements.maximum_box_angular_lag = max(
            measurements.maximum_box_angular_lag,
            float(
                Rotation.from_matrix(
                    native_world_T_box[:3, :3].T @ measured_world_T_box[:3, :3]
                ).magnitude()
            ),
        )
        projected: List[Tuple[Body, np.ndarray]] = []
        for body in self.contents:
            name = str(body.name)
            measured_world_T_screw = matrix_of(self.physics.pose(name))
            box_T_screw = box_T_measured_world @ measured_world_T_screw
            native_world_T_screw = native_world_T_box @ box_T_screw
            measurements.maximum_relative_displacement = max(
                measurements.maximum_relative_displacement,
                float(
                    np.linalg.norm(
                        box_T_screw[:3, 3] - self.initial_relative_positions[name]
                    )
                ),
            )
            measurements.maximum_projection_correction = max(
                measurements.maximum_projection_correction,
                float(
                    np.linalg.norm(
                        native_world_T_screw[:3, 3] - measured_world_T_screw[:3, 3]
                    )
                ),
            )
            in_box = body.parent_connection.parent is self.box
            projected.append((body, box_T_screw if in_box else native_world_T_screw))
        with self.world.batch_state_changes():
            for body, parent_T_screw in projected:
                body.parent_connection.origin = HomogeneousTransformationMatrix(
                    data=parent_T_screw,
                    reference_frame=body.parent_connection.parent,
                    child_frame=body,
                )

    # %% retention

    def geometry_indices(self, key: str) -> range:
        """
        :param key: A body name of the contact world.
        :return: The indices of the geoms attached directly to it.
        """
        body = self.physics.world.model.body(key)
        start = int(body.geomadr[0])
        return range(start, start + int(body.geomnum[0]))

    def cavity_bounds(self) -> CollisionBounds:
        """
        :return: The box's open cavity, from its floor and four walls, in its frame.
        :raises InvalidContentsCoupling: When the box's shapes are not a floor and four
            unrotated walls.
        """
        model = self.physics.world.model
        indices = list(self.geometry_indices(self.box_key))
        if len(indices) != BOX_WALLS or any(
            model.geom_type[index] != mujoco.mjtGeom.mjGEOM_BOX
            or not np.allclose(model.geom_quat[index], UNROTATED)
            for index in indices
        ):
            raise InvalidContentsCoupling(CouplingProblem.OPEN_BOX)
        floor = min(indices, key=lambda index: model.geom_size[index, 2])
        lower = model.geom_pos[floor] - model.geom_size[floor]
        upper = model.geom_pos[floor] + model.geom_size[floor]
        lower[2] = upper[2]
        walls = [index for index in indices if index != floor]
        upper[2] = min(
            model.geom_pos[index, 2] + model.geom_size[index, 2] for index in walls
        )
        for index in walls:
            axis = int(np.argmin(model.geom_size[index, :2]))
            centre = model.geom_pos[index, axis]
            extent = model.geom_size[index, axis]
            if centre < model.geom_pos[floor, axis]:
                lower[axis] = max(lower[axis], centre + extent)
            else:
                upper[axis] = min(upper[axis], centre - extent)
        return CollisionBounds(lower=lower, upper=upper)

    def collision_bounds(self, key: str) -> CollisionBounds:
        """
        :param key: A screw's name.
        :return: The bounds of its measured collision shapes in the simulated box's
            frame.
        :raises InvalidContentsCoupling: For a shape other than a box, cylinder or
            sphere.
        """
        model, data = self.physics.world.model, self.physics.world.data
        world_T_box = matrix_of(self.physics.pose(self.box_key))
        box_R_world = world_T_box[:3, :3].T
        lower, upper = [], []
        for index in self.geometry_indices(key):
            centre = box_R_world @ (data.geom_xpos[index] - world_T_box[:3, 3])
            rotation = box_R_world @ data.geom_xmat[index].reshape(3, 3)
            size = model.geom_size[index]
            shape = model.geom_type[index]
            if shape == mujoco.mjtGeom.mjGEOM_BOX:
                extent = np.abs(rotation) @ size
            elif shape == mujoco.mjtGeom.mjGEOM_CYLINDER:
                extent = size[0] * np.linalg.norm(rotation[:, :2], axis=1) + size[
                    1
                ] * np.abs(rotation[:, 2])
            elif shape == mujoco.mjtGeom.mjGEOM_SPHERE:
                extent = np.full(3, size[0])
            else:
                raise InvalidContentsCoupling(CouplingProblem.UNSUPPORTED_SHAPE)
            lower.append(centre - extent)
            upper.append(centre + extent)
        return CollisionBounds(lower=np.min(lower, axis=0), upper=np.max(upper, axis=0))

    def measure_retention(self) -> None:
        """
        Record which screws ended outside the box's cavity.
        """
        cavity = self.cavity_bounds()
        self.measurements.escaped_contents = tuple(
            str(body.name)
            for body in self.contents
            if not cavity.contains(
                self.collision_bounds(str(body.name)), self.retention_tolerance
            )
        )
        self.measurements.retained_contents = not self.measurements.escaped_contents

    def stop(self) -> None:
        """
        Settle the screws where the box is set down, check they stayed in, and put them
        back below the world's root for the actions after.

        :raises InvalidContentsCoupling: When a screw escaped the box.
        """
        if not self.active:
            return
        if self.final_settle_seconds:
            self.advance(self.final_settle_seconds)
        self.measure_retention()
        self.reparent_contents(self.world.root)
        self.physics.release()
        self.active = False
        if not self.measurements.retained_contents:
            raise InvalidContentsCoupling(
                CouplingProblem.ESCAPED, self.measurements.escaped_contents
            )

    # %% plan callbacks

    def on_start(self, node: PlanNode) -> None:
        """
        :raises InvalidContentsCoupling: When the retrieval starts uncoupled.
        """
        if (
            isinstance(node, ActionNode)
            and node.designator is self.action
            and not self.active
        ):
            raise InvalidContentsCoupling(CouplingProblem.UNPREPARED)

    def on_end(self, node: PlanNode) -> None:
        if isinstance(node, ActionNode) and node.designator is self.action:
            self.stop()

    def on_motion_tick(self, statechart: MotionStatechart) -> None:
        if self.active:
            self.advance(self.control_period)
