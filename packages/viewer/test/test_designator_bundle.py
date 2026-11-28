"""
The chain the Designators layout shows, checked on the shipped PR2 laboratory workflow:
each role of a designator names entities the scene has, the vessels and handles are
named by the entity queries the run asked, with the frame each was asked at, and the
locations the vessels are set down at are poses the plan computed, not answers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typing_extensions import Any, Dict, Iterator, List

from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.designator_roles import DesignatorRole, RoleSource
from cramera_protocol.query_steps import StepPhase
from cramera_protocol.resolutions import KnowledgeSource

BUNDLE = (
    Path(__file__).resolve().parents[3]
    / "demo"
    / "standard_scenes"
    / "aicor_medical_lab_pr2_workflow"
)
"""
The recorded workflow.
"""

RACK = "laboratory_rack"
"""
The body the rack's slots are given in.
"""

ROTOR = "laboratory_centrifuge_rotor"
"""
The body the centrifuge's holders are given in.
"""

REFRIGERATOR = "laboratory_refrigerator_base"
"""
The body the refrigerator's holders are given in.
"""


@pytest.fixture(scope="module")
def scene() -> Dict[str, Any]:
    """
    :return: The workflow's scene description.
    """
    return json.loads((BUNDLE / BundleFile.SCENE).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def steps(scene) -> List[Dict[str, Any]]:
    """
    :return: The queries the run asked.
    """
    document = json.loads((BUNDLE / scene["querySteps"]).read_text(encoding="utf-8"))
    return document["steps"]


def nodes(roots: List[Dict[str, Any]]) -> Iterator[Dict[str, Any]]:
    """
    :param roots: Plan trees.
    :return: Every node, in plan order.
    """
    for root in roots:
        yield root
        yield from nodes(root.get("children", []))


def top_level_actions(scene) -> List[Dict[str, Any]]:
    """
    :param scene: A scene description.
    :return: The actions no action encloses.
    """
    found = []

    def visit(node):
        if node["kind"] == "action":
            found.append(node)
        else:
            for child in node.get("children", []):
                visit(child)

    for root in scene["planTrees"]:
        visit(root)
    return found


def identity(entity: Dict[str, Any]) -> str:
    """
    :param entity: An entity a role or an answer names.
    :return: The keys it lights up, as the layout matches them.
    """
    return "|".join(sorted(set(entity["keys"])))


def role(node: Dict[str, Any], field: str) -> Dict[str, Any]:
    """
    :param node: A plan node.
    :param field: One of its fields.
    :return: The role the field fills.
    """
    return next(slot for slot in node["roles"] if slot["field"] == field)


def test_every_entity_a_role_names_is_shown_by_the_scene(scene):
    known = {item["key"] for item in scene["objects"]} | set(scene["classes"]["bodies"])
    named = {
        key
        for node in nodes(scene["planTrees"])
        for slot in node.get("roles", [])
        for entity in slot["entities"]
        + ([slot["reference"]] if slot.get("reference") else [])
        for key in entity["keys"]
    }
    assert named and named <= known


def test_every_action_names_the_robot_of_its_context_as_its_agent(scene):
    for action in top_level_actions(scene):
        agent = role(action, "robot")
        assert agent["role"] == DesignatorRole.AGENT
        assert agent["source"] == RoleSource.CONTEXT


def test_every_slot_a_vessel_is_set_into_is_given_in_its_stations_frame(
    scene,
):
    places = [a for a in top_level_actions(scene) if a["label"] == "RackPlaceAction"]
    references = [role(a, "target_location")["reference"]["name"] for a in places]
    assert references.count(RACK) == 3
    assert references.count(ROTOR) == 2
    assert references.count(REFRIGERATOR) == 1
    for action in places:
        assert role(action, "target_location")["role"] == DesignatorRole.LOCATION


def test_each_vessel_picked_up_was_named_by_a_query_asked_before_the_pick_up(
    scene, steps
):
    pick_ups = [
        a for a in top_level_actions(scene) if a["label"] == "VesselPickUpAction"
    ]
    assert len(pick_ups) == 6
    for action in pick_ups:
        (vessel,) = role(action, "grasp.graspable")["entities"]
        naming = [
            step
            for step in steps
            if any(identity(e) == identity(vessel) for e in step["entities"])
        ]
        assert naming, vessel["name"]
        assert min(step["frame"] for step in naming) <= action["start"]


def test_the_handles_taken_were_named_by_queries(scene, steps):
    answered = {identity(e) for step in steps for e in step["entities"]}
    graspings = [a for a in top_level_actions(scene) if a["label"] == "GraspingAction"]
    assert graspings
    for action in graspings:
        (handle,) = role(action, "grasp.graspable")["entities"]
        assert identity(handle) in answered, handle["name"]


def test_no_query_answered_where_a_vessel_is_set_down(scene, steps):
    answered = {identity(e) for step in steps for e in step["entities"]}
    for action in top_level_actions(scene):
        if action["label"] != "RackPlaceAction":
            continue
        slot = role(action, "target_location")
        assert slot["entities"] == []
        assert identity(slot["reference"]) not in answered


def test_every_query_was_answered_from_working_memory_while_the_plan_was_built(
    scene, steps
):
    first_motion = min(a["start"] for a in top_level_actions(scene))
    assert steps
    for step in steps:
        assert step["backend"]["name"] == "EntityQueryLanguageBackend"
        assert step["backend"]["source"] == KnowledgeSource.WORKING_MEMORY
        assert step["phase"] in (StepPhase.SETUP, StepPhase.EXPANSION)
        assert step.get("planNode") is None
        assert step["frame"] <= first_motion


def test_every_location_a_vessel_is_set_down_at_is_named_by_its_slot(scene):
    places = [
        role(action, "target_location").get("place")
        for action in top_level_actions(scene)
        if action["label"] == "RackPlaceAction"
    ]
    assert places == [
        "rack A3",
        "rack A1",
        "rack B1",
        "refrigerator R6",
        "centrifuge C4",
        "centrifuge C2",
    ]


def test_no_pose_but_a_slot_is_named(scene):
    named = [
        slot
        for node in nodes(scene["planTrees"])
        for slot in node.get("roles", [])
        if slot.get("place")
    ]
    assert {slot["field"] for slot in named} == {"target_location"}


def test_the_stepped_transfer_sets_its_vessel_into_the_rack_slot_a_query_did_not_name():
    bundle = BUNDLE.parent / "aicor_medical_lab_pr2_query_stepper"
    scene = json.loads((bundle / BundleFile.SCENE).read_text(encoding="utf-8"))
    steps = json.loads((bundle / scene["querySteps"]).read_text(encoding="utf-8"))
    pick_up, place = top_level_actions(scene)
    (vessel,) = role(pick_up, "grasp.graspable")["entities"]
    naming = [
        step["number"]
        for step in steps["steps"]
        if any(identity(e) == identity(vessel) for e in step["entities"])
    ]
    target = role(place, "target_location")
    assert naming == [2]
    assert target["place"] == "rack A3"
    assert target["entities"] == []
    assert target["reference"]["name"] == RACK


LAYOUT = (
    Path(__file__).resolve().parents[2]
    / "plugins/laboratory/src/cramera_laboratory/resources/aicor_medical_lab/scene.json"
)
"""
The bench layout the workflow's holders come from.
"""


def test_a_location_carries_its_pose_in_its_references_frame_as_the_layout_gives_it(
    scene,
):
    layout = json.loads(LAYOUT.read_text(encoding="utf-8"))["laboratory"]
    holders = {
        f"centrifuge {slot['id']}": slot["position"]
        for slot in layout["centrifuge"]["slots"]
    } | {
        f"refrigerator {slot['id']}": slot["localPosition"]
        for slot in layout["refrigerator"]["slots"]
    }
    located = [
        slot
        for node in nodes(scene["planTrees"])
        for slot in node.get("roles", [])
        if slot.get("reference")
    ]
    assert located and all(len(slot["pose"]) == 7 for slot in located)
    for slot in located:
        if slot.get("place") in holders:
            assert slot["pose"][:3] == pytest.approx(holders[slot["place"]], abs=1e-6)
