"""
Fixtures of the workshop's CRAM tests: the workshop as a CRAM world, with and without a
PR2.
"""

from __future__ import annotations

import pytest

from cramera.locations import DataLocations
from cramera_workshop.robot.demos import (
    ScrewAssemblyDemo,
    ScrewInsertionDemo,
    WorkshopDemoName,
)
from cramera_workshop.robot.world import RobotStart, WorkshopEnvironment
from coraplex.datastructures.dataclasses import Context
from semantic_digital_twin.world import World


@pytest.fixture(scope="session")
def environment(bundle) -> WorkshopEnvironment:
    """
    :return: The packaged workshop as a CRAM environment.
    """
    return WorkshopEnvironment(bundle=bundle)


@pytest.fixture
def workshop_world(environment) -> World:
    """
    :return: A new world holding only the workshop.
    """
    return environment.create_world()


@pytest.fixture(scope="session")
def assembly_demo(bundle, tmp_path_factory) -> ScrewAssemblyDemo:
    """
    :return: The assembly demo, saving below a temporary data directory.
    """
    return ScrewAssemblyDemo.of_bundle(
        bundle,
        WorkshopDemoName.ASSEMBLY,
        "PR2: assembly",
        locations=DataLocations(
            data=tmp_path_factory.mktemp("assembly"), shared_scenes=None
        ),
    )


@pytest.fixture(scope="session")
def assembly_context(assembly_demo) -> Context:
    """
    :return: The assembly demo's world and PR2, shared by tests that only read them.
    """
    return assembly_demo.build_context(assembly_demo.build_world())


@pytest.fixture
def insertion_demo(bundle, tmp_path) -> ScrewInsertionDemo:
    """
    :return: The insertion demo, saving below a temporary data directory.
    """
    return ScrewInsertionDemo.of_bundle(
        bundle,
        WorkshopDemoName.INSERTION,
        "PR2: insertion",
        locations=DataLocations(data=tmp_path, shared_scenes=None),
    )


@pytest.fixture
def bench_start() -> RobotStart:
    """
    :return: Where the PR2 stands at the assembly station.
    """
    return RobotStart(x=0.16, y=-0.86)
