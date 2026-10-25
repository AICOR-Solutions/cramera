"""
The compact laboratory's five independent devices, each carrying its own asset terms.
"""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from typing_extensions import List

from cramera_laboratory.exceptions import DeviceFolderExists, UnknownDevice
from cramera_laboratory.resources import RESOURCES_DIRECTORY, LaboratoryResource
from cramera_laboratory.urdf import UrdfAttribute, UrdfJointType, UrdfTag
from cramera_protocol.laboratory.physics import DeviceCatalog, DeviceEntry

HEADING_PREFIX = "# "
"""
What starts the title line of a device's README.
"""

# %% names


class LaboratoryDevice(StrEnum):
    """
    The device folders of the catalog.
    """

    CENTRIFUGE = "centrifuge"
    """
    Housing, continuous rotor and hinged protective lid.
    """

    DUAL_DISPENSER = "dual_dispenser"
    """
    Two-reservoir dispenser with an open receiving cradle.
    """

    SCALE = "scale"
    """
    Weighing instrument with its pan and open sample support.
    """

    TUBE_RACK = "tube_rack"
    """
    Six-position rack with open insertion apertures.
    """

    REFRIGERATOR = "refrigerator"
    """
    Compact sample refrigerator with a glass door and six storage positions.
    """


class DeviceFile(StrEnum):
    """
    The files every device folder holds.
    """

    DESCRIPTION = "model.urdf"
    """
    The URDF, which refers only to files of the same folder.
    """

    README = "README.md"
    """
    The device's description.
    """


# %% devices


@dataclass(frozen=True)
class DeviceFolder:
    """
    One device folder.
    """

    device: LaboratoryDevice
    """
    The device.
    """

    catalog: Path = RESOURCES_DIRECTORY / LaboratoryResource.DEVICES
    """
    The folder holding the device folders.
    """

    @property
    def directory(self) -> Path:
        """
        The device's folder.
        """
        return self.catalog / self.device.value

    @property
    def description(self) -> Path:
        """
        The device's URDF.
        """
        return self.directory / DeviceFile.DESCRIPTION

    def title(self) -> str:
        """
        :return: The heading of the device's README.
        """
        first_line = (
            (self.directory / DeviceFile.README)
            .read_text(encoding="utf-8")
            .splitlines()[0]
        )
        return first_line.removeprefix(HEADING_PREFIX).strip()

    def moving_joints(self) -> int:
        """
        :return: How many joints of the device's URDF move.
        """
        joints = ElementTree.parse(self.description).getroot().findall(UrdfTag.JOINT)
        return sum(
            joint.get(UrdfAttribute.TYPE) != UrdfJointType.FIXED for joint in joints
        )

    def entry(self) -> DeviceEntry:
        """
        :return: The device as the catalog lists it.
        """
        return DeviceEntry(
            name=self.device.value,
            title=self.title(),
            description=DeviceFile.DESCRIPTION.value,
            moving_joints=self.moving_joints(),
        )

    def copy_to(self, parent: Path) -> Path:
        """
        Copy the whole device folder, its licence and notices included, so the copy
        loads without the plugin and keeps the assets' terms.

        :param parent: The folder receiving the device folder.
        :return: The copied device folder.
        :raises DeviceFolderExists: When the parent holds a folder of that name.
        """
        destination = parent / self.device.value
        if destination.exists():
            raise DeviceFolderExists(destination)
        shutil.copytree(self.directory, destination)
        return destination


@dataclass(frozen=True)
class DeviceShelf:
    """
    The device catalog.
    """

    catalog: Path = RESOURCES_DIRECTORY / LaboratoryResource.DEVICES
    """
    The folder holding the device folders.
    """

    def folder(self, name: str) -> DeviceFolder:
        """
        :param name: A device's folder name.
        :return: The device's folder.
        :raises UnknownDevice: When the catalog has no such device.
        """
        if name not in tuple(LaboratoryDevice):
            raise UnknownDevice(name)
        return DeviceFolder(LaboratoryDevice(name), self.catalog)

    def folders(self) -> List[DeviceFolder]:
        """
        :return: Every device folder, by name.
        """
        return [
            DeviceFolder(device, self.catalog)
            for device in sorted(LaboratoryDevice, key=lambda device: device.value)
        ]

    def entries(self) -> DeviceCatalog:
        """
        :return: The catalog as the browser reads it.
        """
        return DeviceCatalog(devices=[folder.entry() for folder in self.folders()])
