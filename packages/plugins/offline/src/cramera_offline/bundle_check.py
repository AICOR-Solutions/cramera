"""
Checking that a scene bundle holds every file it references, so it can be shown from its
directory alone: the files ``scene.json`` names, and every mesh, material library and
texture those files name in turn.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import unquote, urlsplit

from typing_extensions import List, Optional, Set, Union

from cramera_offline.exceptions import InvalidReference, UnreadableFile
from cramera_offline.json_file import JsonFile
from cramera_offline.references import ReferenceReaders
from cramera_protocol.bundle.files import BundleFile, MeshFormat
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.exceptions import ProtocolError
from cramera_protocol.offline import AssetProblem, AssetProblemKind, BundleCheckReport

# %% vocabulary


class UrlScheme(StrEnum):
    """
    The URL schemes a reference may carry without leaving the bundle.
    """

    DATA = "data"
    """
    Content stored in the reference itself, as glTF files embed buffers and images.
    """


PARENT_DIRECTORY = ".."
"""
The path segment that leads to the parent directory.
"""

# %% references


@dataclass(frozen=True)
class Reference:
    """
    A file reference and the bundle file that declares it.
    """

    source: str
    """
    The declaring file, relative to the bundle with ``/`` separators.
    """

    location: str
    """
    The reference as the file declares it; relative to the declaring file's directory.
    """


@dataclass(frozen=True)
class ResolvedFile:
    """
    A referenced file that exists inside the bundle.
    """

    relative: str
    """
    The file, relative to the bundle with ``/`` separators.
    """


@dataclass(frozen=True)
class EmbeddedContent:
    """
    A reference whose content is stored in the reference itself.
    """


# %% check


@dataclass
class BundleCheck:
    """
    Follows every reference of one bundle, from ``scene.json`` through models, meshes
    and material libraries to textures, and reports each that leaves the bundle or names
    a missing file.
    """

    bundle: Path
    """
    The bundle directory.
    """

    readers: ReferenceReaders = field(default_factory=ReferenceReaders)
    """
    Reads the references inside each file format.
    """

    checked: Set[str] = field(default_factory=set, init=False)
    """
    The files found so far, relative to the bundle.
    """

    problems: List[AssetProblem] = field(default_factory=list, init=False)
    """
    The problems found so far.
    """

    def report(self) -> BundleCheckReport:
        """
        :return: The files the bundle holds and the references it cannot follow.
        """
        self.checked.clear()
        self.problems.clear()
        pending = self.scene_references()
        while pending:
            reference = pending.pop(0)
            resolved = self.resolve(reference)
            if not isinstance(resolved, ResolvedFile):
                continue
            if resolved.relative in self.checked:
                continue
            self.checked.add(resolved.relative)
            pending.extend(self.references_inside(resolved.relative))
        return BundleCheckReport(
            bundle=self.bundle.name,
            checked_files=sorted(self.checked),
            problems=list(self.problems),
        )

    def scene_references(self) -> List[Reference]:
        """
        :return: The files ``scene.json`` names; the problem of a missing or unreadable
            ``scene.json`` is recorded and nothing is returned.
        """
        scene_file = self.bundle / BundleFile.SCENE
        if not scene_file.is_file():
            self.add_problem(
                AssetProblemKind.MISSING, BundleFile.SCENE, BundleFile.SCENE
            )
            return []
        description = self.scene_description(scene_file)
        if description is None:
            return []
        self.checked.add(BundleFile.SCENE.value)
        for missing in description.missing_assets:
            self.add_problem(
                AssetProblemKind.DECLARED_MISSING, BundleFile.SCENE, missing
            )
        locations = [
            description.trajectory,
            description.statecharts,
            description.background,
            description.rendering.environment if description.rendering else None,
            *(model.urdf for model in description.models),
            *(
                location
                for scene_object in description.objects
                for location in (
                    scene_object.mesh,
                    scene_object.material_library,
                    scene_object.urdf,
                )
            ),
        ]
        return [
            Reference(BundleFile.SCENE.value, location)
            for location in locations
            if location is not None
        ]

    def scene_description(self, scene_file: Path) -> Optional[SceneDescription]:
        """
        A damaged ``scene.json`` must still give a report, so this is where its reading
        errors become a problem.

        :param scene_file: The bundle's ``scene.json``.
        :return: The scene description, or None when it cannot be read.
        """
        try:
            return SceneDescription.from_json(JsonFile(scene_file).read())
        except UnreadableFile as error:
            reason = error.reason
        except ProtocolError as error:
            reason = error.message()
        self.add_problem(
            AssetProblemKind.UNREADABLE, BundleFile.SCENE, BundleFile.SCENE, reason
        )
        return None

    def references_inside(self, relative: str) -> List[Reference]:
        """
        A damaged asset must not hide the problems of the others, so this is where its
        reading errors become a problem.

        :param relative: A file of the bundle, relative to the bundle.
        :return: The references the file declares.
        """
        try:
            locations = self.readers.references(self.bundle / relative)
        except UnreadableFile as error:
            self.add_problem(
                AssetProblemKind.UNREADABLE, relative, relative, error.reason
            )
            return []
        except InvalidReference as error:
            self.add_problem(
                AssetProblemKind.INVALID_REFERENCE, relative, error.declaration
            )
            return []
        return [Reference(relative, location) for location in locations]

    def resolve(
        self, reference: Reference
    ) -> Union[ResolvedFile, EmbeddedContent, None]:
        """
        :param reference: A reference of a bundle file.
        :return: The referenced file, the marker of embedded content, or None after
            the reason it cannot be followed was recorded.
        """
        parts = urlsplit(reference.location.strip())
        if parts.scheme == UrlScheme.DATA and self.may_embed(reference.source):
            return EmbeddedContent()
        location = unquote(parts.path).replace("\\", "/")
        if (
            parts.scheme
            or parts.netloc
            or location.startswith("/")
            or PureWindowsPath(location).drive
        ):
            self.add_problem(
                AssetProblemKind.EXTERNAL, reference.source, reference.location
            )
            return None
        if not location or "\x00" in location:
            self.add_problem(
                AssetProblemKind.INVALID_REFERENCE,
                reference.source,
                reference.location,
            )
            return None
        relative = posixpath.normpath(
            str(PurePosixPath(reference.source).parent / location)
        )
        target = (self.bundle / relative).resolve()
        if relative.split("/")[0] == PARENT_DIRECTORY or not target.is_relative_to(
            self.bundle.resolve()
        ):
            self.add_problem(
                AssetProblemKind.OUTSIDE_BUNDLE, reference.source, reference.location
            )
            return None
        if not target.is_file():
            self.add_problem(
                AssetProblemKind.MISSING, reference.source, reference.location
            )
            return None
        return ResolvedFile(relative)

    @staticmethod
    def may_embed(source: str) -> bool:
        """
        :param source: A bundle file.
        :return: Whether its format stores content inside references, as glTF does.
        """
        return PurePosixPath(source).suffix.lower() in (MeshFormat.GLTF, MeshFormat.GLB)

    def add_problem(
        self,
        kind: AssetProblemKind,
        source: str,
        reference: str,
        detail: Optional[str] = None,
    ) -> None:
        """
        :param kind: Why the reference cannot be followed.
        :param source: The declaring file, relative to the bundle.
        :param reference: The reference as declared.
        :param detail: Why the file could not be parsed.
        """
        self.problems.append(
            AssetProblem(
                kind=kind, source=str(source), reference=reference, detail=detail
            )
        )
