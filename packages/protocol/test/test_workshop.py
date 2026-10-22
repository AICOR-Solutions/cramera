"""
The documents of the woodworking workshop: its scene description, the commands of its
contact simulation and the state that simulation measures.
"""

from __future__ import annotations

import json

import pytest

from cramera_protocol.browser import BROWSER_ENUMERATIONS
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.exceptions import InvalidDocumentValue, MissingDocumentField
from cramera_protocol.rights import AssetRights
from cramera_protocol.workshop import (
    COMMAND_ARGUMENTS,
    DriveDirection,
    InvalidWorkshopCommand,
    ThreadState,
    WorkshopAction,
    WorkshopCommand,
    WorkshopCommandKey,
    WorkshopDescription,
    WorkshopPartKind,
    WorkshopSceneKey,
    WorkshopSemantics,
    WorkshopSemanticsKey,
    WorkshopState,
    WorkshopStateKey,
    WorkshopView,
)

# %% scene description


@pytest.fixture
def scene(read_json) -> SceneDescription:
    """
    :return: The scene description of the AICOR workshop bundle.
    """
    return SceneDescription.from_json(read_json("workshop/workshop_scene.json"))


def test_a_workshop_scene_carries_its_description_as_plugin_content(read_json, scene):
    data = read_json("workshop/workshop_scene.json")[WorkshopSceneKey.WORKSHOP]
    workshop = WorkshopDescription.of_scene(scene.extensions)
    assert [drawer.joint for drawer in workshop.drawers] == [
        drawer["joint"] for drawer in data["drawers"]
    ]
    assert workshop.assembly.maximum_depth == data["assembly"]["maximumDepth"]
    assert workshop.screw.thread_pitch == data["screw"]["threadPitch"]
    assert set(workshop.cameras) == {view.value for view in WorkshopView}
    assert WorkshopDescription.from_json(workshop.to_json()) == workshop


def test_the_screws_are_the_parts_of_the_screw_kind(scene):
    workshop = WorkshopDescription.of_scene(scene.extensions)
    screws = workshop.screws()
    assert screws == [
        part.key for part in workshop.parts if part.kind is WorkshopPartKind.SCREW
    ]
    assert len(screws) < len(workshop.parts)


def test_every_movable_body_of_the_workshop_is_an_object_of_the_scene(scene):
    workshop = WorkshopDescription.of_scene(scene.extensions)
    assert sorted(workshop.movable_keys()) == sorted(
        description.key for description in scene.objects
    )


def test_a_scene_without_a_workshop_describes_none():
    assert WorkshopDescription.of_scene({}) is None
    assert AssetRights.of_scene({}, WorkshopSceneKey.ASSET_RIGHTS) is None


def test_the_asset_rights_name_the_licence_and_its_files(read_json, scene):
    data = read_json("workshop/workshop_scene.json")[WorkshopSceneKey.ASSET_RIGHTS]
    rights = AssetRights.of_scene(scene.extensions, WorkshopSceneKey.ASSET_RIGHTS)
    assert rights.license_identifier == data["license"]
    assert rights.to_json() == data


def test_the_semantics_list_the_handles(read_json):
    data = read_json("workshop/workshop_semantics.json")
    semantics = WorkshopSemantics.from_json(data)
    assert semantics.handles == data[WorkshopSemanticsKey.HANDLES]
    assert semantics.to_json() == data


# %% commands


def test_a_grab_names_the_body(read_json):
    data = read_json("workshop/grab.json")
    command = WorkshopCommand.from_json(data)
    assert command.action is WorkshopAction.GRAB
    assert command.object_key == data[WorkshopCommandKey.OBJECT]
    assert command.to_json() == data


def test_a_move_keeps_its_quaternion_as_given(read_json):
    data = read_json("workshop/move.json")
    command = WorkshopCommand.from_json(data)
    assert command.pose.to_json() == data[WorkshopCommandKey.POSE]


def test_a_drive_names_its_direction(read_json):
    command = WorkshopCommand.from_json(read_json("workshop/drive.json"))
    assert command.direction is DriveDirection.FORWARD


def test_a_drawer_command_names_joint_and_target(read_json):
    data = read_json("workshop/drawer.json")
    command = WorkshopCommand.from_json(data)
    assert (command.joint, command.position) == (
        data[WorkshopCommandKey.JOINT],
        data[WorkshopCommandKey.POSITION],
    )


@pytest.mark.parametrize(
    "file_name",
    [
        "grab_without_object.json",
        "grab_with_empty_object.json",
        "pause_with_pose.json",
        "move_with_zero_quaternion.json",
        "move_with_infinite_height.json",
        "drawer_with_infinite_position.json",
    ],
)
def test_a_command_that_does_not_fit_its_action_is_refused(read_json, file_name):
    with pytest.raises(InvalidWorkshopCommand):
        WorkshopCommand.from_json(read_json(f"workshop/{file_name}"))


def test_a_drive_by_number_is_refused(read_json):
    with pytest.raises(InvalidDocumentValue):
        WorkshopCommand.from_json(read_json("workshop/drive_with_turn_count.json"))


def test_actions_without_arguments_take_only_the_action():
    for action in WorkshopAction:
        if action in COMMAND_ARGUMENTS:
            continue
        assert WorkshopCommand(action=action).to_json() == {
            WorkshopCommandKey.ACTION: action.value
        }


def test_the_refusal_names_the_action(read_json):
    with pytest.raises(InvalidWorkshopCommand) as refused:
        WorkshopCommand.from_json(read_json("workshop/pause_with_pose.json"))
    assert refused.value.action is WorkshopAction.PAUSE
    assert WorkshopAction.PAUSE.value in refused.value.message()


# %% state


def test_the_state_reads_poses_contacts_and_the_thread(read_json):
    data = read_json("workshop/state.json")
    state = WorkshopState.from_json(data)
    assert state.objects["screw_1"].to_json() == data["objects"]["screw_1"]
    assert state.contacts[0].force == data["contacts"][0]["force"]
    assert state.thread.state is ThreadState.FREE
    assert state.error is None
    assert WorkshopState.from_json(state.to_json()) == state


def test_a_state_before_the_simulation_exists_is_empty_and_available():
    data = WorkshopState().to_json()
    assert WorkshopStateKey.THREAD not in data
    assert data[WorkshopStateKey.AVAILABLE] is True
    assert data[WorkshopStateKey.OBJECTS] == {}


def test_a_thread_in_an_unknown_state_is_refused(read_json):
    with pytest.raises(InvalidDocumentValue):
        WorkshopState.from_json(
            read_json("workshop/state_with_unknown_thread_state.json")
        )


def test_a_workshop_without_drawers_is_refused(read_json):
    data = read_json("workshop/workshop_scene.json")[WorkshopSceneKey.WORKSHOP]
    del data["drawers"]
    with pytest.raises(MissingDocumentField):
        WorkshopDescription.from_json(json.loads(json.dumps(data)))


# %% names


def test_the_browser_reads_the_workshop_names():
    for enumeration in (
        WorkshopAction,
        WorkshopCommandKey,
        DriveDirection,
        WorkshopStateKey,
        ThreadState,
        WorkshopSceneKey,
        WorkshopView,
    ):
        assert enumeration in BROWSER_ENUMERATIONS
