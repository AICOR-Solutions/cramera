"""
Carrying in the workshop: a held body moved to a pose from its measured attachment, and
the screw box fetched from the right shelf through the free aisle to the workbench.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from typing_extensions import Tuple

from coraplex.datastructures.enums import Arms, ApproachDirection, VerticalAlignment
from coraplex.plans.factories import sequential
from coraplex.plans.plan_node import PlanNode
from coraplex.robot_plans.actions.base import ActionDescription
from coraplex.robot_plans.actions.core.placing import PlaceAction
from coraplex.robot_plans.actions.core.robot_body import ParkArmsAction
from coraplex.robot_plans.motions.gripper import MoveToolCenterPointMotion
from cramera_workshop.robot.grasps import BoxHandleGrasp, ShaftFrame
from cramera_workshop.robot.navigation import WorkshopTranslateAction
from cramera_workshop.robot.pickup import PickUpBoxAction
from cramera_workshop.robot.screw_thread import MoveHeldBodyMotion, tool_frame
from semantic_digital_twin.spatial_types import HomogeneousTransformationMatrix, Pose
from semantic_digital_twin.world_description.world_entity import Body

# %% carrying


@dataclass(frozen=True)
class CarrySpeeds:
    """
    How fast a held body is carried.
    """

    linear: float = 0.06
    """
    The hand's largest speed, in metres per second.
    """

    angular: float = 0.4
    """
    The hand's largest angular speed, in radians per second.
    """


@dataclass
class MoveCarriedBodyMotion(MoveHeldBodyMotion):
    """
    Moves a held body to a world pose, resolved from its measured attachment once the
    grasp before it has run.
    """

    destination: Pose = field(kw_only=True)
    """
    The body's pose to reach.
    """

    speeds: CarrySpeeds = field(default_factory=CarrySpeeds, kw_only=True)
    """
    How fast the hand moves.
    """

    keep_shaft_roll: bool = field(default=False, kw_only=True)
    """
    Whether the body keeps its measured roll about its shaft, so a screw that rolled
    before it was grasped is not turned back by the hand.
    """

    def resolved_motion(self) -> MoveToolCenterPointMotion:
        tool = tool_frame(self, self.arm)
        body_T_tool = self.world.compute_forward_kinematics(self.body, tool)
        destination = self.destination.to_homogeneous_matrix()
        if self.keep_shaft_roll:
            world_T_body = self.body.global_pose.to_np()
            shaft_T_body = (
                np.linalg.inv(ShaftFrame(world_T_body).matrix()) @ world_T_body
            )
            destination = destination @ HomogeneousTransformationMatrix(
                shaft_T_body, reference_frame=self.body
            )
        target = (destination @ body_T_tool).to_pose()
        target.reference_frame = self.world.root
        motion = MoveToolCenterPointMotion(
            target,
            self.arm,
            max_linear_velocity=self.speeds.linear,
            max_angular_velocity=self.speeds.angular,
        )
        motion.plan_node = self.plan_node
        return motion


@dataclass
class MoveHeldObjectAction(ActionDescription):
    """
    Moves a held body to a world pose.
    """

    body: Body
    """
    The held body.
    """

    target: Pose
    """
    Its pose to reach.
    """

    arm: Arms = Arms.LEFT
    """
    The hand holding it.
    """

    keep_shaft_roll: bool = False
    """
    Whether the body keeps its measured roll about its shaft.
    """

    @property
    def _action_plan(self) -> PlanNode:
        return sequential(
            [
                MoveCarriedBodyMotion(
                    arm=self.arm,
                    body=self.body,
                    destination=self.target,
                    keep_shaft_roll=self.keep_shaft_roll,
                )
            ]
        )


# %% screw box


@dataclass(frozen=True)
class RetrievalRoute:
    """
    The way from the shelf to the workbench.
    """

    aisle_y: float = -1.62
    """
    The free aisle's y position, in metres.
    """

    station_setback: float = 0.20
    """
    How far behind the bench station the robot sets the box down, in metres.
    """

    pickup_speeds: Tuple[float, float, float] = (0.10, 0.025, 0.04)
    """
    The hand's speeds before, during and after grasping the box, in metres per second.
    """

    transport_speed: float = 0.07
    """
    The hand's speed while carrying the box, in metres per second.
    """

    placing_speed: float = 0.025
    """
    The hand's speed while setting the box down, in metres per second.
    """

    heading: float = math.pi / 2
    """
    The robot's heading on the whole way, towards the workbench, in radians.
    """


@dataclass
class RetrieveScrewBoxAction(ActionDescription):
    """
    Fetches the loaded screw box from the right shelf, carries it upright through the
    free aisle and sets it down on the workbench; then the robot parks its arm and moves
    sideways to the assembly station.

    Every move keeps the robot's heading, so each is a checked straight corridor.
    """

    box: Body
    """
    The screw box on the shelf.
    """

    screws: Tuple[Body, ...]
    """
    The loose screws in it.
    """

    destination: Pose
    """
    Where the box is set down on the workbench.
    """

    bench_base: Pose
    """
    Where the robot's base ends, in front of the assembly station.
    """

    route: RetrievalRoute = field(default_factory=RetrievalRoute)
    """
    The way and its speeds.
    """

    @property
    def _action_plan(self) -> PlanNode:
        route = self.route
        root = self.world.root
        base_x = self.robot.root.global_pose.x
        carrier_x = self.destination.x + base_x - self.box.global_pose.x
        grasp = BoxHandleGrasp(
            ApproachDirection.FRONT,
            VerticalAlignment.NoAlignment,
            self.robot.left_arm.end_effector,
        )
        before, during, after = route.pickup_speeds
        return sequential(
            [
                PickUpBoxAction(
                    self.box,
                    Arms.LEFT,
                    grasp,
                    pre_approach_linear_velocity=before,
                    final_approach_linear_velocity=during,
                    lift_linear_velocity=after,
                ),
                WorkshopTranslateAction(
                    Pose.from_xyz_rpy(
                        base_x, route.aisle_y, yaw=route.heading, reference_frame=root
                    )
                ),
                WorkshopTranslateAction(
                    Pose.from_xyz_rpy(
                        carrier_x,
                        route.aisle_y,
                        yaw=route.heading,
                        reference_frame=root,
                    )
                ),
                WorkshopTranslateAction(
                    Pose.from_xyz_rpy(
                        carrier_x,
                        self.bench_base.y - route.station_setback,
                        yaw=route.heading,
                        reference_frame=root,
                    )
                ),
                PlaceAction(
                    self.box,
                    self.destination,
                    Arms.LEFT,
                    transport_linear_velocity=route.transport_speed,
                    placing_linear_velocity=route.placing_speed,
                ),
                ParkArmsAction(Arms.LEFT),
                WorkshopTranslateAction(self.bench_base),
            ]
        )
