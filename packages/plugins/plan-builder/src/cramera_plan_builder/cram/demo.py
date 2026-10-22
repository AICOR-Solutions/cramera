"""
A plan run as a robot task demo: the plan's robots and objects in its environment, the
performing robot's steps as native actions, and the placements measured afterwards.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from typing_extensions import Dict, Iterator, List

from coraplex.datastructures.dataclasses import Context
from coraplex.plans.factories import sequential
from coraplex.plans.plan import Plan
from cramera_cram.exceptions import TaskFailed
from cramera_cram.geometry import NumericPose
from cramera_cram.robot_task import NAME_PART_SEPARATOR, RobotTaskDemo
from cramera_cram.scenes.multi_robot import RobotPlacement, RobotScene
from cramera_plan_builder.cram.steps import StepActions
from cramera_plan_builder.cram.workspace import RobotAnnotations
from cramera_plan_builder.cram.world import EmptyFloor, PlannedObjects
from cramera_cram.scenes.bundle_world import PoseText
from cramera_protocol.bundle.acceptance import AcceptanceMetrics
from cramera_protocol.bundle.index import SceneName
from cramera_protocol.plan_builder import (
    DemoDocument,
    PlacementMode,
    PlanDocument,
    PlannedRobot,
    PlanStep,
    StepKind,
)
from semantic_digital_twin.spatial_types import HomogeneousTransformationMatrix
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.world_entity import Body

PLACEMENT_TOLERANCE = 0.1
"""
How far, in metres, an object put down at a pose may end up from it.
"""

MAXIMUM_NAME_LENGTH = 64
"""
How long a recording's name may be, as :class:`SceneName` allows.
"""

FIRST_REPEAT = 2
"""
The number the first repeated recording of a name carries.
"""

PLACEMENT_ERROR = "placementError"
"""
The measurement of how far an object ended from where a step put it, followed by the
step's identity.
"""

MEASUREMENT_SEPARATOR = "."
"""
Joins a measurement's name and the step it measures.
"""

# %% robots


@dataclass(frozen=True)
class PlannedRobots:
    """
    The robots of a plan as the native scene of several robots, each under its own
    namespace.
    """

    plan: PlanDocument
    """
    The plan.
    """

    annotations: RobotAnnotations = field(default_factory=RobotAnnotations)
    """
    The workspace's robot annotations, which the plan names by class name.
    """

    def performing(self) -> PlannedRobot:
        """
        :return: The robot whose steps run: the selected one, else the first.
        """
        for robot in self.plan.robots:
            if robot.identifier == self.plan.selected_robot:
                return robot
        return self.plan.robots[0]

    def placement(self, robot: PlannedRobot) -> RobotPlacement:
        """
        :param robot: A robot of the plan.
        :return: Its native placement under the namespace of its identity.
        """
        return RobotPlacement(
            namespace=robot.identifier,
            label=robot.label,
            robot_type=self.annotations.named(robot.model),
            pose=PoseText(robot.pose).native(None),
            joint_positions=dict(robot.joint_positions),
        )

    def scene(self) -> RobotScene:
        """
        :return: Every robot of the plan, the performing one selected.
        """
        return RobotScene(
            placements=[self.placement(robot) for robot in self.plan.robots],
            selected_namespace=self.performing().identifier,
        )


# %% demo


@dataclass
class PlannedTaskDemo(RobotTaskDemo):
    """
    Runs a plan composed in the plan builder: its robots and objects in its environment,
    the performing robot's steps one after another.
    """

    document: DemoDocument = field(kw_only=True)
    """
    The plan and where its environment was found.
    """

    robot_scene: RobotScene = field(kw_only=True)
    """
    The plan's robots.
    """

    bodies: Dict[str, Body] = field(default_factory=dict, init=False)
    """
    The plan's objects by identity, once the world is built.
    """

    @classmethod
    def of_document(cls, document: DemoDocument, port: int) -> PlannedTaskDemo:
        """
        :param document: A plan the plan builder checked, and its environment.
        :param port: The port the run is published on.
        :return: The demo; a plan in an environment bundle is recorded as
            ``<bundle>_<robot model>_<plan name>``, otherwise under the plan's name.
        :raises EnvironmentBundleHoldsRobot: When the environment bundle holds a robot.
        """
        plan = document.plan
        robots = PlannedRobots(plan)
        performing = robots.performing()
        scene = robots.scene()
        fields = dict(
            robot=robots.placement(performing).specification(),
            task=plan.task or plan.name,
            port=port,
            document=document,
            robot_scene=scene,
        )
        if document.environment_directory is None:
            return cls(environment=EmptyFloor(), name=plan.name, **fields)
        return cls.in_environment_bundle(
            Path(document.environment_directory),
            robot_name=performing.model,
            task_identifier=plan.name,
            **fields,
        )

    @property
    def plan(self) -> PlanDocument:
        """
        The plan the demo runs.
        """
        return self.document.plan

    def steps(self) -> List[PlanStep]:
        """
        :return: The performing robot's steps.
        """
        return PlannedRobots(self.plan).performing().steps

    def build_world(self) -> World:
        """
        :return: A new world holding the environment, every robot at its start pose
            and posture, and the plan's objects.
        """
        world = self.robot_scene.build_world(self.environment)
        self.bodies = PlannedObjects(self.plan.objects).spawn(world)
        return world

    def build_context(self, world: World) -> Context:
        return Context(world=world, robot=self.robot_scene.selected_robot(world))

    def build_plan(self, context: Context) -> Plan:
        actions = StepActions(context, self.bodies)
        return sequential(
            [actions.action(step) for step in self.steps()], context=context
        ).plan

    def measure(self, context: Context) -> AcceptanceMetrics:
        """
        Measure how far each object put down at a pose ended from it.

        :param context: The world after the plan ran.
        :return: The distances by step.
        :raises TaskFailed: When an object ended farther than
            :data:`PLACEMENT_TOLERANCE` from its pose.
        """
        measurements = {}
        for step in self.placements():
            position = NumericPose.of_entity(
                context.world, self.bodies[step.object_identifier]
            ).position
            error = math.dist(position, step.target.to_json()[:3])
            if error > PLACEMENT_TOLERANCE:
                raise TaskFailed(
                    f"{step.object_identifier} ended {error:.3f} m from the pose of "
                    f"{step.identifier}"
                )
            measurements[
                MEASUREMENT_SEPARATOR.join((PLACEMENT_ERROR, step.identifier))
            ] = error
        return AcceptanceMetrics(measurements=measurements)

    def placements(self) -> Iterator[PlanStep]:
        """
        :return: The performing robot's steps that put an object down at a pose.
        """
        for step in self.steps():
            if (
                step.kind in (StepKind.TRANSPORT, StepKind.PLACE)
                and step.placement is PlacementMode.POSE
            ):
                yield step

    def scene_name(self) -> str:
        """
        :return: The recording's name: the demo's name when it is a valid name, else
            the plan's, followed by ``_2``, ``_3`` and so on when the local scenes
            directory already holds it.
        """
        base = self.name if SceneName.is_valid(self.name) else self.plan.name
        name = base
        repeat = FIRST_REPEAT
        while (self.locations.local_scenes / name).exists():
            suffix = f"{NAME_PART_SEPARATOR}{repeat}"
            name = f"{base[: MAXIMUM_NAME_LENGTH - len(suffix)]}{suffix}"
            repeat += 1
        return SceneName(name).text
