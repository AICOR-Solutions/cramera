"""
A plan's steps as the native coraplex actions they stand for.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import Callable, Dict

from coraplex.datastructures.dataclasses import Context
from coraplex.datastructures.enums import Arms
from coraplex.datastructures.grasp import GraspDescription
from coraplex.robot_plans.actions.base import ActionDescription
from coraplex.robot_plans.actions.composite.transporting import TransportAction
from coraplex.robot_plans.actions.core.navigation import NavigateAction
from coraplex.robot_plans.actions.core.pick_up import PickUpAction
from coraplex.robot_plans.actions.core.placing import PlaceAction
from coraplex.robot_plans.actions.core.robot_body import (
    MoveTorsoAction,
    ParkArmsAction,
)
from coraplex.view_manager import ViewManager
from cramera_plan_builder.cram.surfaces import SurfaceTargets
from cramera_protocol.geometry import Pose as PlannedPose
from cramera_protocol.plan_builder import PlacementMode, PlanStep, StepKind
from semantic_digital_twin.datastructures.definitions import TorsoState
from semantic_digital_twin.spatial_types import Pose
from semantic_digital_twin.world_description.world_entity import Body

# %% actions


@dataclass(frozen=True)
class StepActions:
    """
    Builds the native action of each step against the world and robot of a context.
    """

    context: Context
    """
    The world and the robot that performs the steps.
    """

    bodies: Dict[str, Body]
    """
    The plan's objects by their identity.
    """

    def action(self, step: PlanStep) -> ActionDescription:
        """
        :param step: A complete step the robot's model allows.
        :return: The native action the step stands for.
        """
        builders: Dict[StepKind, Callable[[PlanStep], ActionDescription]] = {
            StepKind.PARK_ARMS: self.park_arms,
            StepKind.MOVE_TORSO: self.move_torso,
            StepKind.NAVIGATE: self.navigate,
            StepKind.TRANSPORT: self.transport,
            StepKind.PICK_UP: self.pick_up,
            StepKind.PLACE: self.place,
        }
        return builders[step.kind](step)

    @staticmethod
    def park_arms(step: PlanStep) -> ParkArmsAction:
        """
        :param step: A park step.
        :return: Parking its arms.
        """
        return ParkArmsAction(Arms[step.arm])

    @staticmethod
    def move_torso(step: PlanStep) -> MoveTorsoAction:
        """
        :param step: A torso step.
        :return: Moving the torso to its state.
        """
        return MoveTorsoAction(TorsoState[step.torso_state])

    def navigate(self, step: PlanStep) -> NavigateAction:
        """
        :param step: A navigation step.
        :return: Driving the base to its target.
        """
        return NavigateAction(self.pose(step.target))

    def transport(self, step: PlanStep) -> TransportAction:
        """
        :param step: A transport step.
        :return: The transport of its object to its pose or surface, with the switches
            its constraints turn on.
        """
        return TransportAction(
            object_designator=self.bodies[step.object_identifier],
            target_location=self.destinations(step),
            arm=Arms[step.arm],
            **self.switches(step),
        )

    def place(self, step: PlanStep) -> PlaceAction:
        """
        :param step: A place step.
        :return: Placing the held object at its pose or on its surface.
        """
        return PlaceAction(
            object_designator=self.bodies[step.object_identifier],
            target_location=self.destination(step),
            arm=Arms[step.arm],
        )

    def pick_up(self, step: PlanStep) -> PickUpAction:
        """
        :param step: A pick-up step.
        :return: The pick-up with the default grasp for the object as it lies, the
            approach side following the robot's reach.
        """
        body = self.bodies[step.object_identifier]
        arm = Arms[step.arm]
        return PickUpAction(
            body,
            arm,
            GraspDescription.robot_relative_default(
                ViewManager.get_end_effector_view(arm, self.context.robot),
                body.global_pose,
                body,
            ),
        )

    def destinations(self, step: PlanStep) -> Pose | SurfaceTargets:
        """
        :param step: A transport step.
        :return: Its pose, or the spots of its surface, sampled when the step runs.
        """
        if step.placement is PlacementMode.POSE:
            return self.pose(step.target)
        return self.surface_targets(step)

    def destination(self, step: PlanStep) -> Pose:
        """
        :param step: A place step.
        :return: Its pose, or the best rated spot of its surface now.
        """
        if step.placement is PlacementMode.POSE:
            return self.pose(step.target)
        return self.surface_targets(step).first()

    def surface_targets(self, step: PlanStep) -> SurfaceTargets:
        """
        :param step: A step putting its object on a surface.
        :return: The spots of the surface for the step's object.
        """
        return SurfaceTargets(
            world=self.context.world,
            body=self.bodies[step.object_identifier],
            surface_type=step.surface_type,
            surface_name=step.surface_name,
        )

    @staticmethod
    def switches(step: PlanStep) -> Dict[str, bool]:
        """
        :param step: A step.
        :return: The keyword arguments its constraints turn on.
        """
        return {
            constraint.switch.value: True
            for constraint in step.constraints
            if constraint.switch is not None
        }

    def pose(self, planned: PlannedPose) -> Pose:
        """
        :param planned: A pose of the plan, in world coordinates.
        :return: The native pose in the world's root frame.
        """
        return Pose.from_xyz_quaternion(
            *planned.to_json(), reference_frame=self.context.world.root
        )
