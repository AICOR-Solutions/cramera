"""
Checks of the commands a person sends before they reach the simulation: which fields an
action takes, and that every number is finite.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import Dict, FrozenSet, Mapping, Optional

from cramera_laboratory.exceptions import (
    AmbiguousManualRequest,
    MissingRequestField,
    NonFiniteValue,
    RequestField,
    UnexpectedRequestField,
    ZeroQuaternion,
)
from cramera_laboratory.knowledge import CentrifugeManual
from cramera_protocol.laboratory.physics import (
    CentrifugeAction,
    CentrifugeRequest,
    DispenserAction,
    DispenserRequest,
    LiquidRequest,
    ManualRequest,
    TargetRequest,
)

SMALLEST_QUATERNION = 1e-8
"""
The shortest quaternion that still names an orientation.
"""


class Quantity(StrEnum):
    """
    The quantities a command gives.
    """

    POSITION = "target position"
    """
    A pull target's position.
    """

    ORIENTATION = "target orientation"
    """
    A pull target's orientation.
    """

    VOLUME = "liquid volume"
    """
    An amount of liquid.
    """

    SPEED = "rotor speed"
    """
    A rotor speed.
    """

    DURATION = "cycle duration"
    """
    A cycle length.
    """

    DOSE = "dose"
    """
    A dose.
    """


# %% fields


@dataclass(frozen=True)
class ActionFields:
    """
    The optional fields one action needs and the ones it may take.
    """

    required: FrozenSet[RequestField] = frozenset()
    """
    The fields the action needs.
    """

    optional: FrozenSet[RequestField] = frozenset()
    """
    The fields the action may take.
    """

    def check(self, action: str, given: Mapping[RequestField, object]) -> None:
        """
        :param action: The action.
        :param given: Each optional field of the request with its value, None when
            absent.
        :raises MissingRequestField: When a needed field is absent.
        :raises UnexpectedRequestField: When a field the action does not take is given.
        """
        for name, value in given.items():
            if value is None and name in self.required:
                raise MissingRequestField(action, name)
            if value is not None and name not in self.required | self.optional:
                raise UnexpectedRequestField(action, name)


CENTRIFUGE_FIELDS: Dict[CentrifugeAction, ActionFields] = {
    CentrifugeAction.OPEN: ActionFields(),
    CentrifugeAction.CLOSE: ActionFields(),
    CentrifugeAction.STOP: ActionFields(),
    CentrifugeAction.SECURE: ActionFields(
        required=frozenset({RequestField.SLOT, RequestField.KEY})
    ),
    CentrifugeAction.RELEASE: ActionFields(required=frozenset({RequestField.SLOT})),
    CentrifugeAction.START: ActionFields(
        optional=frozenset({RequestField.SPEED, RequestField.DURATION})
    ),
}
"""
The fields each centrifuge action takes.
"""

DISPENSER_FIELDS: Dict[DispenserAction, ActionFields] = {
    DispenserAction.STOP: ActionFields(),
    DispenserAction.RESUME: ActionFields(),
    DispenserAction.REFILL: ActionFields(required=frozenset({RequestField.CHANNEL})),
    DispenserAction.DISPENSE: ActionFields(
        required=frozenset({RequestField.KEY, RequestField.CHANNEL}),
        optional=frozenset({RequestField.VOLUME}),
    ),
}
"""
The fields each dispensing station action takes.
"""


# %% checks


@dataclass(frozen=True)
class CommandCheck:
    """
    Checks commands before the simulation acts on them.
    """

    @staticmethod
    def finite(quantity: Quantity, *values: Optional[float]) -> None:
        """
        :param quantity: What the numbers stand for.
        :param values: The numbers; None stands for an absent value.
        :raises NonFiniteValue: When a number is not finite.
        """
        if any(value is not None and not math.isfinite(value) for value in values):
            raise NonFiniteValue(quantity)

    def target(self, request: TargetRequest) -> None:
        """
        :param request: A pull target.
        :raises NonFiniteValue: When a coordinate is not finite.
        :raises ZeroQuaternion: When the orientation has no length.
        """
        self.finite(Quantity.POSITION, *request.position.to_json())
        if request.orientation is None:
            return
        components = request.orientation.to_json()
        self.finite(Quantity.ORIENTATION, *components)
        if math.hypot(*components) < SMALLEST_QUATERNION:
            raise ZeroQuaternion()

    def liquid(self, request: LiquidRequest) -> None:
        """
        :param request: A liquid amount.
        :raises NonFiniteValue: When the volume is not finite.
        """
        self.finite(Quantity.VOLUME, request.volume)

    def centrifuge(self, request: CentrifugeRequest) -> None:
        """
        :param request: A centrifuge operation.
        :raises MissingRequestField: When its action needs a field it lacks.
        :raises UnexpectedRequestField: When it gives a field its action does not take.
        :raises NonFiniteValue: When its speed or duration is not finite.
        """
        CENTRIFUGE_FIELDS[request.action].check(
            request.action,
            {
                RequestField.SLOT: request.slot,
                RequestField.KEY: request.key,
                RequestField.SPEED: request.speed,
                RequestField.DURATION: request.duration,
            },
        )
        self.finite(Quantity.SPEED, request.speed)
        self.finite(Quantity.DURATION, request.duration)

    def dispenser(self, request: DispenserRequest) -> None:
        """
        :param request: A dispensing station operation.
        :raises MissingRequestField: When its action needs a field it lacks.
        :raises UnexpectedRequestField: When it gives a field its action does not take.
        :raises NonFiniteValue: When its dose is not finite.
        """
        DISPENSER_FIELDS[request.action].check(
            request.action,
            {
                RequestField.KEY: request.key,
                RequestField.CHANNEL: request.channel,
                RequestField.VOLUME: request.volume,
            },
        )
        self.finite(Quantity.DOSE, request.volume)

    @staticmethod
    def manual(request: ManualRequest) -> CentrifugeManual:
        """
        :param request: A manual request.
        :return: The manual it names, read.
        :raises AmbiguousManualRequest: Unless it names exactly one of an edition and a
            text.
        :raises InvalidManual: When the text is no readable manual.
        """
        if (request.edition is None) == (request.document is None):
            raise AmbiguousManualRequest()
        if request.edition is not None:
            return CentrifugeManual.shipped(request.edition)
        return CentrifugeManual.of_text(request.document)
