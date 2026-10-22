"""
The independent laboratory devices: twenty instrument and accessory folders, each
loadable on its own with CRAM's URDF parser and carrying its own asset terms.
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

    VORTEX_MIXER = "vortex_mixer"
    """
    Contact cup with vertical travel and a speed control.
    """

    ELECTRONIC_PIPETTE = "electronic_pipette"
    """
    Handheld pipette with a moving plunger and tip ejector.
    """

    TIP_RACK = "tip_rack"
    """
    Opening rack with twenty-four tip sockets.
    """

    TUBE_CAPPER = "tube_capper"
    """
    Tube clamp, travelling chuck and rotating closure head.
    """

    THERMOMIXER = "thermomixer"
    """
    Temperature-controlled mixer with an opening cover and a moving sample block.
    """

    MICROPLATE_READER = "microplate_reader"
    """
    Optical plate reader with an opening sample drawer.
    """

    MICROPLATE = "microplate_96_well"
    """
    Movable plate with ninety-six open wells.
    """

    INCUBATOR = "incubator"
    """
    Glazed chamber door and three separate shelves.
    """

    DIGITAL_MICROSCOPE = "digital_microscope"
    """
    Focus carriage, two-axis specimen stage and objective turret.
    """

    PH_METER = "ph_meter"
    """
    Measurement console with an adjustable electrode support.
    """

    PH_PROBE = "ph_probe"
    """
    Separate glass electrode with a guarded sensing bulb.
    """

    PCR_THERMOCYCLER = "pcr_thermocycler"
    """
    Thermal block with an opening heated cover.
    """

    BARCODE_SCANNER = "barcode_scanner"
    """
    Handheld scanner with a moving trigger.
    """

    BARCODE_DOCK = "barcode_dock"
    """
    Charging cradle for the handheld scanner.
    """

    LABEL_PRINTER = "label_printer"
    """
    Opening media cover, rotating label roll and feed roller.
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
        if name not in LaboratoryDevice:
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
