"""
Publishing how a running plan's open parts were resolved and the queries the process
asks, stepping through those queries and carrying out a resolved plan.
"""

from __future__ import annotations

import json
from http import HTTPStatus

import pytest

from cramera.http.messages import HttpMethod
from cramera_bridge.exceptions import (
    NoQueryStepping,
    NoResolutionExecution,
    ResolutionNotExecutable,
    UnknownResolution,
)
from cramera_bridge.geometry import NumericPose
from cramera_protocol.geometry import Pose, Vector3
from cramera_protocol.live import Capability, LiveRoute
from cramera_protocol.live_messages import LiveParameter
from cramera_protocol.query_steps import (
    HeldStep,
    QueryStep,
    QuerySteps,
    StepAdvance,
    StepMoment,
    StepPhase,
    SteppingRequest,
)
from cramera_protocol.resolutions import (
    BackendDescription,
    ExecutionRequest,
    KnowledgeSource,
    PlanResolution,
    PlanResolutions,
)
from semantic_digital_twin.world_description.geometry import Scale

from ..dataset.regions import RegionOverBody
from ..dataset.stepping import RememberedExecution, RememberedStepControl
from .conftest import live_request

BACKEND = BackendDescription(
    name="WorkingMemory", source=KnowledgeSource.WORKING_MEMORY
)
"""
The backend the published parts and steps are answered by.
"""


def resolutions(*executable: bool) -> PlanResolutions:
    """
    :param executable: Whether each resolution's plan can be carried out.
    :return: One resolution per value, identified by its position.
    """
    return PlanResolutions(
        backends=[BACKEND],
        resolutions=[
            PlanResolution(
                identifier=str(index), title="sort", done=True, executable=can_run
            )
            for index, can_run in enumerate(executable)
        ],
    )


def query_steps(count: int) -> QuerySteps:
    """
    :param count: How many queries were asked.
    :return: The steps, the process held at the last one once it was asked.
    """
    return QuerySteps(
        stepping=True,
        held=HeldStep(number=count - 1, moment=StepMoment.ASKED),
        steps=[
            QueryStep(
                number=number,
                phase=StepPhase.RESOLUTION,
                during="sort",
                moment=StepMoment.ASKED,
                backend=BACKEND,
            )
            for number in range(count)
        ],
    )


# %% resolutions


def test_resolutions_are_offered_once_published(publisher):
    assert Capability.RESOLUTIONS not in publisher.capabilities()
    publisher.resolutions.publish(resolutions(True))
    assert Capability.RESOLUTIONS in publisher.capabilities()
    assert Capability.RESOLUTION_EXECUTION not in publisher.capabilities()


def test_the_newest_resolutions_are_served(publisher, answerer):
    publisher.resolutions.publish(resolutions(True))
    publisher.resolutions.publish(resolutions(True, False))
    answer = answerer.answer(live_request(HttpMethod.GET, LiveRoute.RESOLUTIONS))
    assert PlanResolutions.from_json(json.loads(answer.body)) == resolutions(
        True, False
    )


def test_a_resolved_plan_is_carried_out_on_request(publisher, answerer):
    execution = RememberedExecution()
    publisher.resolutions.publish(resolutions(True), execution)
    request = ExecutionRequest(resolution="0")
    answer = answerer.answer(
        live_request(
            HttpMethod.POST,
            LiveRoute.RESOLUTION_EXECUTION,
            json.dumps(request.to_json()).encode(),
        )
    )
    assert answer.status is HTTPStatus.OK
    assert execution.executed == [request.resolution]
    assert Capability.RESOLUTION_EXECUTION in publisher.capabilities()


def test_a_plan_is_not_carried_out_where_the_process_offers_no_execution(publisher):
    publisher.resolutions.publish(resolutions(True))
    with pytest.raises(NoResolutionExecution):
        publisher.resolutions.execute(ExecutionRequest(resolution="0"))


def test_an_unknown_resolution_is_not_carried_out(publisher):
    execution = RememberedExecution()
    publisher.resolutions.publish(resolutions(True), execution)
    with pytest.raises(UnknownResolution):
        publisher.resolutions.execute(ExecutionRequest(resolution="7"))
    assert execution.executed == []


def test_a_plan_that_cannot_be_carried_out_is_not(publisher):
    execution = RememberedExecution()
    publisher.resolutions.publish(resolutions(False), execution)
    with pytest.raises(ResolutionNotExecutable):
        publisher.resolutions.execute(ExecutionRequest(resolution="0"))
    assert execution.executed == []


# %% query steps


