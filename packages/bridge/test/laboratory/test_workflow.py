"""
The PR2 laboratory workflow, run once in simulation, recorded and measured.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from cramera.locations import DataLocations
from cramera_bridge.exceptions import TaskFailed
from cramera_bridge.laboratory.transfer import PENETRATION_TOLERANCE
from cramera_bridge.laboratory.workflow import (
    CLOSED_TOLERANCE,
    OPENED_TOLERANCE,
    RACK_STAND,
    TASK,
    LaboratoryWorkflowDemo,
    WorkflowMeasurement,
)
from cramera_protocol.bundle.acceptance import AcceptanceMetrics
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import SceneDescription


@pytest.fixture(scope="module")
def workflow(tmp_path_factory, laboratory_bundle):
    """
    :return: The workflow after one run, and the bundle it saved.
    """
    data = tmp_path_factory.mktemp("data")
    demo = LaboratoryWorkflowDemo.at_the_bench(
        laboratory_bundle,
        locations=DataLocations(data=data, shared_scenes=None),
        port=0,
    )
    saved = demo.run()
    return demo, demo.locations.local_scenes / saved.scene


@pytest.fixture(scope="module")
def measurements(workflow):
    """
    :return: The measurements saved beside the recording.
    """
    _, bundle = workflow
    return AcceptanceMetrics.from_json(
        json.loads((bundle / BundleFile.ACCEPTANCE_METRICS).read_text())
    ).measurements


def test_every_moved_vessel_is_set_down_in_its_new_slot(workflow, measurements):
    demo, _ = workflow
    assert (
        measurements[WorkflowMeasurement.RACK_POSITION_ERROR]
        <= 2 * demo.position_tolerance
    )


def test_the_door_and_the_lid_were_opened_and_are_closed_again(workflow, measurements):
    demo, _ = workflow
    assert measurements[WorkflowMeasurement.WIDEST_DOOR] >= (
        demo.door_open - OPENED_TOLERANCE
    )
    assert measurements[WorkflowMeasurement.WIDEST_LID] >= (
        demo.lid_pushed - OPENED_TOLERANCE
    )
    assert abs(measurements[WorkflowMeasurement.DOOR]) <= CLOSED_TOLERANCE
    assert abs(measurements[WorkflowMeasurement.LID]) <= CLOSED_TOLERANCE


def test_the_pads_never_cut_into_the_glass(measurements):
    assert (
        measurements[WorkflowMeasurement.SMALLEST_PAD_CLEARANCE]
        >= -PENETRATION_TOLERANCE
    )


def test_the_pr2_ends_where_it_started(workflow):
    demo, _ = workflow
    context = demo.observation.context
    np.testing.assert_allclose(
        context.robot.root.global_pose.to_np(),
        RACK_STAND.pose(context.world).to_np(),
        atol=0.003,
    )


def test_the_recording_names_the_task_and_the_environment(workflow):
    demo, bundle = workflow
    scene = SceneDescription.from_json(
        json.loads((bundle / BundleFile.SCENE).read_text())
    )
    assert scene.task == TASK
    assert scene.environment_name == demo.environment_name
    assert scene.camera == demo.camera


def test_vessels_set_down_in_another_order_fail_the_task(workflow):
    demo, _ = workflow
    released = list(demo.observation.released)
    demo.observation.released.reverse()
    try:
        with pytest.raises(TaskFailed):
            demo.measure(demo.observation.context)
    finally:
        demo.observation.released[:] = released
