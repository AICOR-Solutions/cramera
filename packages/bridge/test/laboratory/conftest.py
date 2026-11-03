"""
The laboratory asset bundle used by the bridge's native integration tests, and how the
tests expand a plan without running it.
"""

from pathlib import Path

import pytest
from typing_extensions import Callable

from cramera_bridge.performing import TaskContext
from cramph.node import StatechartNode
from cramph.statechart import Statechart


@pytest.fixture(scope="module")
def laboratory_bundle() -> Path:
    """
    :return: The small laboratory bundle, independent of installing its plugin.
    """
    return (
        Path(__file__).resolve().parents[3]
        / "plugins/laboratory/src/cramera_laboratory/resources/aicor_medical_lab"
    )


def expanded(plan: StatechartNode, context: TaskContext) -> Statechart:
    """
    :param plan: A plan's top-level node.
    :param context: The world and the robot the plan is built for.
    :return: A statechart holding the plan, which expanded every action of it, neither
        compiled nor run.
    """
    statechart = Statechart(context=context.take_statechart_context())
    statechart.add_node(plan)
    return statechart


@pytest.fixture(scope="module")
def expand() -> Callable[[StatechartNode, TaskContext], Statechart]:
    """
    :return: Expands a plan in a statechart of its own without running it, see
        :func:`expanded`.
    """
    return expanded
