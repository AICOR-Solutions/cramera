"""
The protocol's names as an ES module, so the browser reads the same definitions as
Python.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum

from typing_extensions import List, Tuple, Type

from cramera_protocol.bundle.files import BundleFile, MeshFormat, ScenesDirectoryFile
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
    PerceptionImageKey,
    PerceptionImageSource,
    PlaceTargetKey,
    PlanNodeKey,
    PlanNodeKind,
    LegacyPlanNodeKind,
    PlanConstraintKey,
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
from cramera_protocol.events import (
    PageReportKey,
    PageState,
    PageStateAttribute,
    SelectionKey,
    SelectionKind,
    ViewerEvent,
)
from cramera_protocol.geometry import RectangleKey
from cramera_protocol.live import Capability, LiveInfoKey, LiveRoute
from cramera_protocol.offline import (
    AssetProblemKey,
    AssetProblemKind,
    BundleCheckKey,
    ChapterKey,
    OfflineParameter,
    OfflineRoute,
    StoryboardKey,
)
from cramera_protocol.plan_builder import (
    PlanBuilderName,
    PlanBuilderFile,
    PlanBuilderRoute,
    PlanBuilderPageParameter,
    PlacementMode,
    DestinationKey,
    StepConstraintKey,
    ConstraintTextKey,
    RuleValue,
    ConstraintRuleKey,
    PlanStepKey,
    PlannedRobotKey,
    PlannedObjectKey,
    PlanKey,
    PlanSummaryKey,
    PlanRecordKey,
    PlanListKey,
    PlanBuilderLimitsKey,
    ActionFieldKind,
    ActionGroup,
    ActionFieldKey,
    HiddenActionFieldKey,
    ActionSchemaKey,
    FailedActionModuleKey,
    ActionCatalogKey,
    RobotModelKey,
    ObjectModelKey,
    PlanBuilderCatalogKey,
    DemoSourceKey,
    SavedDemoKey,
    RunMode,
    RunState,
    RunRequestKey,
    RunStatusKey,
)
from cramera_protocol.plugins import PluginName
from cramera_protocol.scene_builder import (
    AppearanceKey,
    BuilderPageParameter,
    CatalogKey,
    DraftKey,
    DraftListKey,
    DraftRecordKey,
    DraftSummaryKey,
    InstanceKey,
    LimitsKey,
    LinkOffsetKey,
    NoticeKey,
    PointCloudFormat,
    PrimitiveShape,
    PointCloudKey,
    ReservedResourceRoot,
    ResourceCategory,
    ResourceKey,
    ResourceKind,
    SceneBuilderFile,
    SceneBuilderName,
    SceneBuilderRoute,
    TemplateParameter,
)
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
    MonitorParameterKey,
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
    RecordedAnswerKey,
    RecordedAnswersKey,
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
from cramera_protocol.viewer import (
    BuildKey,
    ErrorKey,
    NavigationGroup,
    NavigationKey,
    PluginKey,
    Serving,
    ViewerInfoKey,
    ViewerRoute,
)
from cramera_protocol.page import PageLayout, PageParameter, PageStorageKey, Theme
from cramera_protocol.rights import AssetRightsKey

# %% module


BROWSER_ENUMERATIONS: Tuple[Type[StrEnum], ...] = (
    BundleFile,
    ScenesDirectoryFile,
    MeshFormat,
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
    PlanNodeKind,
    LegacyPlanNodeKind,
    PlanConstraintKey,
    PerceptionImageKey,
    PerceptionImageSource,
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
    MonitorParameterKey,
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
    RecordedAnswersKey,
    RecordedAnswerKey,
    ViewerRoute,
    ViewerInfoKey,
    BuildKey,
    ErrorKey,
    PluginKey,
    NavigationKey,
    NavigationGroup,
    Serving,
    PageParameter,
    PageLayout,
    Theme,
    PageStorageKey,
    ViewerEvent,
    PageStateAttribute,
    PageState,
    PageReportKey,
    SelectionKind,
    SelectionKey,
    PluginName,
    OfflineRoute,
    OfflineParameter,
    StoryboardKey,
    ChapterKey,
    BundleCheckKey,
    AssetProblemKey,
    AssetProblemKind,
    SceneBuilderName,
    SceneBuilderFile,
    SceneBuilderRoute,
    TemplateParameter,
    BuilderPageParameter,
    ResourceKind,
    ResourceCategory,
    ReservedResourceRoot,
    NoticeKey,
    PointCloudFormat,
    PrimitiveShape,
    PointCloudKey,
    ResourceKey,
    AppearanceKey,
    LinkOffsetKey,
    InstanceKey,
    DraftKey,
    DraftSummaryKey,
    DraftRecordKey,
    DraftListKey,
    LimitsKey,
    CatalogKey,
    AssetRightsKey,
    PlanBuilderName,
    PlanBuilderFile,
    PlanBuilderRoute,
    PlanBuilderPageParameter,
    PlacementMode,
    DestinationKey,
    StepConstraintKey,
    ConstraintTextKey,
    RuleValue,
    ConstraintRuleKey,
    PlanStepKey,
    PlannedRobotKey,
    PlannedObjectKey,
    PlanKey,
    PlanSummaryKey,
    PlanRecordKey,
    PlanListKey,
    PlanBuilderLimitsKey,
    ActionFieldKind,
    ActionGroup,
    ActionFieldKey,
    HiddenActionFieldKey,
    ActionSchemaKey,
    FailedActionModuleKey,
    ActionCatalogKey,
    RobotModelKey,
    ObjectModelKey,
    PlanBuilderCatalogKey,
    DemoSourceKey,
    SavedDemoKey,
    RunMode,
    RunState,
    RunRequestKey,
    RunStatusKey,
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
