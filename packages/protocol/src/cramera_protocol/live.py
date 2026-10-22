"""
The live protocol: what a running CRAM process offers the viewer over HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import List, Optional

from cramera_protocol.document import JsonDocument, document_field
from cramera_protocol.version import CURRENT_VERSION, ProtocolVersion

# %% routes


class LiveRoute(StrEnum):
    """
    The routes of a live publisher.
    """

    INFO = "/info"
    """
    The publisher's protocol version and capabilities.
    """

    STATE = "/state"
    """
    The current joint values and object poses.
    """

    ROBOTS = "/robots"
    """
    The robot instances of the world.
    """

    ROBOT = "/robot"
    """
    Selects the robot the live controls act on.
    """

    PLAN = "/plan"
    """
    The executing plan.
    """

    STATECHART = "/chart"
    """
    The motion statechart being ticked.
    """

    TRANSFORMS = "/transforms"
    """
    Every connection of the world with its pose.
    """

    OBJECTS = "/objects"
    """
    The free objects of the world with their shapes.
    """

    CAPTURED_OBJECTS = "/captured_objects"
    """
    The objects a robot holds.
    """

    SURFACES = "/surfaces"
    """
    The surfaces objects can be placed on.
    """

    MESH = "/mesh"
    """
    A mesh file the world references.
    """

    LIVE_SCENE = "/live_scene"
    """
    Bundles the world's current model into the live scene.
    """

    MARKERS = "/markers"
    """
    The debug markers the process publishes.
    """

    MARKER_TOPICS = "/marker_topics"
    """
    The ROS topics markers are read from.
    """

    PRESETS = "/presets"
    """
    Ready-made questions about the running world.
    """

    VOCABULARY = "/vocabulary"
    """
    The names a question may use.
    """

    MEMBERS = "/members"
    """
    The attributes of a class a question may use.
    """

    QUERY = "/eql"
    """
    Answers a query in the entity query language.
    """

    QUESTION = "/question"
    """
    Answers a question in plain language.
    """

    RECORDING = "/recording"
    """
    The state of the current recording.
    """

    RECORDING_STOP = "/recording/stop"
    """
    Ends the current recording.
    """

    RECORDING_SAVE = "/recording/save"
    """
    Saves the ended recording as a scene bundle.
    """

    RECORDING_DISCARD = "/recording/discard"
    """
    Throws the ended recording away.
    """

    CONSTRAINT = "/constraint"
    """
    Adds a constraint to the next plan.
    """

    JOINT = "/joint"
    """
    Sets a joint value of the robot.
    """

    TELEOPERATION = "/teleop"
    """
    Moves the robot's hand interactively.
    """

    TELEOPERATION_STOP = "/teleop/stop"
    """
    Ends interactive hand motion.
    """

    MOVE = "/move"
    """
    Moves a free object.
    """


# %% address

LIVE_HOST = "127.0.0.1"
"""
The address a live publisher listens on: this machine only, since a query runs code.
"""

LIVE_PORT = 8765
"""
The port a live publisher listens on unless told otherwise, where the viewer looks for
it.
"""

# %% capabilities


class Capability(StrEnum):
    """
    What a publisher offers; the viewer shows a panel only when its capability is
    offered.
    """

    PLAN = "plan"
    """
    The executing plan is published.
    """

    STATECHART = "statechart"
    """
    The motion statechart is published.
    """

    TRANSFORMS = "transforms"
    """
    The connection poses are published.
    """

    MARKERS = "markers"
    """
    Debug markers are published.
    """

    QUESTIONS = "questions"
    """
    Questions about the world are answered.
    """

    RECORDING = "recording"
    """
    The run can be recorded and saved.
    """

    TELEOPERATION = "teleoperation"
    """
    The robot can be moved by hand.
    """

    CONSTRAINTS = "constraints"
    """
    Constraints can be added to the next plan.
    """

    OBJECT_PLACEMENT = "object_placement"
    """
    Free objects can be moved by hand.
    """

    ROBOT_SELECTION = "robot_selection"
    """
    One of several robots can be selected.
    """


# %% information


class LiveInfoKey(StrEnum):
    """
    The keys of the answer to :attr:`LiveRoute.INFO`.
    """

    PROTOCOL_VERSION = "protocolVersion"
    """
    The protocol version the publisher speaks.
    """

    PUBLISHER = "publisher"
    """
    The name and version of the publishing package.
    """

    CAPABILITIES = "capabilities"
    """
    What the publisher offers.
    """

    SCENE = "scene"
    """
    The bundle that shows the publisher's world.
    """

    RUNNING = "running"
    """
    Whether a world is attached.
    """

    BUNDLE_SIGNATURE = "bundleSignature"
    """
    The identity of the world model the live bundle shows.
    """


@dataclass(kw_only=True)
class LiveInfo(JsonDocument):
    """
    What a live publisher says about itself.
    """

    protocol_version: ProtocolVersion = document_field(
        LiveInfoKey.PROTOCOL_VERSION, default=CURRENT_VERSION
    )
    """
    The protocol version the publisher speaks.
    """

    publisher: str = document_field(LiveInfoKey.PUBLISHER)
    """
    The name and version of the publishing package.
    """

    capabilities: List[Capability] = document_field(
        LiveInfoKey.CAPABILITIES, default_factory=list
    )
    """
    What the publisher offers.
    """

    scene: Optional[str] = document_field(LiveInfoKey.SCENE, default=None)
    """
    The bundle that shows the publisher's world, once it exists.
    """

    running: bool = document_field(LiveInfoKey.RUNNING, default=False)
    """
    Whether the publisher is attached to a world.
    """

    bundle_signature: Optional[str] = document_field(
        LiveInfoKey.BUNDLE_SIGNATURE, default=None
    )
    """
    The identity of the world model; when it differs from
    :attr:`~cramera_protocol.bundle.scene.SceneDescription.bundle_signature` of the
    loaded live bundle, the bundle is out of date.
    """

    def __post_init__(self) -> None:
        self.protocol_version.require_readable_by(CURRENT_VERSION)
