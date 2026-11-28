"""
Validating a plan before it runs on the robot: each validation runs cramera-bridge's
validator as a child process of its own, which expects the order validated last and
builds its robots meanwhile, and the plan builder remembers the plan whose validation
passed last, which alone may then run on the robot, and the grounding it passed on,
which a simulated run of that plan performs instead of grounding it again.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field, replace

from typing_extensions import Callable, Optional

from cramera_plan_builder.bridge_processes import BridgeModule, BridgeProcess
from cramera_plan_builder.exceptions import (
    PlanBuilderError,
    ValidationCancelled,
    ValidationFailed,
)
from cramera_protocol.document import JsonDocument
from cramera_protocol.plan_builder import PlanDocument
from cramera_protocol.validation import (
    ValidatedGrounding,
    ValidationOrder,
    ValidationReport,
)

# %% validator


@dataclass(frozen=True)
class PlanValidations(BridgeProcess):
    """
    Validates plans, one process per validation.
    """

    @property
    def module(self) -> BridgeModule:
        return BridgeModule.VALIDATOR

    def describe_failure(self, reason: str, output: str) -> PlanBuilderError:
        return ValidationFailed(reason, output)

    def describe_cancellation(self) -> PlanBuilderError:
        return ValidationCancelled(self.module)

    def expected_order(self, answered: JsonDocument) -> Optional[JsonDocument]:
        """
        :return: The order validated last: a plan is validated again after each edit,
            mostly with the same robots.
        """
        return answered

    def validate(self, order: ValidationOrder) -> ValidationReport:
        """
        :param order: The checked plan and the scene the robot's camera sees.
        :return: How each step of the performing robot fared, and how long the
            validation took, its process's start included.
        :raises CramUnavailable: Without the CRAM workspace.
        :raises ValidationFailed: When the validator ends without a report.
        :raises ValidationCancelled: When the validation is cancelled before it ends.
        """
        started = time.monotonic()
        report = ValidationReport.from_json(self.answer(order))
        return replace(report, seconds=time.monotonic() - started)


# %% gate


@dataclass
class ValidationGate:
    """
    The plan whose validation passed last, which a run needing a validated plan must be;
    read and written by request threads.
    """

    validated: Optional[str] = None
    """
    The JSON text of the plan whose validation passed last, None when the latest
    validation failed or none ran.
    """

    grounding: Optional[ValidatedGrounding] = None
    """
    The grounding the validation that passed last passed on, which a simulated run of
    its plan performs; None when it passed none on or a run on the robot closed the
    gate since.
    """

    kept: Optional[str] = None
    """
    The JSON text of the plan whose passed validation the run that closed the gate
    last took away, which it gives back once it was refused before anything moved.
    """

    kept_if: Callable[[], bool] = lambda: False
    """
    Whether the run that closed the gate last was refused before anything moved.
    """

    lock: threading.Lock = field(default_factory=threading.Lock)
    """
    Guards :attr:`validated`, :attr:`kept` and :attr:`kept_if`.
    """

    def record(self, plan: PlanDocument, report: ValidationReport) -> None:
        """
        :param plan: A plan as it was validated.
        :param report: How its validation went; a failed one closes the gate.
        """
        with self.lock:
            self.validated = self.serialize(plan) if report.passed else None
            self.grounding = report.grounding if report.passed else None
            self.kept = None

    def grounding_for(self, plan: PlanDocument) -> Optional[ValidatedGrounding]:
        """
        :param plan: A plan to run in simulation.
        :return: The grounding the validation that passed last passed on, when that
            validated this plan unchanged and no run on the robot followed it; else
            None, and the run grounds the plan itself.
        """
        with self.lock:
            if self.validated != self.serialize(plan):
                return None
            return self.grounding

    def admits(self, plan: PlanDocument) -> bool:
        """
        :param plan: A plan to run.
        :return: Whether it is the plan whose validation passed last, unchanged.
        """
        with self.lock:
            admitted = self.admitted()
        return admitted is not None and admitted == self.serialize(plan)

    def holds_validation(self) -> bool:
        """
        :return: Whether a plan is admitted now, see :meth:`admitted`.
        """
        with self.lock:
            return self.admitted() is not None

    def admitted(self) -> Optional[str]:
        """
        :return: The JSON text of the plan admitted now: the one whose validation passed
            last, unless a run took it away and was not refused before anything moved;
            the caller holds :attr:`lock`.
        """
        if self.validated is not None:
            return self.validated
        return self.kept if self.kept is not None and self.kept_if() else None

    def close(self, kept_if: Callable[[], bool] = lambda: False) -> None:
        """
        Admit no plan until the next validation passes, as once the robot moved the
        latest validation no longer describes where it stands; a run refused before
        anything moved gives the validation back.

        :param kept_if: Whether the run closing the gate was refused before anything
            moved, asked whenever a plan is to be admitted.
        """
        with self.lock:
            self.kept = self.admitted()
            self.kept_if = kept_if
            self.validated = None
            self.grounding = None

    @staticmethod
    def serialize(plan: PlanDocument) -> str:
        """
        :param plan: A plan.
        :return: Its JSON, the same for the same plan.
        """
        return json.dumps(plan.to_json(), sort_keys=True)
