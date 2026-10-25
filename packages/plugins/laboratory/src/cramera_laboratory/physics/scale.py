"""
The laboratory scale: the vertical contact load on its pan and holder, filtered like a
real balance's display, with a tare a person takes once the reading settles.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum

import mujoco
import numpy as np
from typing_extensions import Optional, Set, Tuple

from cramera_laboratory.exceptions import OperationRefused, Refusal
from cramera_laboratory.physics.contacts import ContactReader
from cramera_protocol.laboratory.physics import ScaleReading

GRAMS_PER_KILOGRAM = 1000.0
"""
How many grams a kilogram has.
"""

TIME_TOLERANCE = 1e-9
"""
How much earlier than due a sample or a settling window still counts, in seconds.
"""

HALF_DIGIT = 0.5
"""
The share of the display's last digit the filter may still be off by when settled.
"""

# %% names


class ScaleGeometry(StrEnum):
    """
    The geometries that carry the measured load.
    """

    PAN = "laboratory_balance_weighing_pan"
    """
    The weighing pan.
    """

    HOLDER = "laboratory_balance_weighing_holder_"
    """
    The prefix of the numbered segments of the holder ring on the pan.
    """


# %% parameters


@dataclass(frozen=True)
class ScaleParameters:
    """
    How the scale samples, filters and settles.
    """

    sample_period: float = 0.02
    """
    The time between samples, in simulated seconds.
    """

    filter_time_constant: float = 0.12
    """
    The display filter's time constant, in seconds.
    """

    settling_period: float = 0.5
    """
    How long the load must stay calm before the reading counts as settled, in seconds.
    """

    settling_tolerance: float = 0.01
    """
    How far the load may vary within the settling period, in grams.
    """

    decimal_places: int = 3
    """
    The digits after the decimal point the display shows.
    """


# %% scale


@dataclass
class LaboratoryScale:
    """
    The scale's measurement of its pan's contact load.
    """

    model: mujoco.MjModel
    """
    The compiled model.
    """

    data: mujoco.MjData
    """
    The simulation state.
    """

    parameters: ScaleParameters = field(default_factory=ScaleParameters)
    """
    How the scale samples, filters and settles.
    """

    load_geometries: Set[int] = field(init=False)
    """
    The pan and the holder's segments.
    """

    filtered: float = field(init=False, default=0.0)
    """
    The filtered gross load, in grams.
    """

    tare: float = field(init=False, default=0.0)
    """
    The load taken as zero, in grams.
    """

    force: float = field(init=False, default=0.0)
    """
    The latest downward force on the pan, in newtons.
    """

    objects: Tuple[str, ...] = field(init=False, default=())
    """
    The bodies that pressed on the pan at the latest sample.
    """

    samples: deque = field(init=False, default_factory=deque)
    """
    The recent samples as pairs of time and gross load in grams.
    """

    last_sample: Optional[float] = field(init=False, default=None)
    """
    When the latest sample was taken, None before the first.
    """

    @classmethod
    def of_model(
        cls, model: mujoco.MjModel, data: mujoco.MjData
    ) -> Optional[LaboratoryScale]:
        """
        :param model: The compiled model.
        :param data: The simulation state.
        :return: The scale, or None for a laboratory without one.
        """
        pan = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, ScaleGeometry.PAN)
        if pan < 0:
            return None
        return cls(model, data)

    def __post_init__(self) -> None:
        self.load_geometries = {
            index
            for index in range(self.model.ngeom)
            if self.model.geom(index).name == ScaleGeometry.PAN
            or self.model.geom(index).name.removeprefix(ScaleGeometry.HOLDER).isdigit()
            and self.model.geom(index).name.startswith(ScaleGeometry.HOLDER)
        }

    @property
    def gravity(self) -> float:
        """
        The gravitational acceleration, in metres per second squared.
        """
        return float(np.linalg.norm(self.model.opt.gravity))

    @property
    def stable(self) -> bool:
        """
        Whether the load stayed within the tolerance for the settling period and the
        display caught up with it.
        """
        if not self.samples:
            return False
        elapsed = self.samples[-1][0] - self.samples[0][0]
        values = [value for _, value in self.samples]
        return (
            elapsed + TIME_TOLERANCE >= self.parameters.settling_period
            and max(values) - min(values) <= self.parameters.settling_tolerance
            and abs(self.filtered - values[-1])
            <= HALF_DIGIT * 10 ** (-self.parameters.decimal_places)
        )

    def reset(self) -> None:
        """
        Forget the tare and the samples after the laboratory was reset.
        """
        self.filtered = self.tare = self.force = 0.0
        self.objects = ()
        self.samples.clear()
        self.last_sample = None
        self.observe(force=True)

    def observe(self, force: bool = False) -> None:
        """
        Sample the pan's load when a sample is due.

        :param force: Whether to sample now even if none is due.
        """
        now = float(self.data.time)
        elapsed = 0.0 if self.last_sample is None else now - self.last_sample
        if (
            not force
            and self.last_sample is not None
            and elapsed + TIME_TOLERANCE < self.parameters.sample_period
        ):
            return
        upward = -self.model.opt.gravity / self.gravity
        load = 0.0
        objects = set()
        reader = ContactReader(self.model, self.data)
        for contact in reader.contacts():
            on_first = contact.first_geometry in self.load_geometries
            on_second = contact.second_geometry in self.load_geometries
            if on_first == on_second:
                continue
            downward = float(contact.world_force() @ upward) * (1 if on_first else -1)
            load += downward
            if downward > 0:
                objects.add(
                    reader.name(contact.second_body if on_first else contact.first_body)
                )
        self.force = max(0.0, load)
        self.objects = tuple(sorted(objects))
        grams = self.force / self.gravity * GRAMS_PER_KILOGRAM
        if self.last_sample is None:
            self.filtered = grams
        else:
            share = -math.expm1(-elapsed / self.parameters.filter_time_constant)
            self.filtered += share * (grams - self.filtered)
        self.last_sample = now
        self.samples.append((now, grams))
        while (
            len(self.samples) > 1
            and self.samples[1][0] <= now - self.parameters.settling_period
        ):
            self.samples.popleft()

    def take_tare(self) -> None:
        """
        Take the settled load as the display's zero.

        :raises OperationRefused: When the reading has not settled.
        """
        if not self.stable:
            raise OperationRefused(Refusal.UNSETTLED_SCALE)
        self.tare = self.filtered

    def reading(self) -> ScaleReading:
        """
        :return: The display's reading.
        """
        places = self.parameters.decimal_places
        return ScaleReading(
            grams=round(self.filtered - self.tare, places) + 0.0,
            tare=round(self.tare, places),
            stable=self.stable,
            force=self.force,
            objects=list(self.objects),
        )
