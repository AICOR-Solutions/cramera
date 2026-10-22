"""
The motion statecharts of a recorded run, ``statecharts.json``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import List, Optional

from cramera_protocol.document import JsonDocument, document_field

# %% structure


class ChartNodeKey(StrEnum):
    """
    The keys of one node of a motion statechart.
    """

    IDENTIFIER = "id"
    """
    The node's identifier within its chart.
    """

    NAME = "name"
    """
    The node's name.
    """

    CLASS_NAME = "class_name"
    """
    The class of the node in CRAM.
    """

    PARENT = "parent"
    """
    The identifier of the node's parent.
    """


@dataclass(kw_only=True)
class ChartNode(JsonDocument):
    """
    One node of a motion statechart.
    """

    identifier: str = document_field(ChartNodeKey.IDENTIFIER)
    """
    The node's identifier within its chart.
    """

    name: str = document_field(ChartNodeKey.NAME)
    """
    The node's name.
    """

    class_name: str = document_field(ChartNodeKey.CLASS_NAME)
    """
    The class of the node in CRAM.
    """

    parent: Optional[str] = document_field(ChartNodeKey.PARENT, default=None)
    """
    The identifier of the node's parent, or None for a top-level node.
    """


class ChartEdgeKey(StrEnum):
    """
    The keys of one transition of a motion statechart.
    """

    SOURCE = "from"
    """
    The node the transition starts at.
    """

    DESTINATION = "to"
    """
    The node the transition leads to.
    """

    KIND = "kind"
    """
    The kind of the transition.
    """


@dataclass(kw_only=True)
class ChartEdge(JsonDocument):
    """
    One transition of a motion statechart.
    """

    source: str = document_field(ChartEdgeKey.SOURCE)
    """
    The identifier of the node the transition starts at.
    """

    destination: str = document_field(ChartEdgeKey.DESTINATION)
    """
    The identifier of the node the transition leads to.
    """

    kind: str = document_field(ChartEdgeKey.KIND)
    """
    The name of the native transition kind.
    """


class ChartKey(StrEnum):
    """
    The keys of one motion statechart.
    """

    SIGNATURE = "signature"
    """
    The chart's identity.
    """

    TITLE = "title"
    """
    The chart's title.
    """

    NODES = "nodes"
    """
    The chart's nodes.
    """

    EDGES = "edges"
    """
    The chart's transitions.
    """


@dataclass(kw_only=True)
class Chart(JsonDocument):
    """
    One motion statechart a run went through.
    """

    signature: str = document_field(ChartKey.SIGNATURE)
    """
    The chart's identity, the same for every run of the same chart.
    """

    title: str = document_field(ChartKey.TITLE)
    """
    The chart's title.
    """

    nodes: List[ChartNode] = document_field(ChartKey.NODES, default_factory=list)
    """
    The chart's nodes, in the order :attr:`Moment.life_cycles` lists their states.
    """

    edges: List[ChartEdge] = document_field(ChartKey.EDGES, default_factory=list)
    """
    The chart's transitions.
    """


# %% states over time


class MomentKey(StrEnum):
    """
    The keys of one state of a chart.
    """

    CHART = "chart"
    """
    The position of the chart in :attr:`Statecharts.charts`.
    """

    LIFE_CYCLES = "lifeCycles"
    """
    The life-cycle state of each node.
    """

    OBSERVATIONS = "observations"
    """
    The observation state of each node.
    """


@dataclass(kw_only=True)
class Moment(JsonDocument):
    """
    The state of every node of one chart at one point of the run.
    """

    chart: int = document_field(MomentKey.CHART)
    """
    The position of the chart in :attr:`Statecharts.charts`.
    """

    life_cycles: List[str] = document_field(MomentKey.LIFE_CYCLES)
    """
    The name of each node's native life-cycle value.
    """

    observations: List[str] = document_field(MomentKey.OBSERVATIONS)
    """
    The name of each node's native observation value.
    """


class StatechartsKey(StrEnum):
    """
    The keys of ``statecharts.json``.
    """

    CHARTS = "charts"
    """
    The charts of the run.
    """

    MOMENTS = "moments"
    """
    The distinct chart states of the run.
    """

    FRAMES = "frames"
    """
    The moment shown at each trajectory frame.
    """


@dataclass(kw_only=True)
class Statecharts(JsonDocument):
    """
    The content of ``statecharts.json``.
    """

    charts: List[Chart] = document_field(StatechartsKey.CHARTS, default_factory=list)
    """
    The charts of the run.
    """

    moments: List[Moment] = document_field(StatechartsKey.MOMENTS, default_factory=list)
    """
    The distinct chart states of the run.
    """

    frames: List[int] = document_field(StatechartsKey.FRAMES, default_factory=list)
    """
    The position in :attr:`moments` shown at each trajectory frame, or -1 for a frame
    without a chart state.
    """
