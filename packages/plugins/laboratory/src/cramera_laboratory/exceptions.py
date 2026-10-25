"""
Requests and configurations the laboratory refuses.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from http import HTTPStatus
from pathlib import Path

from typing_extensions import List

from cramera.exceptions import ViewerError

# %% base


@dataclass
class LaboratoryError(ViewerError):
    """
    A request or configuration the laboratory cannot serve.
    """


# %% laboratories and resources


@dataclass
class UnknownLaboratory(LaboratoryError):
    """
    A laboratory name the plugin does not ship.
    """

    name: str
    """
    The name that was given.
    """

    known: List[str]
    """
    The laboratories the plugin ships.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return f"No laboratory is named {self.name!r}; known: {', '.join(self.known)}."


@dataclass
class MissingLaboratoryBundle(LaboratoryError):
    """
    A directory that holds no laboratory bundle.
    """

    directory: Path
    """
    The directory that was given.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return f"{self.directory} holds no laboratory bundle."


@dataclass
class NotALaboratory(LaboratoryError):
    """
    A scene bundle without the laboratory's bench.
    """

    directory: Path
    """
    The bundle directory.
    """

    def message(self) -> str:
        return f"The bundle {self.directory} describes no laboratory bench."


@dataclass
class UnknownDevice(LaboratoryError):
    """
    A device name the catalog does not hold.
    """

    name: str
    """
    The name that was given.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return f"No laboratory device is named {self.name!r}."


@dataclass
class DeviceFolderExists(LaboratoryError):
    """
    A device copy whose destination exists already.
    """

    destination: Path
    """
    The destination folder.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.CONFLICT

    def message(self) -> str:
        return f"{self.destination} exists already; choose another folder."


# %% requests


@dataclass
class InvalidRequestBody(LaboratoryError):
    """
    A request body that is not a JSON object.
    """

    reason: str
    """
    Why it cannot be read.
    """

    def message(self) -> str:
        return f"The request body is not JSON: {self.reason}"


class RequestField(StrEnum):
    """
    The request fields an action can require or forbid, named as the request writes
    them.
    """

    SLOT = "slot"
    """
    A holder.
    """

    KEY = "key"
    """
    An object.
    """

    SPEED = "rpm"
    """
    A rotor speed.
    """

    DURATION = "duration"
    """
    A cycle length.
    """

    CHANNEL = "source"
    """
    A reagent channel.
    """

    VOLUME = "volumeMl"
    """
    A dose.
    """

    EDITION = "edition"
    """
    A manual edition.
    """

    DOCUMENT = "document"
    """
    A manual text.
    """


@dataclass
class MissingRequestField(LaboratoryError):
    """
    A request that lacks a field its action needs.
    """

    action: str
    """
    The requested action.
    """

    field_name: RequestField
    """
    The missing field.
    """

    def message(self) -> str:
        return f"The action {self.action!r} needs {self.field_name.value!r}."


@dataclass
class UnexpectedRequestField(LaboratoryError):
    """
    A request that gives a field its action does not take.
    """

    action: str
    """
    The requested action.
    """

    field_name: RequestField
    """
    The field that does not belong.
    """

    def message(self) -> str:
        return f"The action {self.action!r} takes no {self.field_name.value!r}."


@dataclass
class AmbiguousManualRequest(LaboratoryError):
    """
    A manual request that names neither or both of an edition and a text.
    """

    def message(self) -> str:
        return "Give exactly one of a manual edition and a manual text."


@dataclass
class NonFiniteValue(LaboratoryError):
    """
    A number that is not finite.
    """

    quantity: str
    """
    What the number stands for.
    """

    def message(self) -> str:
        return f"The {self.quantity} must be a finite number."


@dataclass
class ValueOutOfRange(LaboratoryError):
    """
    A number outside the range its quantity allows.
    """

    quantity: str
    """
    What the number stands for.
    """

    value: float
    """
    The number given.
    """

    lowest: float
    """
    The smallest allowed value.
    """

    highest: float
    """
    The largest allowed value.
    """

    def message(self) -> str:
        return (
            f"The {self.quantity} {self.value:g} lies outside "
            f"{self.lowest:g} to {self.highest:g}."
        )


@dataclass
class ZeroQuaternion(LaboratoryError):
    """
    An orientation whose quaternion has no length.
    """

    def message(self) -> str:
        return "An orientation quaternion must not be zero."


@dataclass
class UnknownObject(LaboratoryError):
    """
    An object key the simulated laboratory does not hold, or one that cannot take the
    request.
    """

    key: str
    """
    The key that was given.
    """

    role: str
    """
    What the object was asked to be, such as a vessel.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return f"The laboratory has no {self.role} {self.key!r}."


