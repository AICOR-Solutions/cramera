"""
A robot profile: how the plan builder is set up for one robot at one site, which robot
plans start with, the environment it stands in, the skills people compose plans from and
the plans they start from.

A deployment names its profile with :attr:`RobotProfileVariable.PROFILE`; without one
the plan builder offers every robot and action of the CRAM workspace.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from typing_extensions import Any, Dict, List, Optional, Self

from cramera_protocol.document import JsonDocument, document_field
from cramera_protocol.version import ProtocolVersion

PROFILE_FORMAT_VERSION = ProtocolVersion(major=1, minor=0)
"""
The version profiles are written with.
"""


class RobotProfileVariable(StrEnum):
    """
    The environment variables a deployment configures the profile with.
    """

    PROFILE = "CRAMERA_ROBOT_PROFILE"
    """
    The path of the robot profile's JSON file.
    """


class ExecutorKind(StrEnum):
    """
    How a run of a plan executes its motions, which picks the plan executor the
    generated program runs the plan with.

    A robot executing on its real hardware is added here with the executor that drives
    it, and a profile names it for the run mode that runs on the robot.
    """

    KINEMATIC = "kinematic"
    """
    Moves the world kinematically, as fast as the controller computes the motions.
    """

    PHYSICS = "physics"
    """
    Runs the motions against a physics simulation of the world (MuJoCo), where an object
    is held by friction alone.
    """


class SkillKey(StrEnum):
    """
    The keys of a skill.
    """

    IDENTIFIER = "id"
    """
    The skill's stable identity, which plans name.
    """

    LABEL = "label"
    """
    The skill's name in the palette.
    """

    ACTION = "action"
    """
    The native action the skill carries out.
    """

    VALUES = "values"
    """
    The values the skill sets on its action's fields.
    """

    FIELDS = "fields"
    """
    The action's fields a person edits.
    """

    DOCUMENTATION = "documentation"
    """
    What the skill does, in a sentence.
    """


@dataclass(kw_only=True)
class Skill(JsonDocument):
    """
    A capability the robot offers people, carried out by a native action with some of
    its fields set.

    A plan names the skill by its identifier, so the platform can map the skill to
    another action without breaking saved plans.
    """

    identifier: str = document_field(SkillKey.IDENTIFIER)
    """
    The skill's stable identity, which a step keeps across platform versions.
    """

    label: str = document_field(SkillKey.LABEL)
    """
    The skill's name in the palette and on its steps.
    """

    action: str = document_field(SkillKey.ACTION)
    """
    The identifier of the native action that carries the skill out, as the catalog's
    action schemas name it.
    """

    values: Dict[str, Any] = document_field(SkillKey.VALUES, default_factory=dict)
    """
    The JSON values a new step of the skill starts with, by field name.
    """

    fields: Optional[List[str]] = document_field(SkillKey.FIELDS, default=None)
    """
    The names of the action's fields a person edits on a step of the skill; the others
    keep their values.

    None shows every field.
    """

    documentation: str = document_field(SkillKey.DOCUMENTATION, default="")
    """
    What the skill does, shown with its palette entry.
    """


class RobotProfileKey(StrEnum):
    """
    The keys of a robot profile.
    """

    FORMAT_VERSION = "formatVersion"
    """
    The format version the profile is written in.
    """

    ROBOT = "robot"
    """
    The robot model plans start with.
    """

    LABEL = "label"
    """
    The name the site gives the robot.
    """

    ENVIRONMENT = "environment"
    """
    The environment bundle the robot stands in.
    """

    PLATFORM_VERSION = "platformVersion"
    """
    The version of the platform the profile belongs to.
    """

    SKILLS = "skills"
    """
    The skills people compose plans from.
    """

    TEMPLATES = "templates"
    """
    The files of the plans people start from.
    """

    EXECUTORS = "executors"
    """
    How each run mode the robot offers executes its plan.
    """


@dataclass(kw_only=True)
class RobotProfile(JsonDocument):
    """
    The plan builder's setup for one robot.
    """

    robot: str = document_field(RobotProfileKey.ROBOT)
    """
    The identifier of the robot model a new plan starts with, as the catalog lists it.
    """

    label: str = document_field(RobotProfileKey.LABEL)
    """
    The name shown for the robot.
    """

    environment: Optional[str] = document_field(
        RobotProfileKey.ENVIRONMENT, default=None
    )
    """
    The environment bundle a new plan is set in, or None for an empty floor.
    """

    platform_version: Optional[str] = document_field(
        RobotProfileKey.PLATFORM_VERSION, default=None
    )
    """
    The version of the platform the profile belongs to, which plans saved with it
    record; None outside a platform.
    """

    skills: List[Skill] = document_field(RobotProfileKey.SKILLS, default_factory=list)
    """
    The skills the palette offers, in order; empty offers every native action.
    """

    templates: List[str] = document_field(
        RobotProfileKey.TEMPLATES, default_factory=list
    )
    """
    The plan files a new plan can start from, relative to the profile's file.
    """

    executors: Dict[str, ExecutorKind] = document_field(
        RobotProfileKey.EXECUTORS, default_factory=dict
    )
    """
    How a run of each mode the robot offers executes, by the run mode's value; empty
    offers every run mode with its default executor.
    """

    format_version: ProtocolVersion = document_field(
        RobotProfileKey.FORMAT_VERSION, default=PROFILE_FORMAT_VERSION
    )
    """
    The format version the profile is written in.
    """

    def __post_init__(self) -> None:
        self.format_version.require_readable_by(PROFILE_FORMAT_VERSION)

    def skill_named(self, identifier: str) -> Optional[Skill]:
        """
        :param identifier: A skill's identifier.
        :return: The profile's skill of that identifier, or None when it has none.
        """
        for skill in self.skills:
            if skill.identifier == identifier:
                return skill
        return None

    def executor_for(
        self, mode: str, default: Optional[ExecutorKind]
    ) -> Optional[ExecutorKind]:
        """
        :param mode: The value of a run mode that performs the plan.
        :param default: How the mode executes unless the profile says otherwise.
        :return: How the profile executes a run of that mode: the executor it names,
            the default when it names none at all, or None when it names others only.
        """
        if not self.executors:
            return default
        return self.executors.get(mode)

    @classmethod
    def from_file(cls, path: Path) -> Self:
        """
        :param path: A profile's JSON file.
        :return: The profile it holds.
        """
        return cls.from_json(json.loads(path.read_text(encoding="utf-8")))
