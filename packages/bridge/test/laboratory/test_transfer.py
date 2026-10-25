"""
The PR2 vessel transfer, run once in simulation, recorded and measured.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from cramera.locations import DataLocations
from cramera_bridge.exceptions import SceneNameTaken, TaskFailed
from cramera_bridge.laboratory.grasping import (
    GraspGeometryError,
    GraspProblem,
    PadContact,
)
from cramera_bridge.laboratory.transfer import (
    TASK,
    TransferMeasurement,
    VesselTransferDemo,
)
from cramera_protocol.bundle.acceptance import AcceptanceMetrics
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import SceneDescription


@pytest.fixture(scope="module")
def transfer(tmp_path_factory, laboratory_bundle):
    """
    :return: The transfer demo after one run, and the bundle it saved.
    """
    data = tmp_path_factory.mktemp("data")
    demo = VesselTransferDemo.at_the_bench(
        laboratory_bundle,
        locations=DataLocations(data=data, shared_scenes=None),
        port=0,
    )
    saved = demo.run()
    return demo, demo.locations.local_scenes / saved.scene


def test_the_vessel_is_placed_into_the_target_slot(transfer):
    demo, bundle = transfer
    metrics = AcceptanceMetrics.from_json(
        json.loads((bundle / BundleFile.ACCEPTANCE_METRICS).read_text())
    ).measurements
    assert metrics[TransferMeasurement.POSITION_ERROR] <= 2 * demo.position_tolerance
    assert (
        metrics[TransferMeasurement.MAXIMUM_LIFT] >= demo.lift - demo.position_tolerance
    )
    assert metrics[TransferMeasurement.CARRIED_TICKS] > 0
    assert metrics[TransferMeasurement.SMALLEST_PAD_CLEARANCE] >= 0


def test_the_recording_names_the_task_and_the_environment(transfer):
    demo, bundle = transfer
    scene = SceneDescription.from_json(
        json.loads((bundle / BundleFile.SCENE).read_text())
    )
    assert scene.task == TASK
    assert scene.environment_name == demo.environment_name
    assert scene.camera == demo.camera


def test_a_vessel_never_carried_fails_the_task(transfer):
    demo, _ = transfer
    carried = demo.observation.carried_ticks
    demo.observation.carried_ticks = 0
    with pytest.raises(TaskFailed):
        demo.measure(demo.observation.context)
    demo.observation.carried_ticks = carried


def test_invalid_contact_tolerances_are_refused(transfer):
    demo, _ = transfer
    context = demo.observation.context
    with pytest.raises(GraspGeometryError) as refused:
        PadContact(
            context.world,
            context.robot.left_arm.end_effector,
            demo.observation.body,
            clearance=-1.0,
        )
    assert refused.value.problem is GraspProblem.TOLERANCES


def test_an_open_gripper_far_from_the_glass_finds_no_contact(transfer):
    demo, _ = transfer
    context = demo.observation.context
    contact = PadContact(
        context.world, context.robot.right_arm.end_effector, demo.observation.body
    )
    with pytest.raises(GraspGeometryError) as refused:
        contact.stop_position()
    assert refused.value.problem is GraspProblem.NO_CONTACT


# %% live announcement


@dataclass(frozen=True)
class ListeningAddress:
    """
    The address reported by a listening visualization.
    """

    address: str
    """
    The real port assigned when the visualization starts.
    """

    def url(self) -> str:
        """
        :return: The listening address.
        """
        return self.address


def test_transfer_announces_the_started_visualization_address(
    laboratory_bundle, tmp_path
):
    announcement = tmp_path / "live" / "address"
    demo = VesselTransferDemo.at_the_bench(
        laboratory_bundle, live_url_file=announcement
    )
    visualization = ListeningAddress("http://127.0.0.1:54321/")
    demo.on_live_started(visualization)
    assert announcement.read_text() == visualization.address


def test_transfer_clears_an_old_live_address_even_if_start_fails(
    laboratory_bundle, tmp_path
):
    announcement = tmp_path / "address"
    demo = VesselTransferDemo.at_the_bench(
        laboratory_bundle,
        live_url_file=announcement,
        locations=DataLocations(data=tmp_path / "data", shared_scenes=None),
    )
    (demo.locations.local_scenes / demo.name).mkdir(parents=True)
    announcement.write_text("http://127.0.0.1:54321/")
    with pytest.raises(SceneNameTaken):
        demo.run()
    assert not announcement.exists()