@dataclass
class UnknownInstrument(LaboratoryError):
    """
    An instrument the expanded laboratory does not hold.
    """

    identifier: str
    """
    The identifier that was given.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return f"The laboratory has no instrument {self.identifier!r}."


# %% simulation


@dataclass
class PhysicsUnavailable(LaboratoryError):
    """
    A simulation request where MuJoCo is not installed.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.SERVICE_UNAVAILABLE

    def message(self) -> str:
        return (
            "The contact simulation needs MuJoCo; install cramera-laboratory[physics]."
        )


@dataclass
class SimulationNotRunning(LaboratoryError):
    """
    A simulation command while no simulation runs.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.CONFLICT

    def message(self) -> str:
        return "Start the laboratory's contact simulation first."


class Refusal(StrEnum):
    """
    Why an instrument refuses an operation in its measured state.
    """

    NO_CENTRIFUGE = "This laboratory has no centrifuge."
    """
    The laboratory lacks a centrifuge.
    """

    CLAMPED_VESSEL = "Release this vessel from the centrifuge holder first."
    """
    The vessel is clamped in the rotor.
    """

    ROTOR_TURNING = "Wait until the rotor has completely stopped."
    """
    The rotor still turns.
    """

    NOT_LOADABLE = "Stop the rotor and open the lid fully before loading."
    """
    The rotor turns or the lid is not fully open.
    """

    UNKNOWN_HOLDER = "Select an existing vessel and centrifuge holder."
    """
    The holder or the vessel does not exist.
    """

    HOLDER_TAKEN = "The holder or the vessel is secured already."
    """
    The holder or the vessel is clamped already.
    """

    NOT_SEATED = "Seat the vessel on the holder floor and let it settle first."
    """
    The vessel does not rest upright on the holder's floor.
    """

    EMPTY_HOLDER = "This holder has no secured vessel."
    """
    Nothing is clamped in the holder.
    """

    NOT_READY_TO_START = "Close the lid and secure a balanced opposing pair first."
    """
    The lid is open, the load is unbalanced or the rotor turns.
    """

    STOP_FOR_MANUAL = "Stop the rotor before reading another manual."
    """
    The rotor turns while another manual is given.
    """

    NO_REFRIGERATOR = "This laboratory has no sample refrigerator."
    """
    The laboratory lacks a refrigerator.
    """

    REFRIGERATOR_CLOSED = "Open the refrigerator door before moving the stored sample."
    """
    A stored vessel is taken while the door is not fully open.
    """

    NO_DRAWER = "This laboratory has no drawer."
    """
    The laboratory lacks a drawer.
    """

    NO_SCALE = "This laboratory has no scale."
    """
    The laboratory lacks a scale.
    """

    UNSETTLED_SCALE = "Wait for the scale's reading to settle."
    """
    The scale's reading has not settled.
    """

    NO_DISPENSER = "This laboratory has no dispensing station."
    """
    The laboratory lacks a dispensing station.
    """

    DOSE_RUNNING = "Stop the current dose first."
    """
    A dose is delivered.
    """

    NOTHING_TO_RESUME = "There is no unfinished dose to resume."
    """
    No dose stopped before its end.
    """

    RECEIVER_UNKNOWN = "Select a vessel that holds liquid."
    """
    The dose's receiver holds no liquid.
    """

    RECEIVER_CLAMPED = "Release the receiver from the centrifuge first."
    """
    The receiver is clamped in the rotor.
    """

    RECEIVER_MISPLACED = "Place the receiver beneath the dispensing nozzle."
    """
    The receiver does not stand at the station.
    """

    RECEIVER_TILTED = "Keep the receiver upright beneath the nozzle."
    """
    The receiver leans.
    """

    RIM_MISALIGNED = "Align the open rim directly beneath the nozzle."
    """
    The receiver's rim is not under the nozzle at a dispensing height.
    """

    STOPPER_IN_PLACE = "Remove the stopper before dispensing into this receiver."
    """
    The receiver is closed.
    """

    RECEIVER_FULL = "The receiver has too little room for this dose."
    """
    The dose would overflow the receiver.
    """

    RESERVOIR_EMPTY = "The selected reagent reservoir holds too little liquid."
    """
    The reservoir holds less than the dose.
    """

    DOSE_DELIVERING = "Stop the current dose before changing the receiver's liquid."
    """
    The vessel receives a dose while its liquid is set.
    """

    NO_INSTRUMENTS = "This laboratory has no instrument collection."
    """
    The laboratory lacks the expanded instrument collection.
    """

    NO_RACK = "This laboratory's rack does not move freely."
    """
    The rack is fixed to the bench.
    """


@dataclass
class OperationRefused(LaboratoryError):
    """
    An operation an instrument refuses in its measured state.
    """

    refusal: Refusal
    """
    Why it refuses.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.CONFLICT

    def message(self) -> str:
        return self.refusal.value


