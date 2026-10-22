"""
The authored laboratory as scene bundles describe it.
"""

from __future__ import annotations

import pytest

from cramera_protocol.browser import BROWSER_ENUMERATIONS
from cramera_protocol.exceptions import InvalidDocumentValue
from cramera_protocol.geometry import Pose, Vector3
from cramera_protocol.laboratory.layout import (
    AssetRights,
    AssetRightsKey,
    BenchKey,
    BenchLayout,
    CentrifugeKey,
    CornerBoxKey,
    InstrumentCollection,
    InstrumentCollectionKey,
    InstrumentJointKind,
    InstrumentKey,
    LaboratorySceneKey,
    PlanarSize,
    Quaternion,
    RackSlotKey,
    ScaleKey,
    VesselDimensions,
    VesselDimensionsKey,
    VesselPlacementKey,
)

LABORATORY_LICENSE = "LicenseRef-AICOR-Laboratory-Assets"
"""
The identifier of the laboratory assets' terms, as the owner set it.
"""

INSTRUMENT_WITH_JOINTS = "tube_capper"
"""
The instrument of the fixture whose joints the tests read.
"""

PASSIVE_INSTRUMENT = "barcode_dock"
"""
The instrument of the fixture without moving joints.
"""

# %% bench


def test_the_bench_reads_its_slots_vessels_and_instruments(read_json):
    data = read_json("laboratory/bench.json")
    bench = BenchLayout.from_json(data)
    first_slot = data[BenchKey.RACK_SLOTS][0]
    assert bench.rack_slots[0].identifier == first_slot[RackSlotKey.IDENTIFIER]
    assert bench.rack_slots[0].pose == Pose.from_json(first_slot[RackSlotKey.POSE])
    assert [placement.key for placement in bench.tubes] == [
        tube[VesselPlacementKey.KEY] for tube in data[BenchKey.TUBES]
    ]
    centrifuge = data[BenchKey.CENTRIFUGE]
    assert bench.centrifuge.maximum_speed == centrifuge[CentrifugeKey.MAXIMUM_SPEED]
    assert len(bench.centrifuge.slots) == len(centrifuge[CentrifugeKey.SLOTS])
    assert bench.scale.display_size == PlanarSize.from_json(
        data[BenchKey.SCALE][ScaleKey.DISPLAY_SIZE]
    )


def test_the_bench_round_trips_unchanged(read_json):
    data = read_json("laboratory/bench.json")
    assert BenchLayout.from_json(data).to_json() == data


def test_a_slot_is_found_by_its_name(read_json):
    data = read_json("laboratory/bench.json")
    bench = BenchLayout.from_json(data)
    last = data[BenchKey.RACK_SLOTS][-1]
    assert bench.slot(last[RackSlotKey.IDENTIFIER]).pose == Pose.from_json(
        last[RackSlotKey.POSE]
    )


def test_a_slot_the_rack_lacks_is_refused(read_json):
    bench = BenchLayout.from_json(read_json("laboratory/bench.json"))
    with pytest.raises(KeyError):
        bench.slot("Z9")


def test_a_bench_without_instruments_leaves_them_out(read_json):
    data = read_json("laboratory/bench.json")
    plain = {key: data[key] for key in (BenchKey.RACK_SLOTS, BenchKey.TUBES)}
    bench = BenchLayout.from_json(plain)
    assert bench.centrifuge is None and bench.refrigerator is None
    assert BenchKey.CENTRIFUGE not in bench.to_json()
    assert BenchLayout.from_json(bench.to_json()) == bench


def test_a_slot_with_a_short_pose_is_refused(read_json):
    with pytest.raises(InvalidDocumentValue):
        BenchLayout.from_json(
            read_json("laboratory/invalid/bench_with_short_slot_pose.json")
        )


# %% instruments


def test_the_collection_reads_joints_and_passes_frames_on(read_json):
    data = read_json("laboratory/instruments.json")
    collection = InstrumentCollection.from_json(data)
    instruments = {
        instrument.identifier: instrument for instrument in collection.instruments
    }
    written = {
        instrument[InstrumentKey.IDENTIFIER]: instrument
        for instrument in data[InstrumentCollectionKey.INSTRUMENTS]
    }
    capper = instruments[INSTRUMENT_WITH_JOINTS]
    assert len(capper.joints) == len(
        written[INSTRUMENT_WITH_JOINTS][InstrumentKey.JOINTS]
    )
    assert {joint.kind for joint in capper.joints} <= set(InstrumentJointKind)
    assert instruments[PASSIVE_INSTRUMENT].joints == []
    assert collection.to_json() == data


def test_the_collection_bounds_are_corners(read_json):
    data = read_json("laboratory/instruments.json")
    collection = InstrumentCollection.from_json(data)
    assert collection.bounds.minimum == Vector3.from_json(
        data[InstrumentCollectionKey.BOUNDS][CornerBoxKey.MINIMUM]
    )


# %% rights


def test_the_asset_rights_keep_the_owner_terms(read_json):
    data = read_json("laboratory/asset_rights.json")
    rights = AssetRights.from_json(data)
    assert rights.license_identifier == LABORATORY_LICENSE
    assert rights.license_identifier == data[AssetRightsKey.LICENSE]
    assert rights.to_json() == data


# %% values


def test_a_quaternion_holds_four_numbers():
    with pytest.raises(InvalidDocumentValue):
        Quaternion.from_json([0, 0, 1])


def test_the_browser_reads_the_laboratory_keys():
    assert {LaboratorySceneKey, BenchKey, InstrumentKey} <= set(BROWSER_ENUMERATIONS)


def test_every_enumeration_the_browser_reads_has_its_own_name():
    names = [enumeration.__name__ for enumeration in BROWSER_ENUMERATIONS]
    assert len(names) == len(set(names))


# %% semantics


def test_the_vessel_dimensions_round_trip(read_json):
    data = read_json("laboratory/vessel_dimensions.json")
    dimensions = VesselDimensions.from_json(data)
    assert dimensions.grasp_height == data[VesselDimensionsKey.GRASP_HEIGHT]
    assert dimensions.to_json() == data
