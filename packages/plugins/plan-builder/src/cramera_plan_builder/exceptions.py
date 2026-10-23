"""
Requests, plans and configurations the plan builder refuses.
"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path

from typing_extensions import Any, List, Optional

from cramera.exceptions import ViewerError

# %% base


@dataclass
class PlanBuilderError(ViewerError):
    """
    A request or configuration the plan builder cannot serve.
    """


# %% request bodies


@dataclass
class ContentTooLarge(PlanBuilderError):
    """
    A request body larger than the builder accepts.
    """

    size: int
    """
    The body's size in bytes.
    """

    limit: int
    """
    The largest accepted size in bytes.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.REQUEST_ENTITY_TOO_LARGE

    def message(self) -> str:
        return (
            f"The request holds {self.size} bytes; at most {self.limit} are accepted."
        )


@dataclass
class MalformedRequestBody(PlanBuilderError):
    """
    A request body that is no UTF-8 JSON text.
    """

    reason: str
    """
    Why the decoder refused it.
    """

    def message(self) -> str:
        return f"The request body is no JSON text: {self.reason}"


# %% plans


@dataclass
class InvalidPlanText(PlanBuilderError):
    """
    A name, label, task or constraint that is blank, too long or holds control
    characters.
    """

    location: str
    """
    Where the text sits in the plan.
    """

    text: str
    """
    The text.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return (
            f"{self.location} must be a short text without control characters, "
            f"not {self.text!r}."
        )


@dataclass
class InvalidPlanName(PlanBuilderError):
    """
    A plan name that cannot name a demo file and a recording.
    """

    name: str
    """
    The name.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return (
            f"{self.name!r} cannot name a demo and its recording: use 1 to 64 "
            f"letters, digits, '_' or '-'."
        )


@dataclass
class InvalidIdentifier(PlanBuilderError):
    """
    A plan, robot, object or step identity of other characters than a plan allows.
    """

    location: str
    """
    Where the identity sits in the plan.
    """

    identifier: str
    """
    The identity.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return (
            f"{self.location} {self.identifier!r} must start with a letter and hold "
            f"only letters, digits and '_'."
        )


@dataclass
class DuplicateIdentifier(PlanBuilderError):
    """
    Two robots, objects or steps of a plan with one identity.
    """

    location: str
    """
    Where the identities sit in the plan.
    """

    identifier: str
    """
    The identity they share.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return f"Two entries of {self.location} are named {self.identifier!r}."


@dataclass
class TooManyEntries(PlanBuilderError):
    """
    More robots, objects, steps or constraints than a plan holds.
    """

    location: str
    """
    Where the entries sit in the plan.
    """

    count: int
    """
    How many entries there are.
    """

    limit: int
    """
    How many entries fit.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return f"{self.location} holds {self.count} entries; at most {self.limit} fit."


@dataclass
class ValueOutOfRange(PlanBuilderError):
    """
    A coordinate or joint value that is not finite or beyond the limit.
    """

    location: str
    """
    Where the number sits in the plan.
    """

    value: float
    """
    The number.
    """

    limit: float
    """
    The largest allowed magnitude.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return (
            f"{self.location} is {self.value}; it must be finite and at most "
            f"{self.limit} in magnitude."
        )


@dataclass
class UnknownReference(PlanBuilderError):
    """
    A plan entry naming a robot or object the plan does not hold.
    """

    location: str
    """
    Where the reference sits in the plan.
    """

    reference: str
    """
    The name that was referred to.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return (
            f"{self.location} names {self.reference!r}, which the plan does not hold."
        )


@dataclass
class MissingStepParameter(PlanBuilderError):
    """
    A step without a value its action needs.
    """

    location: str
    """
    Where the value is missing in the plan.
    """

    parameter: str
    """
    The name of the missing field or key.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return f"{self.location} needs {self.parameter!r}."


@dataclass
class UnknownStepAction(PlanBuilderError):
    """
    A step naming an action the installed CRAM workspace does not offer.
    """

    location: str
    """
    Where the step's action sits in the plan.
    """

    action: str
    """
    The action's class name.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return (
            f"{self.location} is {self.action!r}, an action the installed CRAM "
            f"workspace does not offer."
        )


@dataclass
class UnavailableStepAction(PlanBuilderError):
    """
    A step naming an action the builder cannot fill in, since a required field has no
    form control.
    """

    location: str
    """
    Where the step's action sits in the plan.
    """

    action: str
    """
    The action's class name.
    """

    reason: str
    """
    Why the action is unavailable.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return (
            f"{self.location} is {self.action!r}, which is unavailable: {self.reason}."
        )


@dataclass
class UnknownStepField(PlanBuilderError):
    """
    A step giving a value of a field its action does not have.
    """

    location: str
    """
    Where the value sits in the plan.
    """

    name: str
    """
    The field's name.
    """

    action: str
    """
    The action's class name.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return (
            f"{self.location} names {self.name!r}, a field {self.action} does not have."
        )


@dataclass
class InvalidStepValue(PlanBuilderError):
    """
    A step's value that does not fit the kind of its field.
    """

    location: str
    """
    Where the value sits in the plan.
    """

    value: Any
    """
    The value.
    """

    expected: str
    """
    What the value must be.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return f"{self.location} is {self.value!r}; it must be {self.expected}."


