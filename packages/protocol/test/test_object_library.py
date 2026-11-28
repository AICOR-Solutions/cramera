"""
The collection files of object libraries and the catalogue of what they say about each
object model.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cramera_protocol.exceptions import UnsupportedProtocolVersion
from cramera_protocol.object_library import (
    COLLECTION_FORMAT,
    CollectionKey,
    LibraryVariable,
    ObjectCatalog,
    ObjectCollection,
)
from cramera_protocol.version import ProtocolVersion


def write_collection(directory: Path, data: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "collection.json"
    path.write_text(json.dumps(data), "utf-8")
    return path


CUBES = {
    "objects": [
        {"slug": "red_cube", "name": "Red cube", "grasp": "from_above", "color": "red"},
        {"slug": "crate", "name": "Crate"},
    ]
}


def test_a_collection_without_a_format_version_is_read_as_today(tmp_path):
    collection = ObjectCollection.from_file(write_collection(tmp_path, CUBES))
    assert [entry.slug for entry in collection.entries] == ["red_cube", "crate"]
    assert collection.entries[0].color == "red"
    assert collection.entries[0].grasp == "from_above"
    assert collection.entries[1].color is None
    assert collection.entries[1].grasp is None


def test_a_collection_of_a_later_minor_version_keeps_the_keys_it_does_not_know(
    tmp_path,
):
    later = ProtocolVersion(COLLECTION_FORMAT.major, COLLECTION_FORMAT.minor + 1)
    data = {
        CollectionKey.FORMAT_VERSION: later.to_json(),
        "license": "CC-BY",
        "objects": [{"slug": "cup", "name": "Cup", "mass": 0.2}],
    }
    collection = ObjectCollection.from_file(write_collection(tmp_path, data))
    assert collection.format_version == later
    assert collection.entries[0].unknown == {"mass": 0.2}
    assert collection.unknown == {"license": "CC-BY"}
    assert collection.to_json() == data


def test_a_collection_of_another_major_version_is_refused(tmp_path):
    data = {CollectionKey.FORMAT_VERSION: "2.0", "objects": []}
    with pytest.raises(UnsupportedProtocolVersion):
        ObjectCollection.from_file(write_collection(tmp_path, data))


def test_the_catalogue_describes_a_model_by_the_folder_its_path_ends_in(tmp_path):
    write_collection(tmp_path / "aicor" / "objects" / "cubes", CUBES)
    catalog = ObjectCatalog.from_environment(
        {LibraryVariable.LIBRARIES: str(tmp_path / "aicor")}
    )
    red = catalog.description("aicor/objects/cubes/red_cube/model.urdf")
    assert (red.name, red.color) == ("Red cube", "red")
    assert catalog.description("aicor/objects/cubes/green_cube/model.urdf") is None
    assert ObjectCatalog.from_environment({}).descriptions == {}
