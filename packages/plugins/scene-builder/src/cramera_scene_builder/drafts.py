"""
Checking scene drafts against the builder's limits, completing their notices, and
keeping them in the draft directory, apart from every source file.
"""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

from typing_extensions import Dict, List, Sized, Union

from cramera_protocol.exceptions import ProtocolError
from cramera_protocol.geometry import Vector3
from cramera_protocol.scene_builder import (
    AppearanceKey,
    DraftInstance,
    DraftKey,
    DraftRecord,
    DraftSummary,
    InstanceKey,
    LinkOffset,
    LinkOffsetKey,
    NoticeKey,
    PointCloudAppearance,
    ResourceKind,
    ResourceNotice,
    SceneBuilderLimits,
    SceneDraft,
)
from cramera_scene_builder.exceptions import (
    DraftTooLarge,
    DuplicateInstance,
    InvalidDraftIdentifier,
    InvalidDraftText,
    NonPositiveScale,
    NotAPointCloud,
    TooManyEntries,
    UnknownDraft,
    UnreadableDraft,
    UnsafeStoragePath,
    ValueOutOfRange,
)
from cramera_scene_builder.resources import ResourceIdentifier, ResourceLibrary

IDENTITY_CHARACTERS = re.compile(r"[A-Za-z0-9_-]+")
"""
The characters an instance or draft identity is made of.
"""

CONTROL_CHARACTER_LIMIT = 32
"""
Characters below this code point are control characters, which texts must not hold.
"""

LOCATION_SEPARATOR = "."
"""
Joins the keys of a location in a draft, for error messages.
"""


class DraftFile(StrEnum):
    """
    The files of the draft directory.
    """

    SUFFIX = ".json"
    """
    The suffix of a saved draft, named after its identity.
    """

    TEMPORARY_PREFIX = ".draft-"
    """
    The prefix of a draft being written, which is hidden until it is complete.
    """


# %% checks


class Axis(StrEnum):
    """
    The axes of a vector, for error messages.
    """

    X = "x"
    """
    The first component.
    """

    Y = "y"
    """
    The second component.
    """

    Z = "z"
    """
    The third component.
    """


VECTOR_AXES = tuple(Axis)
"""
The axes of a vector, in the order of its components.
"""