@dataclass
class PlanWithoutRobot(PlanBuilderError):
    """
    A plan whose demo is asked for while it holds no robot to perform it.
    """

    name: str
    """
    The plan's name.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return f"The plan {self.name!r} holds no robot to perform it."


@dataclass
class UnsupportedByCatalog(PlanBuilderError):
    """
    A plan entry the catalog does not offer: an unknown robot, object model, environment
    or surface type, or an enumeration member the robot does not have.
    """

    location: str
    """
    Where the entry sits in the plan.
    """

    value: str
    """
    The value the catalog does not offer.
    """

    offered: List[str]
    """
    What the catalog offers there.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return f"{self.location} is {self.value!r}, which is not one of {self.offered}."


@dataclass
class PlanTooLarge(PlanBuilderError):
    """
    A plan whose JSON is larger than the builder keeps.
    """

    size: int
    """
    The plan's size in bytes.
    """

    limit: int
    """
    The largest size in bytes.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.REQUEST_ENTITY_TOO_LARGE

    def message(self) -> str:
        return f"The plan holds {self.size} bytes; at most {self.limit} are kept."


@dataclass
class UnknownPlan(PlanBuilderError):
    """
    A plan identity no saved plan has.
    """

    identifier: str
    """
    The identity.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return f"No saved plan is named {self.identifier!r}."


@dataclass
class UnreadablePlan(PlanBuilderError):
    """
    A saved plan whose file is damaged.
    """

    identifier: str
    """
    The plan's identity.
    """

    reason: str
    """
    Why it cannot be read.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.INTERNAL_SERVER_ERROR

    def message(self) -> str:
        return f"The saved plan {self.identifier!r} cannot be read: {self.reason}"


@dataclass
class UnsafeStoragePath(PlanBuilderError):
    """
    A storage directory or file that is a symbolic link, which could lead writes
    elsewhere.
    """

    path: Path
    """
    The path.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.INTERNAL_SERVER_ERROR

    def message(self) -> str:
        return f"{str(self.path)!r} is a symbolic link; the plan builder does not follow it."


# %% constraints


@dataclass
class ConstraintSubjectMissing(PlanBuilderError):
    """
    A constraint whose monitor needs an object while neither the sentence nor its step
    names one.
    """

    text: str
    """
    The constraint as it was written.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return (
            f"{self.text!r} is about no object: name one of the plan's objects or "
            f"attach it to a step that acts on one."
        )


@dataclass
class ConstraintReferenceMissing(PlanBuilderError):
    """
    A constraint whose monitor measures against a second object the sentence does not
    name.
    """

    text: str
    """
    The constraint as it was written.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return (
            f"{self.text!r} names no second object to keep a distance from: name two "
            f"of the plan's objects."
        )


# %% CRAM


@dataclass
class CramUnavailable(PlanBuilderError):
    """
    A request that needs the CRAM workspace, which this interpreter cannot import.
    """

    missing: List[str]
    """
    The modules that cannot be found.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.SERVICE_UNAVAILABLE

    def message(self) -> str:
        return (
            f"The CRAM workspace is not importable here; missing modules: "
            f"{', '.join(self.missing)}."
        )


@dataclass
class SurfaceNotInWorld(PlanBuilderError):
    """
    A step putting an object on a surface the world does not hold or that offers no free
    spot.
    """

    surface_type: str
    """
    The class name of the surface annotation.
    """

    surface_name: Optional[str]
    """
    The name of the surface, or None for any surface of the class.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        surface = self.surface_type + (
            f" {self.surface_name!r}" if self.surface_name is not None else ""
        )
        return f"The world offers no free spot on a {surface}."


@dataclass
class AnnotationNotInWorld(PlanBuilderError):
    """
    A step naming an annotated entity the world does not hold.
    """

    annotation: str
    """
    The class name of the annotation.
    """

    name: str
    """
    The name the step gives.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return f"The world holds no {self.annotation} named {self.name!r}."


@dataclass
class ArmNotOnRobot(PlanBuilderError):
    """
    A step naming arms the robot performing it does not have as the field asks for them.
    """

    arms: str
    """
    The name of the arms the step gives.
    """

    robot: str
    """
    The class name of the robot.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return f"A {self.robot} has no single arm named {self.arms}."


@dataclass
class ObjectNotGraspable(PlanBuilderError):
    """
    A step naming an object to grasp that offers no grasp.
    """

    identifier: str
    """
    The object's identity.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return f"The object {self.identifier!r} offers no grasp."


@dataclass
class UnknownWorkspaceClass(PlanBuilderError):
    """
    A robot or surface annotation class the CRAM workspace does not define.
    """

    name: str
    """
    The class name.
    """

    offered: List[str]
    """
    The class names the workspace defines.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return (
            f"The CRAM workspace defines no {self.name!r}; it defines {self.offered}."
        )


# %% runs


@dataclass
class DemoNotStarted(PlanBuilderError):
    """
    A demo whose process could not be started.
    """

    path: Path
    """
    The demo file.
    """

    reason: str
    """
    Why the operating system refused.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.INTERNAL_SERVER_ERROR

    def message(self) -> str:
        return f"The demo {str(self.path)!r} could not be started: {self.reason}"


@dataclass
class UnknownAction(PlanBuilderError):
    """
    An action class name the CRAM workspace does not define.
    """

    name: str
    """
    The class name.
    """

    offered: List[str]
    """
    The class names of the actions the workspace defines.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return f"The CRAM workspace defines no action {self.name!r}."
