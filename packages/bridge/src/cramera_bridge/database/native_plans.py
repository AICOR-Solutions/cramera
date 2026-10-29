"""
The plans a run performed, stored in the bundle's plan database by CRAM's own database
mapping, with every parameter of every step as CRAM holds it.

CRAM generates its mapping into ``ormatic_interface`` modules, which a workspace builds
with ``scripts/regenerate_all_orm.py``; where they have not been built, the run keeps
what :mod:`cramera_bridge.database.runs` stores of it.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.orm import Session
from typing_extensions import List

from krrood.ormatic.data_access_objects.helper import to_dao
from krrood.ormatic.utils import create_engine

from cramera_bridge.database.runs import PlanDatabase, RecordedPlan, RunTable
from cramera_bridge.live.plan import PerformedPlan

# %% CRAM's mapping


class GeneratedMapping(StrEnum):
    """
    The modules CRAM generates its database mapping into.
    """

    PLANS = "coraplex.orm.ormatic_interface"
    """
    The mapping of coraplex's plans, which includes everything a plan refers to.
    """


# %% storing


@dataclass(frozen=True)
class NativePlans:
    """
    The plans of one run, to be stored in a bundle's plan database.
    """

    database: PlanDatabase
    """
    The database the run is kept in.
    """

    run: int
    """
    The run's number in the database.
    """

    @staticmethod
    def mapping_is_built() -> bool:
        """
        :return: Whether CRAM's mapping of plans has been generated in this workspace.
        """
        return importlib.util.find_spec(GeneratedMapping.PLANS) is not None

    def store(self, plans: List[PerformedPlan]) -> None:
        """
        Store each plan with CRAM's mapping and link it to the run; without a generated
        mapping nothing is stored and a warning names how to build it.

        The database is opened through krrood's engine, whose JSON serializer writes the
        values CRAM's mapping keeps as JSON.

        :param plans: The plans the run performed, in the order each began.
        """
        if not self.mapping_is_built():
            logging.getLogger(__name__).warning(
                "CRAM's database mapping %s is not built, so the run's plans are kept "
                "only as recorded steps; build it with scripts/regenerate_all_orm.py "
                "in the CRAM workspace.",
                GeneratedMapping.PLANS.value,
            )
            return
        mapping = importlib.import_module(GeneratedMapping.PLANS)
        engine = create_engine(f"sqlite:///{self.database.path}")
        RunTable.metadata.create_all(engine)
        mapping.Base.metadata.create_all(engine)
        with Session(engine) as session, session.begin():
            for performed in plans:
                stored = to_dao(performed.plan)
                session.add(stored)
                session.flush()
                session.add(
                    RecordedPlan(
                        run_identifier=self.run,
                        number=performed.number,
                        robot=performed.robot,
                        stored_plan=stored.database_id,
                    )
                )
