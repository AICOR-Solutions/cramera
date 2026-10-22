"""
The protocol's names as an ES module, so the browser reads the same definitions as
Python.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum

from typing_extensions import List, Tuple, Type

from cramera_protocol.bundle.files import BundleFile, ScenesDirectoryFile
from cramera_protocol.bundle.index import IndexEntryKey, IndexKey, ReservedSceneName
from cramera_protocol.bundle.lighting import LightingKey, LightKey
from cramera_protocol.bundle.scene import (
    CameraKey,
    DetectedEventKey,
    ModelKey,
    ObjectKey,
    PartKey,
    PartRole,
    PartSide,
    PlaceTargetKey,
    PlanNodeKey,
    RenderingKey,
    RobotKey,
    SceneKey,
    SegmentKey,
)
from cramera_protocol.bundle.statecharts import (
    ChartEdgeKey,
    ChartKey,
    ChartNodeKey,
    MomentKey,
    StatechartsKey,
)
from cramera_protocol.bundle.trajectory import TrajectoryKey
from cramera_protocol.events import PageState, PageStateAttribute, ViewerEvent
from cramera_protocol.geometry import RectangleKey
from cramera_protocol.live import Capability, LiveInfoKey, LiveRoute
from cramera_protocol.live_messages import (
    AcknowledgementKey,
    ConnectionKind,
    ConnectionStateKey,
    ConstraintActivation,
    ConstraintMonitorType,
    ConstraintObservationKey,
    ConstraintOperation,
    ConstraintRequestKey,
    JointRequestKey,
    LiveChartNodeKey,
    LiveObjectKey,
    LiveParameter,
    LivePlanKey,
    LivePlanNodeKey,
    LiveSceneKey,
    LiveStateKey,
    LiveStatechartKey,
    MarkerKey,
    MarkerKind,
    MarkerOverlayKey,
    MarkerTopicRequestKey,
    MarkerTopicsKey,
    MonitorSpecificationKey,
    MoveRequestKey,
    ObjectCatalogKey,
    ObjectPosesKey,
    PlanNodeReferenceKey,
    RecordingSaveRequestKey,
    RecordingState,
    RecordingStatusKey,
    RobotInstanceKey,
    RobotRosterKey,
    RobotSelectionKey,
    SavedSceneKey,
    SceneDestination,
    ShapeKey,
    ShapeKind,
    SurfaceKey,
    SurfacesKey,
    TeleoperationRequestKey,
    TransformFreshness,
    TransformGraphKey,
    TransformWriter,
)
from cramera_protocol.questions import (
    AnswerColumn,
    AnswerKind,
    GraphDetailKey,
    GraphEdgeKey,
    GraphEdgeKind,
    GraphLayout,
    GraphNodeKey,
    GraphViewKey,
    GraphViewName,
    LegendEntryKey,
    PresetCatalogKey,
    PresetKey,
    QueryAnswerKey,
    QueryRequestKey,
    QueryScope,
    QuestionMatchKey,
    QuestionRequestKey,
    QuestionsParameter,
    QuestionsRoute,
    ReplayWindowKey,
    ScopeDescriptionKey,
    VerbalizationKey,
    VocabularyEntryKey,
    VocabularyKey,
    VocabularyKind,
)
from cramera_protocol.version import CURRENT_VERSION
from cramera_protocol.viewer import PluginKey, ViewerInfoKey, ViewerRoute

# %% module


BROWSER_ENUMERATIONS: Tuple[Type[StrEnum], ...] = (
    BundleFile,
    ScenesDirectoryFile,
    ReservedSceneName,
    IndexKey,
    IndexEntryKey,
    SceneKey,
    ModelKey,
    RobotKey,
    PartKey,
    PartRole,
    PartSide,
    ObjectKey,
    SegmentKey,
    PlanNodeKey,
    DetectedEventKey,
    PlaceTargetKey,
    CameraKey,
    RenderingKey,
    RectangleKey,
    TrajectoryKey,
    StatechartsKey,
    ChartKey,
    ChartNodeKey,
    ChartEdgeKey,
    MomentKey,
    LightingKey,
    LightKey,
    LiveRoute,
    LiveInfoKey,
    Capability,
    LiveParameter,
    LiveStateKey,
    LivePlanKey,
    LivePlanNodeKey,
    ConstraintObservationKey,
    LiveStatechartKey,
    LiveChartNodeKey,
    TransformGraphKey,
    ConnectionStateKey,
    ConnectionKind,
    TransformWriter,
    TransformFreshness,
    MarkerOverlayKey,
    MarkerKey,
    MarkerKind,
    MarkerTopicsKey,
    MarkerTopicRequestKey,
    ObjectCatalogKey,
    LiveObjectKey,
    ShapeKey,
    ShapeKind,
    ObjectPosesKey,
    SurfacesKey,
    SurfaceKey,
    LiveSceneKey,
    RobotRosterKey,
    RobotInstanceKey,
    RobotSelectionKey,
    RecordingState,
    RecordingStatusKey,
    RecordingSaveRequestKey,
    SceneDestination,
    SavedSceneKey,
    AcknowledgementKey,
    MoveRequestKey,
    JointRequestKey,
    TeleoperationRequestKey,
    ConstraintRequestKey,
    ConstraintOperation,
    ConstraintActivation,
    ConstraintMonitorType,
    PlanNodeReferenceKey,
    MonitorSpecificationKey,
    QueryScope,
    QuestionsRoute,
    QuestionsParameter,
    QueryRequestKey,
    QuestionRequestKey,
    VerbalizationKey,
    ReplayWindowKey,
    AnswerKind,
    AnswerColumn,
    QueryAnswerKey,
    PresetKey,
    ScopeDescriptionKey,
    PresetCatalogKey,
    QuestionMatchKey,
    VocabularyKind,
    VocabularyEntryKey,
    VocabularyKey,
    GraphViewName,
    GraphLayout,
    GraphEdgeKind,
    GraphNodeKey,
    GraphEdgeKey,
    GraphDetailKey,
    LegendEntryKey,
    GraphViewKey,
    ViewerRoute,
    ViewerInfoKey,
    PluginKey,
    ViewerEvent,
    PageStateAttribute,
    PageState,
)
"""
The enumerations the browser application reads.
"""


@dataclass
class BrowserModule:
    """
    An ES module exporting enumerations as frozen objects of their members.
    """

    enumerations: Tuple[Type[StrEnum], ...] = BROWSER_ENUMERATIONS
    """
    The enumerations the module exports, each under its class name.
    """

    header: List[str] = field(
        default_factory=lambda: [
            "// Generated by cramera_protocol.browser from the Python protocol.",
            "// Edit the protocol package, not this file.",
        ]
    )
    """
    The comment lines the module starts with.
    """

    def source(self) -> str:
        """
        :return: The module's JavaScript source.
        """
        lines = list(self.header)
        lines.append(
            f"export const PROTOCOL_VERSION = {json.dumps(CURRENT_VERSION.to_json())};"
        )
        for enumeration in self.enumerations:
            members = {member.name: member.value for member in enumeration}
            lines.append(
                f"export const {enumeration.__name__} = Object.freeze("
                f"{json.dumps(members, indent=2)});"
            )
        return "\n".join(lines) + "\n"


def main() -> None:
    """
    Print the module, for builds that serve the browser application statically.
    """
    print(BrowserModule().source(), end="")


if __name__ == "__main__":
    main()