@dataclass(frozen=True)
class DraftCheck:
    """
    Checks that a draft stays within the builder's limits.
    """

    limits: SceneBuilderLimits
    """
    The limits.
    """

    def check(self, draft: SceneDraft) -> None:
        """
        :param draft: A draft as a browser sent it.
        :raises InvalidDraftText: For an empty or overly long text or one with control
            characters.
        :raises InvalidDraftIdentifier: For an identity of other characters.
        :raises ValueOutOfRange: For a number that is not finite or beyond its limit.
        :raises NonPositiveScale: For a scale factor of zero or less.
        :raises TooManyEntries: For more instances, offsets, joints or notices than
            fit.
        :raises DuplicateInstance: For two instances of one identity.
        :raises DraftTooLarge: For a draft whose JSON is too large.
        """
        self.text(DraftKey.NAME, draft.name, self.limits.maximum_name_length)
        if draft.source_scene is not None:
            self.text(
                DraftKey.SOURCE_SCENE,
                draft.source_scene,
                self.limits.maximum_reference_length,
            )
        self.count(DraftKey.INSTANCES, draft.instances)
        identities = set()
        for instance in draft.instances:
            self.instance(instance)
            if instance.identifier in identities:
                raise DuplicateInstance(instance.identifier)
            identities.add(instance.identifier)
        self.count(DraftKey.NOTICES, draft.notices)
        for notice in draft.notices:
            self.text(NoticeKey.NAME, notice.name, self.limits.maximum_name_length)
            self.text(
                NoticeKey.ASSET, notice.asset, self.limits.maximum_reference_length
            )
        size = len(json.dumps(draft.to_json(), allow_nan=False).encode("utf-8"))
        if size > self.limits.maximum_document_bytes:
            raise DraftTooLarge(size, self.limits.maximum_document_bytes)

    def instance(self, instance: DraftInstance) -> None:
        """
        :param instance: One instance of a draft.
        """
        self.identity(instance.identifier)
        location = self.location(DraftKey.INSTANCES, instance.identifier)
        self.text(
            self.location(location, InstanceKey.ASSET),
            instance.asset,
            self.limits.maximum_reference_length,
        )
        self.text(
            self.location(location, InstanceKey.NAME),
            instance.name,
            self.limits.maximum_name_length,
        )
        self.vector(self.location(location, InstanceKey.POSITION), instance.position)
        self.vector(self.location(location, InstanceKey.ROTATION), instance.rotation)
        self.scale(self.location(location, InstanceKey.SCALE), instance.scale)
        self.count(
            self.location(location, InstanceKey.LINK_OFFSETS), instance.link_offsets
        )
        for link, offset in instance.link_offsets.items():
            self.offset(
                self.location(location, InstanceKey.LINK_OFFSETS, link), link, offset
            )
        self.count(
            self.location(location, InstanceKey.JOINT_POSITIONS),
            instance.joint_positions,
        )
        for joint, value in instance.joint_positions.items():
            joint_location = self.location(location, InstanceKey.JOINT_POSITIONS, joint)
            self.text(joint_location, joint, self.limits.maximum_reference_length)
            self.number(joint_location, value)
        if instance.point_cloud is not None:
            self.appearance(
                self.location(location, InstanceKey.POINT_CLOUD), instance.point_cloud
            )

    def identity(self, identifier: str) -> None:
        """
        :param identifier: An instance or draft identity.
        :raises InvalidDraftIdentifier: Unless it is a bounded run of letters, digits,
            ``_`` and ``-``.
        """
        if (
            len(identifier) > self.limits.maximum_identifier_length
            or IDENTITY_CHARACTERS.fullmatch(identifier) is None
        ):
            raise InvalidDraftIdentifier(identifier)

    def offset(self, location: str, link: str, offset: LinkOffset) -> None:
        """
        :param location: Where the offset sits.
        :param link: The link's name.
        :param offset: The link's offset.
        """
        self.text(location, link, self.limits.maximum_reference_length)
        self.vector(self.location(location, LinkOffsetKey.POSITION), offset.position)
        self.vector(self.location(location, LinkOffsetKey.ROTATION), offset.rotation)

    def appearance(self, location: str, appearance: PointCloudAppearance) -> None:
        """
        :param location: Where the appearance sits.
        :param appearance: How a reference point cloud is shown.
        """
        self.bounded(
            self.location(location, AppearanceKey.POINT_SIZE),
            appearance.point_size,
            self.limits.minimum_point_size,
            self.limits.maximum_point_size,
        )
        self.bounded(
            self.location(location, AppearanceKey.OPACITY),
            appearance.opacity,
            self.limits.minimum_opacity,
            self.limits.maximum_opacity,
        )

    def text(self, location: str, text: str, maximum: int) -> None:
        """
        :param location: Where the text sits.
        :param text: A name or reference.
        :param maximum: How many characters it may have.
        :raises InvalidDraftText: When it is blank, too long or holds control
            characters.
        """
        if (
            not text.strip()
            or len(text) > maximum
            or any(ord(character) < CONTROL_CHARACTER_LIMIT for character in text)
        ):
            raise InvalidDraftText(location, text)

    def vector(self, location: str, vector: Vector3) -> None:
        """
        :param location: Where the vector sits.
        :param vector: A position or rotation.
        """
        for axis, value in zip(VECTOR_AXES, vector.to_json()):
            self.number(self.location(location, axis), value)

    def scale(self, location: str, scale: Vector3) -> None:
        """
        :param location: Where the scale sits.
        :param scale: The scale factor along each axis.
        :raises NonPositiveScale: For a factor of zero or less.
        """
        for axis, value in zip(VECTOR_AXES, scale.to_json()):
            axis_location = self.location(location, axis)
            if value <= 0:
                raise NonPositiveScale(axis_location, value)
            self.bounded(axis_location, value, 0.0, self.limits.maximum_scale)

    def number(self, location: str, value: float) -> None:
        """
        :param location: Where the number sits.
        :param value: A coordinate, angle or joint value.
        """
        maximum = self.limits.maximum_coordinate
        self.bounded(location, value, -maximum, maximum)

    @staticmethod
    def bounded(location: str, value: float, minimum: float, maximum: float) -> None:
        """
        :param location: Where the number sits.
        :param value: The number.
        :param minimum: The smallest allowed value.
        :param maximum: The largest allowed value.
        :raises ValueOutOfRange: When the number is not finite or out of the bounds.
        """
        if not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueOutOfRange(location, value, minimum, maximum)

    def count(self, location: str, entries: Sized) -> None:
        """
        :param location: Where the entries sit.
        :param entries: A list or mapping of a draft.
        :raises TooManyEntries: When it holds more entries than a draft has instances.
        """
        if len(entries) > self.limits.maximum_instances:
            raise TooManyEntries(location, len(entries), self.limits.maximum_instances)

    @staticmethod
    def location(*steps: str) -> str:
        """
        :param steps: Keys from the draft's root.
        :return: The location they name, for error messages.
        """
        return LOCATION_SEPARATOR.join(steps)


# %% notices


