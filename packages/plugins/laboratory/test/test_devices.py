"""
The independent laboratory devices.
"""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree
import json
import struct

import pytest

from cramera_laboratory.devices import (
    DeviceFile,
    DeviceShelf,
    LaboratoryDevice,
)
from cramera_laboratory.urdf import UrdfAttribute, UrdfJointType, UrdfTag
from cramera_laboratory.exceptions import DeviceFolderExists, UnknownDevice
from cramera_laboratory.resources import (
    RESOURCES_DIRECTORY,
    LaboratoryResource,
    RightsFile,
)

LICENSE_FILE = "LICENSE.txt"
"""
The licence text every device folder carries.
"""


def test_the_catalog_lists_every_device_folder():
    entries = DeviceShelf().entries().devices
    assert [entry.name for entry in entries] == sorted(
        device.value for device in LaboratoryDevice
    )


def test_every_device_folder_loads_on_its_own_terms():
    for folder in DeviceShelf().folders():
        assert folder.description.is_file()
        assert (folder.directory / RightsFile.RECORD).is_file()
        assert (folder.directory / LICENSE_FILE).is_file()


def test_an_entry_counts_the_moving_joints_of_its_urdf():
    folder = DeviceShelf().folder(LaboratoryDevice.CENTRIFUGE)
    joints = ElementTree.parse(folder.description).getroot().findall(UrdfTag.JOINT)
    assert folder.entry().moving_joints == sum(
        joint.get(UrdfAttribute.TYPE) != UrdfJointType.FIXED for joint in joints
    )
    assert folder.entry().moving_joints > 0
    assert folder.entry().description == DeviceFile.DESCRIPTION


def test_a_title_comes_from_the_readme():
    folder = DeviceShelf().folder(LaboratoryDevice.CENTRIFUGE)
    first_line = (
        (folder.directory / DeviceFile.README)
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert first_line.endswith(folder.title()) and not folder.title().startswith("#")


def test_a_copy_keeps_the_licence_and_refuses_to_overwrite(tmp_path):
    folder = DeviceShelf().folder(LaboratoryDevice.SCALE)
    copy = folder.copy_to(tmp_path)
    assert (copy / LICENSE_FILE).is_file() and (copy / DeviceFile.DESCRIPTION).is_file()
    with pytest.raises(DeviceFolderExists):
        folder.copy_to(tmp_path)


def test_an_unknown_device_is_refused():
    with pytest.raises(UnknownDevice):
        DeviceShelf().folder("toaster")


@pytest.mark.parametrize(
    "description",
    [
        RESOURCES_DIRECTORY / LaboratoryResource.BENCH / "environment.urdf",
        DeviceShelf().folder(LaboratoryDevice.DUAL_DISPENSER).description,
    ],
)
def test_receiving_guide_collisions_match_the_visible_meshes(description):
    data = (description.parent / "assets" / "pipetting_station.glb").read_bytes()
    [length] = struct.unpack_from("<I", data, 12)
    document = json.loads(data[20 : 20 + length])
    nodes = {node.get("name"): node for node in document["nodes"]}
    collisions = ElementTree.parse(description).findall(".//collision")
    guides = [
        item
        for item in collisions
        if item.get("name", "").startswith("pipetting_holder_")
    ]
    assert len(guides) == 3
    for guide in guides:
        center = [float(value) for value in guide.find("origin").get("xyz").split()]
        size = [
            float(value) for value in guide.find("geometry/box").get("size").split()
        ]
        node = nodes[guide.get("name")]
        [primitive] = document["meshes"][node["mesh"]]["primitives"]
        positions = document["accessors"][primitive["attributes"]["POSITION"]]
        scale = node.get("scale", [1.0, 1.0, 1.0])
        translation = node.get("translation", [0.0, 0.0, 0.0])
        for bound, sign in (("min", -1), ("max", 1)):
            visible = [
                positions[bound][axis] * scale[axis] + translation[axis]
                for axis in range(3)
            ]
            collision = [center[axis] + sign * size[axis] / 2 for axis in range(3)]
            assert visible == pytest.approx(collision, abs=1e-8)
