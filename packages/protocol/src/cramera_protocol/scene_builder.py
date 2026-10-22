"""
The scene builder's documents: the editable scene drafts, the catalog of resources a
draft places, and the reference point clouds the builder stores.

A draft arranges independent copies of existing models; it never changes the models,
meshes or recordings it refers to.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import Dict, List, Optional

from cramera_protocol.bundle.index import SceneIndexEntry
from cramera_protocol.document import JsonDocument, document_field
from cramera_protocol.geometry import Vector3
from cramera_protocol.version import CURRENT_VERSION, ProtocolVersion

# %% plugin


class SceneBuilderName(StrEnum):
    """
    The names under which the scene builder is installed.
    """

    PLUGIN = "scene-builder"
    """
    The plugin's name, which is also its route segment and its side panel's identity.
    """


class SceneBuilderFile(StrEnum):
    """
    The browser files of the scene builder, relative to its web directory.
    """

    MODULE = "index.js"
    """
    The module the viewer registers, which links to the builder page.
    """

    PAGE = "builder.html"
    """
    The builder page, which needs the whole window.
    """


class SceneBuilderRoute(StrEnum):
    """
    The scene builder's routes, below ``/api/plugins/scene-builder/``.
    """

    CATALOG = "catalog"
    """
    The resources, scenes and drafts the builder offers, with its limits.
    """

    TEMPLATE = "template"
    """
    A recorded scene turned into a new draft; the scene is named by
    :attr:`TemplateParameter.SCENE`.
    """

    DRAFTS = "drafts"
    """
    The saved drafts; a draft record posted here is saved.
    """

    DRAFT = "drafts/"
    """
    The prefix of one saved draft: ``drafts/<identifier>``.
    """

    ASSETS = "assets/"
    """
    The prefix of resource files: ``assets/<root>/<path>``.
    """

    POINT_CLOUDS = "point-clouds/"
    """
    The prefix point cloud files are uploaded to: ``point-clouds/<format>``.
    """

    POINT_CLOUD_SAMPLES = "point-cloud-samples/"
    """
    The prefix of the display samples of point clouds: ``point-cloud-
    samples/<root>/<path>``.
    """


class TemplateParameter(StrEnum):
    """
    The query parameters of :attr:`SceneBuilderRoute.TEMPLATE`.
    """

    SCENE = "scene"
    """
    The name of the bundle the draft starts from.
    """


class SceneBuilderVariable(StrEnum):
    """
    The environment variables the scene builder reads.
    """

    LIBRARY = "CRAMERA_SCENE_BUILDER_LIBRARY"
    """
    Further resource directories, separated like ``PATH``; each is offered as a root
    named after the directory.
    """


# %% resources


class ResourceKind(StrEnum):
    """
    How the browser loads a resource.
    """

    URDF = "urdf"
    """
    A URDF model, with links and joints.
    """

    MESH = "mesh"
    """
    A mesh file of one of the bundle mesh formats.
    """

    POINT_CLOUD = "point-cloud"
    """
    A point cloud, shown as a reference from its display sample.
    """


class ResourceCategory(StrEnum):
    """
    What a resource shows, for the library's filter.
    """

    ROBOT = "robot"
    """
    A robot model.
    """

    ENVIRONMENT = "environment"
    """
    A room, a building or its furniture.
    """

    OBJECT = "object"
    """
    Anything else that can be placed.
    """

    POINT_CLOUD = "point-cloud"
    """
    A scanned reference.
    """


class ReservedResourceRoot(StrEnum):
    """
    Resource roots the scene builder keeps for itself.
    """

    POINT_CLOUDS = "point-clouds"
    """
    The uploaded point clouds.
    """


class NoticeKey(StrEnum):
    """
    The keys of an attribution notice.
    """

    NAME = "name"
    """
    The notice's file name.
    """

    ASSET = "asset"
    """
    The notice's resource identifier.
    """


@dataclass(kw_only=True)
class ResourceNotice(JsonDocument):
    """
    A licence or attribution document found next to a resource or above it.
    """

    name: str = document_field(NoticeKey.NAME)
    """
    The notice's file name.
    """

    asset: str = document_field(NoticeKey.ASSET)
    """
    The notice's resource identifier, ``<root>/<path>``.
    """


class PointCloudFormat(StrEnum):
    """
    The point cloud file formats the scene builder reads.
    """

    PLY = "ply"
    """
    Stanford polygon files holding vertices only.
    """

    PCD = "pcd"
    """
    Point Cloud Library files, ASCII or uncompressed binary.
    """

    def suffix(self) -> str:
        """
        :return: The suffix files of this format carry.
        """
        return f".{self.value}"


class PointCloudEncoding(StrEnum):
    """
    How a point cloud file stores its records.
    """

    ASCII = "ascii"
    """
    One line of numbers per point.
    """

    BINARY = "binary"
    """
    Little-endian records, as PCD writes them.
    """

    BINARY_LITTLE_ENDIAN = "binary_little_endian"
    """
    Little-endian records, as PLY writes them.
    """

    BINARY_BIG_ENDIAN = "binary_big_endian"
    """
    Big-endian records, as PLY writes them.
    """


class PointCloudKey(StrEnum):
    """
    The keys of a point cloud's description.
    """

    FORMAT = "format"
    """
    The file format.
    """

    ENCODING = "encoding"
    """
    How the file stores its records.
    """

    POINT_COUNT = "pointCount"
    """
    How many points the file declares.
    """

    FINITE_POINT_COUNT = "finitePointCount"
    """
    How many points have three finite coordinates.
    """


@dataclass(kw_only=True)
class PointCloudMetadata(JsonDocument):
    """
    What checking a point cloud file found.
    """

    file_format: PointCloudFormat = document_field(PointCloudKey.FORMAT)
    """
    The file format.
    """

    encoding: PointCloudEncoding = document_field(PointCloudKey.ENCODING)
    """
    How the file stores its records.
    """

    point_count: int = document_field(PointCloudKey.POINT_COUNT)
    """
    How many points the file declares.
    """

    finite_point_count: int = document_field(PointCloudKey.FINITE_POINT_COUNT)
    """
    How many points have three finite coordinates; the others are missing measurements.
    """


class ResourceKey(StrEnum):
    """
    The keys of one resource in the catalog.
    """

    IDENTIFIER = "id"
    """
    The resource identifier.
    """

    NAME = "name"
    """
    The name the library shows.
    """

    KIND = "kind"
    """
    How the browser loads the resource.
    """

    CATEGORY = "category"
    """
    What the resource shows.
    """

    NOTICES = "notices"
    """
    The attribution documents of the resource.
    """

    POINT_CLOUD = "pointCloud"
    """
    What checking an uploaded point cloud found.
    """


@dataclass(kw_only=True)
class ResourceDescription(JsonDocument):
    """
    One file a draft can place.
    """

    identifier: str = document_field(ResourceKey.IDENTIFIER)
    """
    The resource identifier, ``<root>/<path>``; the file is served at
    ``assets/<root>/<path>``.
    """

    name: str = document_field(ResourceKey.NAME)
    """
    The name the library shows.
    """

    kind: ResourceKind = document_field(ResourceKey.KIND)
    """
    How the browser loads the resource.
    """

    category: ResourceCategory = document_field(ResourceKey.CATEGORY)
    """
    What the resource shows.
    """

    notices: List[ResourceNotice] = document_field(
        ResourceKey.NOTICES, default_factory=list
    )
    """
    The licence and attribution documents next to the resource or above it.
    """

    point_cloud: Optional[PointCloudMetadata] = document_field(
        ResourceKey.POINT_CLOUD, default=None
    )
    """
    What checking the file found, for an uploaded point cloud.
    """


# %% drafts


class AppearanceKey(StrEnum):
    """
    The keys of how a reference point cloud is shown.
    """

    VISIBLE = "visible"
    """
    Whether the reference is shown.
    """

    LOCKED = "locked"
    """
    Whether the reference keeps its placement and cannot be picked.
    """

    POINT_SIZE = "pointSize"
    """
    The size of each point in metres.
    """

    OPACITY = "opacity"
    """
    How opaque the points are.
    """


DEFAULT_POINT_SIZE = 0.006
"""
The size of a reference's points in metres before a person changes it.
"""

DEFAULT_OPACITY = 0.65
"""
The opacity of a reference's points before a person changes it.
"""


@dataclass(kw_only=True)
class PointCloudAppearance(JsonDocument):
    """
    How a reference point cloud is shown while models are arranged over it.
    """

    visible: bool = document_field(AppearanceKey.VISIBLE, default=True)
    """
    Whether the reference is shown.
    """

    locked: bool = document_field(AppearanceKey.LOCKED, default=True)
    """
    Whether the reference keeps its placement; a locked reference cannot be picked, so
    clicks reach the models arranged over it.
    """

    point_size: float = document_field(
        AppearanceKey.POINT_SIZE, default=DEFAULT_POINT_SIZE
    )
    """
    The size of each point in metres.
    """

    opacity: float = document_field(AppearanceKey.OPACITY, default=DEFAULT_OPACITY)
    """
    How opaque the points are, from transparent at 0 to opaque at 1.
    """


class LinkOffsetKey(StrEnum):
    """
    The keys of a link's offset.
    """

    POSITION = "position"
    """
    The offset's translation.
    """

    ROTATION = "rotation"
    """
    The offset's roll, pitch and yaw.
    """


@dataclass(kw_only=True)
class LinkOffset(JsonDocument):
    """
    A change to where a URDF link sits, in its parent's frame, applied before the link's
    authored transform; removing it restores the authored placement.
    """

    position: Vector3 = document_field(LinkOffsetKey.POSITION)
    """
    The translation in metres.
    """

    rotation: Vector3 = document_field(LinkOffsetKey.ROTATION)
    """
    The roll, pitch and yaw in radians, about the fixed x, y and z axes.
    """


class InstanceKey(StrEnum):
    """
    The keys of one placed model of a draft.
    """

    IDENTIFIER = "id"
    """
    The instance's identity in the draft.
    """

    ASSET = "asset"
    """
    The resource the instance shows.
    """

    NAME = "name"
    """
    The instance's name.
    """

    POSITION = "position"
    """
    Where the instance stands.
    """

    ROTATION = "rotation"
    """
    How the instance is turned.
    """

    SCALE = "scale"
    """
    How the instance is scaled along each axis.
    """

    LINK_OFFSETS = "linkOffsets"
    """
    The links moved away from their authored placement.
    """

    JOINT_POSITIONS = "jointPositions"
    """
    The joint values set for the instance.
    """

    POINT_CLOUD = "pointCloud"
    """
    How a reference point cloud is shown.
    """


UNIT_SCALE = Vector3(1.0, 1.0, 1.0)
"""
The scale of an instance shown at the size of its resource.
"""


@dataclass(kw_only=True)
class DraftInstance(JsonDocument):
    """
    One copy of a resource placed in a draft.
    """

    identifier: str = document_field(InstanceKey.IDENTIFIER)
    """
    The instance's identity, unique in the draft.
    """

    asset: str = document_field(InstanceKey.ASSET)
    """
    The resource identifier of the model the instance shows.
    """

    name: str = document_field(InstanceKey.NAME)
    """
    The instance's name.
    """

    position: Vector3 = document_field(InstanceKey.POSITION)
    """
    The position in the scene in metres, z up.
    """

    rotation: Vector3 = document_field(InstanceKey.ROTATION)
    """
    The roll, pitch and yaw in radians, about the fixed x, y and z axes.
    """

    scale: Vector3 = document_field(InstanceKey.SCALE, default=UNIT_SCALE)
    """
    The factor along each axis; it scales the whole model, articulated links included.
    """

    link_offsets: Dict[str, LinkOffset] = document_field(
        InstanceKey.LINK_OFFSETS, default_factory=dict
    )
    """
    The offset of each moved URDF link, by link name.
    """

    joint_positions: Dict[str, float] = document_field(
        InstanceKey.JOINT_POSITIONS, default_factory=dict
    )
    """
    The value of each set joint, by joint name, in radians or metres.
    """

    point_cloud: Optional[PointCloudAppearance] = document_field(
        InstanceKey.POINT_CLOUD, default=None
    )
    """
    How the instance is shown, for a reference point cloud; None for a model.
    """


class DraftKey(StrEnum):
    """
    The keys of a scene draft.
    """

    FORMAT_VERSION = "formatVersion"
    """
    The protocol version the draft was written with.
    """

    NAME = "name"
    """
    The scene's name.
    """

    INSTANCES = "instances"
    """
    The placed models.
    """

    SOURCE_SCENE = "sourceScene"
    """
    The bundle the draft started from.
    """

    NOTICES = "notices"
    """
    The attribution documents of every placed resource.
    """


@dataclass(kw_only=True)
class SceneDraft(JsonDocument):
    """
    An editable arrangement of resources: a layout for an editor, neither a plan nor a
    generated URDF.
    """

    name: str = document_field(DraftKey.NAME)
    """
    The scene's name.
    """

    format_version: ProtocolVersion = document_field(
        DraftKey.FORMAT_VERSION, default=CURRENT_VERSION
    )
    """
    The protocol version the draft was written with.
    """

    instances: List[DraftInstance] = document_field(
        DraftKey.INSTANCES, default_factory=list
    )
    """
    The placed models, in the order they were added.
    """

    source_scene: Optional[str] = document_field(DraftKey.SOURCE_SCENE, default=None)
    """
    The name of the bundle the draft started from, if it started from one.
    """

    notices: List[ResourceNotice] = document_field(
        DraftKey.NOTICES, default_factory=list
    )
    """
    The licence and attribution documents of the placed resources.
    """

    def __post_init__(self) -> None:
        self.format_version.require_readable_by(CURRENT_VERSION)


class DraftSummaryKey(StrEnum):
    """
    The keys of a saved draft in the draft list.
    """

    IDENTIFIER = "id"
    """
    The draft's identity.
    """

    NAME = "name"
    """
    The scene's name.
    """

    UPDATED_AT = "updatedAt"
    """
    When the draft was last saved.
    """


@dataclass(kw_only=True)
class DraftSummary(JsonDocument):
    """
    A saved draft as the draft list offers it.
    """

    identifier: str = document_field(DraftSummaryKey.IDENTIFIER)
    """
    The draft's identity.
    """

    name: str = document_field(DraftSummaryKey.NAME)
    """
    The scene's name.
    """

    updated_at: str = document_field(DraftSummaryKey.UPDATED_AT)
    """
    When the draft was last saved, as an ISO 8601 date and time in UTC.
    """


class DraftRecordKey(StrEnum):
    """
    The keys of a draft with its identity.
    """

    IDENTIFIER = "id"
    """
    The draft's identity.
    """

    DOCUMENT = "document"
    """
    The draft.
    """


@dataclass(kw_only=True)
class DraftRecord(JsonDocument):
    """
    A draft with its identity: what is posted to be saved and what a saved draft is
    answered with.
    """

    document: SceneDraft = document_field(DraftRecordKey.DOCUMENT)
    """
    The draft.
    """

    identifier: Optional[str] = document_field(DraftRecordKey.IDENTIFIER, default=None)
    """
    The draft's identity; None in a request to save a new draft.
    """


class DraftListKey(StrEnum):
    """
    The keys of the draft list.
    """

    DRAFTS = "drafts"
    """
    The saved drafts.
    """


@dataclass(kw_only=True)
class DraftList(JsonDocument):
    """
    The saved drafts.
    """

    drafts: List[DraftSummary] = document_field(
        DraftListKey.DRAFTS, default_factory=list
    )
    """
    The saved drafts, sorted by identity.
    """


# %% limits


class LimitsKey(StrEnum):
    """
    The keys of the scene builder's limits.
    """

    MAXIMUM_INSTANCES = "maximumInstances"
    """
    How many instances a draft holds at most.
    """

    MAXIMUM_DOCUMENT_BYTES = "maximumDocumentBytes"
    """
    How large a draft's JSON is at most.
    """

    MAXIMUM_NAME_LENGTH = "maximumNameLength"
    """
    How long a name is at most.
    """

    MAXIMUM_IDENTIFIER_LENGTH = "maximumIdentifierLength"
    """
    How long an instance or draft identity is at most.
    """

    MAXIMUM_REFERENCE_LENGTH = "maximumReferenceLength"
    """
    How long a resource identifier, link name or joint name is at most.
    """

    MAXIMUM_COORDINATE = "maximumCoordinate"
    """
    The largest magnitude of a coordinate, angle or joint value.
    """

    MAXIMUM_SCALE = "maximumScale"
    """
    The largest scale factor.
    """

    MINIMUM_POINT_SIZE = "minimumPointSize"
    """
    The smallest point size of a reference.
    """

    MAXIMUM_POINT_SIZE = "maximumPointSize"
    """
    The largest point size of a reference.
    """

    MINIMUM_OPACITY = "minimumOpacity"
    """
    The lowest opacity of a reference.
    """

    MAXIMUM_OPACITY = "maximumOpacity"
    """
    The highest opacity of a reference.
    """

    MAXIMUM_POINT_CLOUD_BYTES = "maximumPointCloudBytes"
    """
    How large an uploaded point cloud file is at most.
    """

    MAXIMUM_POINTS = "maximumPoints"
    """
    How many points an uploaded point cloud declares at most.
    """

    MAXIMUM_SAMPLE_POINTS = "maximumSamplePoints"
    """
    How many points a display sample holds at most.
    """


MEBIBYTE = 1024 * 1024
"""
The number of bytes in a mebibyte.
"""


@dataclass(kw_only=True)
class SceneBuilderLimits(JsonDocument):
    """
    The bounds every draft and upload stays within; the browser checks against the same
    values the server enforces.
    """

    maximum_instances: int = document_field(LimitsKey.MAXIMUM_INSTANCES, default=500)
    """
    How many instances a draft holds at most.
    """

    maximum_document_bytes: int = document_field(
        LimitsKey.MAXIMUM_DOCUMENT_BYTES, default=2 * MEBIBYTE
    )
    """
    How large a draft's JSON is at most, in bytes.
    """

    maximum_name_length: int = document_field(
        LimitsKey.MAXIMUM_NAME_LENGTH, default=160
    )
    """
    How many characters a scene, instance or notice name has at most.
    """

    maximum_identifier_length: int = document_field(
        LimitsKey.MAXIMUM_IDENTIFIER_LENGTH, default=96
    )
    """
    How many characters an instance or draft identity has at most.
    """

    maximum_reference_length: int = document_field(
        LimitsKey.MAXIMUM_REFERENCE_LENGTH, default=2048
    )
    """
    How many characters a resource identifier, bundle name, link name or joint name has
    at most.
    """

    maximum_coordinate: float = document_field(
        LimitsKey.MAXIMUM_COORDINATE, default=10000.0
    )
    """
    The largest magnitude of a coordinate in metres, an angle in radians or a joint
    value.
    """

    maximum_scale: float = document_field(LimitsKey.MAXIMUM_SCALE, default=1000.0)
    """
    The largest scale factor; scale factors are positive.
    """

    minimum_point_size: float = document_field(
        LimitsKey.MINIMUM_POINT_SIZE, default=0.0001
    )
    """
    The smallest point size of a reference in metres.
    """

    maximum_point_size: float = document_field(
        LimitsKey.MAXIMUM_POINT_SIZE, default=0.1
    )
    """
    The largest point size of a reference in metres.
    """

    minimum_opacity: float = document_field(LimitsKey.MINIMUM_OPACITY, default=0.05)
    """
    The lowest opacity of a reference, so a reference never disappears by its opacity.
    """

    maximum_opacity: float = document_field(LimitsKey.MAXIMUM_OPACITY, default=1.0)
    """
    The highest opacity of a reference.
    """

    maximum_point_cloud_bytes: int = document_field(
        LimitsKey.MAXIMUM_POINT_CLOUD_BYTES, default=64 * MEBIBYTE
    )
    """
    How large an uploaded point cloud file is at most, in bytes.
    """

    maximum_points: int = document_field(LimitsKey.MAXIMUM_POINTS, default=2_000_000)
    """
    How many points an uploaded point cloud declares at most.
    """

    maximum_sample_points: int = document_field(
        LimitsKey.MAXIMUM_SAMPLE_POINTS, default=250_000
    )
    """
    How many points a display sample holds at most.
    """


# %% catalog


class CatalogKey(StrEnum):
    """
    The keys of the scene builder's catalog.
    """

    RESOURCES = "resources"
    """
    The files a draft can place.
    """

    SCENES = "scenes"
    """
    The bundles a draft can start from.
    """

    DRAFTS = "drafts"
    """
    The saved drafts.
    """

    LIMITS = "limits"
    """
    The bounds drafts and uploads stay within.
    """

    DEFAULT_APPEARANCE = "defaultAppearance"
    """
    How a newly placed reference point cloud is shown.
    """


@dataclass(kw_only=True)
class SceneBuilderCatalog(JsonDocument):
    """
    What the scene builder offers.
    """

    resources: List[ResourceDescription] = document_field(
        CatalogKey.RESOURCES, default_factory=list
    )
    """
    The files a draft can place, sorted by identifier.
    """

    scenes: List[SceneIndexEntry] = document_field(
        CatalogKey.SCENES, default_factory=list
    )
    """
    The bundles a draft can start from, as the viewer's scene index lists them.
    """

    drafts: List[DraftSummary] = document_field(CatalogKey.DRAFTS, default_factory=list)
    """
    The saved drafts.
    """

    limits: SceneBuilderLimits = document_field(
        CatalogKey.LIMITS, default_factory=SceneBuilderLimits
    )
    """
    The bounds drafts and uploads stay within.
    """

    default_appearance: PointCloudAppearance = document_field(
        CatalogKey.DEFAULT_APPEARANCE, default_factory=PointCloudAppearance
    )
    """
    How a newly placed reference point cloud is shown.
    """
