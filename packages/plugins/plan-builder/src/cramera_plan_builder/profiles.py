"""
The robot profile a deployment configures: the profile itself, the plan templates its
file names, and how the profile's skills keep saved plans current.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from typing_extensions import List, Mapping, Optional

from cramera_protocol.plan_builder import PlanDocument, PlanStep, PlanTemplate
from cramera_protocol.robot_profile import RobotProfile, RobotProfileVariable

# %% configured profile


@dataclass(frozen=True)
class ConfiguredProfile:
    """
    The robot profile a deployment names, with the templates its file refers to.
    """

    profile: Optional[RobotProfile] = None
    """
    The profile, or None when the deployment names none.
    """

    templates: List[PlanTemplate] = field(default_factory=list)
    """
    The plans the profile offers to start from, in the profile's order.
    """

    @classmethod
    def of_environment(cls, environment: Mapping[str, str]) -> ConfiguredProfile:
        """
        :param environment: The process environment, which may name the profile's file.
        :return: The profile it names with its templates, or no profile.
        """
        path = environment.get(RobotProfileVariable.PROFILE)
        return cls.of_file(Path(path).expanduser()) if path else cls()

    @classmethod
    def of_file(cls, path: Path) -> ConfiguredProfile:
        """
        :param path: A profile's JSON file.
        :return: The profile with the templates it names, read relative to the file.
        """
        profile = RobotProfile.from_file(path)
        return cls(
            profile=profile,
            templates=[
                PlanTemplate(
                    identifier=Path(template).stem,
                    plan=PlanDocument.from_json(
                        json.loads((path.parent / template).read_text("utf-8"))
                    ),
                )
                for template in profile.templates
            ],
        )

    def resolved(self, plan: PlanDocument) -> PlanDocument:
        """
        :param plan: A plan whose steps may name skills of the profile.
        :return: The plan with every step of a known skill naming that skill's current
            action, and stamped with the profile's platform version; a plan unchanged
            without a profile.
        """
        if self.profile is None:
            return plan
        return replace(
            plan,
            platform_version=self.profile.platform_version,
            robots=[
                replace(robot, steps=[self.resolved_step(step) for step in robot.steps])
                for robot in plan.robots
            ],
        )

    def resolved_step(self, step: PlanStep) -> PlanStep:
        """
        :param step: A step of a plan.
        :return: The step naming the action its skill maps to now; a step without a
            skill, or of a skill the profile no longer has, unchanged.
        """
        skill = None if step.skill is None else self.profile.skill_named(step.skill)
        if skill is None:
            return step
        return replace(step, action=skill.action)