def test_query_steps_are_offered_once_published(publisher):
    assert Capability.QUERY_STEPS not in publisher.capabilities()
    publisher.query_steps.publish(query_steps(1), RememberedStepControl())
    assert {Capability.QUERY_STEPS, Capability.QUERY_STEPPING} <= set(
        publisher.capabilities()
    )


def test_a_recording_keeps_every_step_held_nowhere(publisher):
    assert publisher.query_steps.recorded() is None
    publisher.query_steps.publish(query_steps(2), RememberedStepControl())
    recorded = publisher.query_steps.recorded()
    assert recorded.steps == query_steps(2).steps
    assert (recorded.held, recorded.stepping, recorded.revision) == (None, False, 0)


def test_each_publication_is_a_new_revision(publisher):
    publisher.query_steps.publish(query_steps(1))
    first = publisher.query_steps.current().revision
    publisher.query_steps.publish(query_steps(2))
    assert publisher.query_steps.current().revision == first + 1


def test_a_viewer_showing_the_newest_revision_is_answered_without_the_steps(
    publisher, answerer
):
    publisher.query_steps.publish(query_steps(2))
    revision = publisher.query_steps.current().revision
    answer = answerer.answer(
        live_request(
            HttpMethod.GET,
            LiveRoute.QUERY_STEPS,
            query=f"{LiveParameter.REVISION}={revision}",
        )
    )
    assert QuerySteps.from_json(json.loads(answer.body)) == QuerySteps(
        revision=revision, unchanged=True
    )


def test_a_viewer_showing_an_older_revision_gets_the_steps(publisher, answerer):
    publisher.query_steps.publish(query_steps(2))
    current = publisher.query_steps.current()
    answer = answerer.answer(
        live_request(
            HttpMethod.GET,
            LiveRoute.QUERY_STEPS,
            query=f"{LiveParameter.REVISION}={current.revision - 1}",
        )
    )
    assert QuerySteps.from_json(json.loads(answer.body)) == current


def test_a_revision_that_is_no_number_is_refused(answerer):
    answer = answerer.answer(
        live_request(
            HttpMethod.GET, LiveRoute.QUERY_STEPS, query=f"{LiveParameter.REVISION}=new"
        )
    )
    assert answer.status is HTTPStatus.BAD_REQUEST


def test_the_viewer_moves_a_held_process_on_from_the_step_it_saw(publisher, answerer):
    control = RememberedStepControl()
    publisher.query_steps.publish(query_steps(2), control)
    advance = StepAdvance(held=publisher.query_steps.current().held)
    answerer.answer(
        live_request(
            HttpMethod.POST,
            LiveRoute.QUERY_STEPS_NEXT,
            json.dumps(advance.to_json()).encode(),
        )
    )
    assert control.advanced_from == [advance.held]


def test_the_viewer_changes_how_the_process_is_held(publisher, answerer):
    control = RememberedStepControl()
    publisher.query_steps.publish(query_steps(1), control)
    request = SteppingRequest(stepping=False, holds_nested=False)
    answerer.answer(
        live_request(
            HttpMethod.POST,
            LiveRoute.QUERY_STEPS_MODE,
            json.dumps(request.to_json()).encode(),
        )
    )
    assert control.stepping_changes == [request]


def test_a_process_that_cannot_be_held_is_not_stepped(publisher):
    publisher.query_steps.publish(query_steps(1))
    with pytest.raises(NoQueryStepping):
        publisher.query_steps.advance(StepAdvance())


# %% scene highlights


def test_bodies_light_up_under_their_keys_and_frame_the_camera(publisher, kitchen):
    highlight = publisher.scene_highlight([kitchen.milk, kitchen.table], [kitchen.milk])
    assert highlight.keys == [str(kitchen.milk.id), str(kitchen.table.name)]
    assert highlight.framed == [str(kitchen.milk.id)]
    assert highlight.regions == []


def test_a_region_is_outlined_where_its_area_is(publisher, kitchen):
    height, box_offset, size = 0.2, 0.1, Scale(0.2, 0.1, 0.05)
    region = RegionOverBody.build(
        kitchen.world, kitchen.table, height, box_offset, size
    ).region
    highlight = publisher.scene_highlight([region], [region])
    table = NumericPose.of_entity(kitchen.world, kitchen.table)
    outline = highlight.regions[0]
    assert outline.identifier == str(region.name)
    assert outline.pose == Pose(
        table.position[0] + box_offset,
        table.position[1],
        table.position[2] + height,
        *table.quaternion,
    )
    assert outline.size == Vector3(size.x, size.y, size.z)
    assert highlight.keys == []
    assert highlight.framed == [str(region.name)]
