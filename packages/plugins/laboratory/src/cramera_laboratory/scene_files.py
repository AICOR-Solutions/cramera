"""
Writing bundle documents and registering bundles in a scenes directory's ``index.json``.

cramera-cram has the same for recordings; the laboratory keeps its own small copy
because cramera-cram pulls in cramera-questions, whose viewer plugin cannot load without
the CRAM workspace, and the laboratory's viewer side must run without it.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from typing_extensions import Type, TypeVar

from cramera.scenes import SceneDirectory, SceneSource
from cramera_protocol.bundle.files import ScenesDirectoryFile
from cramera_protocol.bundle.index import SceneIndexEntry
from cramera_protocol.document import JsonDocument

JSON_INDENT = 2
"""
How far written JSON is indented.
"""

TEMPORARY_SUFFIX = ".tmp"
"""
The suffix of a file being written.
"""

DocumentType = TypeVar("DocumentType", bound=JsonDocument)
"""
A document class.
"""

# %% files


@dataclass(frozen=True)
class JsonFile:
    """
    One JSON file holding a protocol document.
    """

    path: Path
    """
    The file.
    """

    def write(self, document: JsonDocument) -> None:
        """
        Write the document so a reader sees the old or the new file, never half of one.

        :param document: The document.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=TEMPORARY_SUFFIX,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(document.to_json(), stream, indent=JSON_INDENT)
        os.replace(temporary, self.path)

    def read(self, document_class: Type[DocumentType]) -> DocumentType:
        """
        :param document_class: The stored document's class.
        :return: The document.
        """
        return document_class.from_json(
            json.loads(self.path.read_text(encoding="utf-8"))
        )


@dataclass(frozen=True)
class LocalSceneIndex:
    """
    The ``index.json`` of the viewer's local scenes.
    """

    directory: Path
    """
    The local scenes directory.
    """

    def register(self, entry: SceneIndexEntry) -> None:
        """
        List a bundle in the index, replacing an entry of the same name.

        Without an index the directory needs none: the viewer lists every bundle of a directory
        without one.

        :param entry: The bundle's entry.
        """
        index_file = JsonFile(self.directory / ScenesDirectoryFile.INDEX)
        if not index_file.path.is_file():
            return
        index = SceneDirectory(self.directory, SceneSource.LOCAL).index()
        index.scenes = [scene for scene in index.scenes if scene.name != entry.name]
        index.scenes.append(entry)
        index_file.write(index)
