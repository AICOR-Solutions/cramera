"""
The arms a step names: the builder's own choice of a robot's arm, offered for every
field that takes an arm, several arms or an arm's end effector, and resolved into the
robot's parts when the step's action is built. A step may leave the arm to be chosen
when it is grounded: the arm that reaches.

coraplex names an arm by the robot part itself, which exists only once a robot stands in
a world; a plan names it by side, so that the same plan reads for every robot.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from typing_extensions import Any, List, get_args, get_origin

from cramera_bridge.exceptions import ArmNotOnRobot
from krrood.entity_query_language.factories import variable
from semantic_digital_twin.robots.robot_parts import AbstractRobot, Arm, EndEffector


class Arms(Enum):
    """
    The arms a step can name; the names are those plans are saved with.
    """

    LEFT = auto()
    """
    The left arm of a robot with a left and a right arm.
    """

    RIGHT = auto()
    """
    The right arm of a robot with a left and a right arm.
    """

    BOTH = auto()
    """
    Every arm of the robot, or the only one of a robot with one arm.
    """

    AUTOMATIC = auto()
    """
    The arm that reaches, chosen among the robot's arms when the step is grounded; every
    arm for a field taking several.
    """


ARM_PARTS = (Arm, EndEffector)
"""
The robot parts a field taking an arm names: the arm or its end effector.
"""


@dataclass(frozen=True)
class ArmField:
    """
    The type of a field, asked whether it takes an arm.
    """

    annotation: Any
    """
    A resolved field type.
    """

    def part(self) -> Any:
        """
        :return: The robot part the field takes one or several of, else None.
        """
        if get_origin(self.annotation) in (list, List):
            (member,) = get_args(self.annotation) or (None,)
            return member if self.is_arm_part(member) else None
        return self.annotation if self.is_arm_part(self.annotation) else None

    def takes_several(self) -> bool:
        """
        :return: Whether the field takes a list of arms.
        """
        return get_origin(self.annotation) in (list, List)

    @staticmethod
    def is_arm_part(candidate: Any) -> bool:
        """
        :param candidate: A type.
        :return: Whether it is an arm or an end effector.
        """
        return isinstance(candidate, type) and issubclass(candidate, ARM_PARTS)


@dataclass(frozen=True)
class RobotArms:
    """
    Resolves the arms a step names into the parts of the robot performing it.
    """

    robot: AbstractRobot
    """
    The robot.
    """

    def arms(self, choice: Arms) -> List[Arm]:
        """
        :param choice: The arms a step names.
        :return: The robot's arms the choice stands for, the arms to choose among for
            an automatic choice.
        :raises ArmNotOnRobot: When the robot, or a part of it, names no arm on the
            side.
        """
        if choice in (Arms.BOTH, Arms.AUTOMATIC):
            return list(self.robot.all_arms)
        arm = (
            self.robot.get_left_arm_if_specified()
            if choice is Arms.LEFT
            else self.robot.get_right_arm_if_specified()
        )
        if arm is None:
            raise ArmNotOnRobot(choice.name, type(self.robot).__name__)
        return [arm]

    def value(self, choice: Arms, annotation: Any) -> Any:
        """
        :param choice: The arms a step names.
        :param annotation: The type of the field taking them.
        :return: The field's value: the arms for a field taking several, else the one
            arm, or its end effector for a field taking an end effector; for an
            automatic choice, a variable over the parts of every arm.
        :raises ArmNotOnRobot: When the choice names several arms for a field taking
            one.
        """
        field_type = ArmField(annotation)
        arms = self.arms(choice)
        if field_type.takes_several():
            return arms
        part = field_type.part()
        parts = [
            arm.end_effector if issubclass(part, EndEffector) else arm for arm in arms
        ]
        if choice is Arms.AUTOMATIC:
            return variable(part, domain=parts)
        if len(parts) != 1:
            raise ArmNotOnRobot(choice.name, type(self.robot).__name__)
        return parts[0]

    def find_side(self, part: Arm | EndEffector) -> Arms:
        """
        :param part: An arm of the robot, or an arm's end effector.
        :return: The side of the robot the arm is on; both for the only arm of a robot
            with one arm.
        """
        for choice in (Arms.LEFT, Arms.RIGHT):
            arm = (
                self.robot.get_left_arm_if_specified()
                if choice is Arms.LEFT
                else self.robot.get_right_arm_if_specified()
            )
            if arm is not None and part in (arm, arm.end_effector):
                return choice
        return Arms.BOTH