@dataclass
class TooFewSamples(LaboratoryError):
    """
    A centrifuge start with fewer secured samples than the manual asks for.
    """

    version: str
    """
    The manual's version.
    """

    required: int
    """
    How many samples the manual asks for.
    """

    secured: int
    """
    How many are secured.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.CONFLICT

    def message(self) -> str:
        return (
            f"Manual {self.version}: at least {self.required} secured samples are "
            f"required; {self.secured} are secured."
        )


class ManualProblem(StrEnum):
    """
    Why a manual cannot be read.
    """

    TOO_LONG = "The manual must be text of at most 8192 bytes in UTF-8."
    """
    The text is empty, too long or not encodable.
    """

    TITLE = "The manual needs exactly one title."
    """
    The text has no or several first-level headings.
    """

    VERSION = "The manual needs exactly one valid document version."
    """
    The text has no, several or a malformed version line.
    """

    RULE_SECTION = "The manual needs exactly one Operating rules section."
    """
    The text has no or several rule sections.
    """

    HEADER = "The rule table needs exactly one header row."
    """
    The rule table's header is missing or repeated.
    """

    SEPARATOR = "The separator row must follow the table header directly."
    """
    The rule table's separator is misplaced.
    """

    UNSUPPORTED_RULE = (
        "Operating rules supports only Minimum secured samples with 2 or 4."
    )
    """
    The table states a rule or value the laboratory does not support.
    """

    RULE_COUNT = "The manual needs exactly one Minimum secured samples rule."
    """
    The table states the rule not exactly once.
    """


@dataclass
class InvalidManual(LaboratoryError):
    """
    A manual that cannot be read.
    """

    problem: ManualProblem
    """
    What is wrong with it.
    """

    def message(self) -> str:
        return self.problem.value


@dataclass
class InvalidLaboratoryModel(LaboratoryError):
    """
    Authored laboratory files the contact simulation cannot be built from.
    """

    reason: str
    """
    What is wrong.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.INTERNAL_SERVER_ERROR

    def message(self) -> str:
        return f"The laboratory cannot be simulated: {self.reason}"
