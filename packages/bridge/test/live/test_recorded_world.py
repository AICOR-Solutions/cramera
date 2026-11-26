"""
A recording keeps the world it ran in, and a recorded scene is asked about in that very
world at the frame the viewer shows, with the desk its live run answered with.
"""

from __future__ import annotations

from cramera.scenes import SceneCatalog, SceneDirectory, SceneSource
from cramera_bridge.documents import DocumentFile
from cramera_bridge.questions.recorded.replayed_world import ReplayedWorld
from cramera_bridge.questions.scenes import RecordedSceneQuestions
from cramera_bridge.questions.workspace_classes import WorkspaceClassIndex
from cramera_bridge.scenes.world_history import WorldHistory
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.index import ReservedSceneName
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.live_messages import RecordingSaveRequest
from cramera_protocol.questions import QueryRequest, QueryScope

from .test_recording import FRAME_COUNT, carry_milk

MOVED_AWAY = """
moved = a(Body).from_(domain=scene_object)
moved.where(moved.global_pose.x > 1.25)
"""
"""
Asks which free object stands beyond x = 1.25, which the milk passes at frame 3.
"""


def recorded_history(locations, scene: str) -> WorldHistory:
    """
    :return: The world history a bundle of the local scenes keeps.
    """
    bundle = locations.local_scenes / scene
    description = DocumentFile(bundle / BundleFile.SCENE).read(SceneDescription)
    return WorldHistory.read(bundle / description.world_history)


def milk_x_at(history: WorldHistory, frame: int, kitchen) -> float:
    """
    :return: Where the rebuilt world has the milk along x at a frame.
    """
    replayed = ReplayedWorld(history)
    replayed.show(frame)
    milk = replayed.world.get_kinematic_structure_entity_by_id(kitchen.milk.id)
    return float(milk.global_pose.to_np()[0, 3])


def test_a_recording_keeps_the_world_it_ran_in(publisher, kitchen, locations):
    carry_milk(kitchen, publisher)
    publisher.finish_recording()
    history = recorded_history(locations, ReservedSceneName.RECORDING)
    assert len(history.frames) == publisher.recording.frame_count()
    assert history.versions[-1].block_count == len(kitchen.world.modification_history)


def test_the_rebuilt_world_is_the_recorded_one_at_each_frame(
    publisher, kitchen, locations
):
    carry_milk(kitchen, publisher)
    publisher.finish_recording()
    history = recorded_history(locations, ReservedSceneName.RECORDING)
    replayed = ReplayedWorld(history)
    replayed.show(0)
    assert sorted(str(body.name) for body in replayed.world.bodies) == sorted(
        str(body.name) for body in kitchen.world.bodies
    )
    assert sorted(
        (type(annotation).__name__, str(annotation.name))
        for annotation in replayed.world.semantic_annotations
    ) == sorted(
        (type(annotation).__name__, str(annotation.name))
        for annotation in kitchen.world.semantic_annotations
    )
    first = history.frames.index(
        next(
            frame
            for frame in history.frames
            if frame.positions != history.frames[0].positions
        )
    )
    assert milk_x_at(history, FRAME_COUNT - 1, kitchen) > milk_x_at(
        history, first - 1, kitchen
    )


def test_a_saved_recording_keeps_the_world_of_its_kept_frames(
    publisher, kitchen, locations
):
    carry_milk(kitchen, publisher)
    publisher.finish_recording()
    whole = recorded_history(locations, ReservedSceneName.RECORDING)
    saved = publisher.save_recording(
        RecordingSaveRequest(name="carry", first_frame=2, last_frame=4)
    )
    history = recorded_history(locations, saved.scene)
    assert history.frames == whole.frames[2:5]


def test_a_recorded_scene_is_asked_with_the_live_desk_at_the_shown_frame(
    publisher, kitchen, locations
):
    carry_milk(kitchen, publisher)
    publisher.finish_recording()
    saved = publisher.save_recording(RecordingSaveRequest(name="carry"))
    questions = RecordedSceneQuestions.of_catalog(
        SceneCatalog([SceneDirectory(locations.local_scenes, SceneSource.LOCAL)]),
        WorkspaceClassIndex(),
    )
    catalog = questions.preset_catalog(saved.scene)
    assert [scope.name for scope in catalog.scopes] == [QueryScope.CURRENT_STATE]
    history = recorded_history(locations, saved.scene)
    frames_beyond = [
        frame
        for frame in range(len(history.frames))
        if milk_x_at(history, frame, kitchen) > 1.25
    ]
    assert frames_beyond and frames_beyond[0] > 0
    before, after = frames_beyond[0] - 1, frames_beyond[0]
    asked = [
        questions.answer_query(
            saved.scene,
            QueryRequest(code=MOVED_AWAY, scope=QueryScope.CURRENT_STATE, frame=frame),
        )
        for frame in (before, after)
    ]
    assert all(answer.ok for answer in asked), [answer.error for answer in asked]
    assert asked[0].count == 0
    assert asked[1].count == 1
    assert str(kitchen.milk.id) in asked[1].highlight