@dataclass(frozen=True)
class DraftResources:
    """
    Checks a draft's resources against the library and completes its notices.
    """

    library: ResourceLibrary
    """
    The resource library.
    """

    def complete(self, draft: SceneDraft) -> SceneDraft:
        """
        :param draft: A draft whose limits were checked.
        :return: The draft with the notices of its placed resources, as the library
            holds them, in place of the notices it carried.
        :raises InvalidResourceIdentifier: For an instance of a malformed resource
            identifier.
        :raises NotAModel: For an instance of a resource that cannot be placed.
        :raises FileNotInDirectory: For an instance of a missing resource.
        :raises NotAPointCloud: For a point cloud appearance on a model.
        """
        notices: Dict[str, ResourceNotice] = {}
        for instance in draft.instances:
            identifier = ResourceIdentifier.parse(instance.asset)
            self.library.placeable_file(identifier)
            if (
                instance.point_cloud is not None
                and ResourceLibrary.kind_of(identifier) is not ResourceKind.POINT_CLOUD
            ):
                raise NotAPointCloud(instance.asset)
            for notice in self.library.notices(identifier):
                notices[notice.asset] = notice
        return replace(draft, notices=list(notices.values()))


# %% storage


@dataclass(frozen=True)
class DraftStore:
    """
    The saved drafts, one JSON file per draft, written whole or not at all.
    """

    directory: Path
    """
    The draft directory.
    """

    check: DraftCheck
    """
    Checks draft identities.
    """

    def summaries(self) -> List[DraftSummary]:
        """
        :return: Every readable saved draft, sorted by identity; a damaged draft does
            not hide the others.
        """
        if not self.directory.is_dir():
            return []
        summaries = []
        for path in sorted(self.directory.glob(f"*{DraftFile.SUFFIX}")):
            if path.is_symlink() or IDENTITY_CHARACTERS.fullmatch(path.stem) is None:
                continue
            read = DraftFileReader(path).read()
            if isinstance(read, UnreadableDraft):
                continue
            summaries.append(
                DraftSummary(
                    identifier=path.stem,
                    name=read.name,
                    updated_at=datetime.fromtimestamp(
                        path.stat().st_mtime, timezone.utc
                    ).isoformat(),
                )
            )
        return summaries

    def load(self, identifier: str) -> DraftRecord:
        """
        :param identifier: A draft's identity.
        :return: The saved draft.
        :raises InvalidDraftIdentifier: For a malformed identity.
        :raises UnknownDraft: When no draft has the identity.
        :raises UnreadableDraft: When the draft's file is damaged.
        """
        path = self.path(identifier)
        if not path.is_file():
            raise UnknownDraft(identifier)
        read = DraftFileReader(path).read()
        if isinstance(read, UnreadableDraft):
            raise read
        return DraftRecord(identifier=identifier, document=read)

    def save(self, record: DraftRecord) -> DraftRecord:
        """
        :param record: A checked draft, with the identity of the draft it replaces or
            without one for a new draft.
        :return: The saved draft with its identity.
        :raises InvalidDraftIdentifier: For a malformed identity.
        :raises UnsafeStoragePath: When the draft directory or file is a symbolic link.
        """
        identifier = record.identifier or uuid.uuid4().hex
        target = self.path(identifier)
        if self.directory.is_symlink():
            raise UnsafeStoragePath(self.directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.directory,
            prefix=DraftFile.TEMPORARY_PREFIX,
            delete=False,
        ) as temporary:
            json.dump(record.document.to_json(), temporary, indent=2, allow_nan=False)
            temporary.write("\n")
        os.replace(temporary.name, target)
        return DraftRecord(identifier=identifier, document=record.document)

    def path(self, identifier: str) -> Path:
        """
        :param identifier: A draft's identity.
        :return: The draft's file.
        :raises InvalidDraftIdentifier: For a malformed identity.
        :raises UnsafeStoragePath: When the file is a symbolic link.
        """
        self.check.identity(identifier)
        path = self.directory / f"{identifier}{DraftFile.SUFFIX}"
        if path.is_symlink():
            raise UnsafeStoragePath(path)
        return path


@dataclass(frozen=True)
class DraftFileReader:
    """
    Reads one saved draft file.
    """

    path: Path
    """
    The draft's file, named after its identity.
    """

    def read(self) -> Union[SceneDraft, UnreadableDraft]:
        """
        A saved draft is written by the store, so a file that is no draft is damaged;
        this is the one place where its reading errors become data, so a damaged draft
        does not hide the others.

        :return: The draft, or why it cannot be read.
        """
        try:
            return SceneDraft.from_json(
                json.loads(self.path.read_text(encoding="utf-8"))
            )
        except (ValueError, ProtocolError) as error:
            return UnreadableDraft(self.path.stem, str(error))
