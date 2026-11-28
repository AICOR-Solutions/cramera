"""
The frames each node of a recorded plan ran in, read from the action and the motion
each frame recorded.
"""

from __future__ import annotations

from cramera_bridge.live.bundles import PlanNodeFrames
from cramera_bridge.live.recording import FrameRange, RecordedFrame
from cramera_protocol.bundle.scene import PlanNodeKind
from cramera_protocol.live_messages import LivePlan, LivePlanNode

PLAN = LivePlan(
    nodes=[
        LivePlanNode(
            identifier="root",
            kind=PlanNodeKind.SEQUENCE,
            label="Sequence",
            status="CREATED",
        ),
        LivePlanNode(
            identifier="pick",
            parent="root",
            kind=PlanNodeKind.ACTION,
            label="PickUp",
            status="SUCCEEDED",
        ),
        LivePlanNode(
            identifier="steps",
            parent="pick",
            kind=PlanNodeKind.SEQUENCE,
            label="Sequence",
            status="CREATED",
        ),
        LivePlanNode(
            identifier="reach",
            parent="steps",
            kind=PlanNodeKind.MOTION,
            label="Reach",
            status="SUCCEEDED",
        ),
        LivePlanNode(
            identifier="close",
            parent="steps",
            kind=PlanNodeKind.MOTION,
            label="Close",
            status="SUCCEEDED",
        ),
        LivePlanNode(
            identifier="lift",
            parent="pick",
            kind=PlanNodeKind.MOTION,
            label="Lift",
            status="SUCCEEDED",
        ),
    ]
)


def frame(action, motion) -> RecordedFrame:
    """
    :param action: The action the frame recorded.
    :param motion: The motion the frame recorded.
    :return: A frame of an empty state.
    """
    return RecordedFrame(
        time=0.0,
        frames={},
        base=None,
        objects={},
        model_bases={},
        action_node=action,
        motion_node=motion,
    )


def test_each_motion_runs_in_its_own_frames_and_its_ancestors_cover_them():
    frames = [
        frame(None, None),
        frame("pick", "reach"),
        frame("pick", "reach"),
        frame("pick", "close"),
        frame(None, "lift"),
        frame(None, None),
    ]
    ranges = PlanNodeFrames(PLAN, frames).ranges()
    assert ranges["reach"] == FrameRange(1, 2)
    assert ranges["close"] == FrameRange(3, 3)
    assert ranges["steps"] == FrameRange(1, 3)
    assert ranges["lift"] == FrameRange(4, 4)
    assert ranges["pick"] == FrameRange(1, 4), "a motion after the action's last report"
    assert ranges["root"] == FrameRange(1, 4)


def test_a_recording_without_motions_gives_the_actions_their_frames_alone():
    frames = [frame("pick", None), frame("pick", None)]
    ranges = PlanNodeFrames(PLAN, frames).ranges()
    assert set(ranges) == {"pick", "root"}
