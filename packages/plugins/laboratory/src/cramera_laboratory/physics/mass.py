"""
The weight of the liquid in the vessels: each vessel's mass and inertia grow with the
liquid it holds, so the scale, the centrifuge's balance and a hand feel it.

The liquid's mass sits at the vessel's own centre of mass and scales its inertia; how
the liquid moves inside the vessel does not push the vessel.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import mujoco
import numpy as np
from typing_extensions import Dict, Mapping

from cramera_laboratory.liquid import LaboratoryLiquid

GRAMS_PER_KILOGRAM = 1000.0
"""
How many grams a kilogram has.
"""

WATER_DENSITY = 1.0
"""
The density every liquid is taken to have, in grams per millilitre.
"""

# %% mass


@dataclass(frozen=True)
class DryVessel:
    """
    A vessel's own mass and inertia, without liquid.
    """

    body: int
    """
    The vessel's body.
    """

    mass: float
    """
    Its mass, in kilograms.
    """

    inertia: np.ndarray
    """
    Its principal moments of inertia, in kilogram square metres.
    """


@dataclass
class LiquidMass:
    """
    Keeps each vessel's simulated mass at its glass plus its liquid.
    """

    model: mujoco.MjModel
    """
    The compiled model, whose body masses change.
    """

    bodies: Mapping[str, int]
    """
    Each vessel's body, by the vessel's key.
    """

    density: float = WATER_DENSITY
    """
    The liquid's density, in grams per millilitre.
    """

    dry: Dict[str, DryVessel] = field(init=False)
    """
    Each vessel's mass and inertia without liquid.
    """

    scratch: mujoco.MjData = field(init=False, repr=False)
    """
    A state MuJoCo recomputes the model's constants in, apart from the simulation's.
    """

    def __post_init__(self) -> None:
        self.dry = {
            key: DryVessel(
                body=body,
                mass=float(self.model.body_mass[body]),
                inertia=self.model.body_inertia[body].copy(),
            )
            for key, body in self.bodies.items()
        }
        self.scratch = mujoco.MjData(self.model)

    def synchronize(self, liquid: LaboratoryLiquid) -> bool:
        """
        Set each vessel's mass to its glass plus its liquid.

        :param liquid: The liquid model.
        :return: Whether any mass changed, so the simulation must recompute positions.
        """
        changed = False
        for key, dry in self.dry.items():
            mass = (
                dry.mass
                + liquid.vessels[key].volume * self.density / GRAMS_PER_KILOGRAM
            )
            if self.model.body_mass[dry.body] == mass:
                continue
            self.model.body_mass[dry.body] = mass
            self.model.body_inertia[dry.body] = dry.inertia * (mass / dry.mass)
            changed = True
        if changed:
            mujoco.mj_setConst(self.model, self.scratch)
        return changed
