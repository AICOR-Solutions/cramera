"""
The roles the fields of an action designator fill: which entities of the semantic
digital twin each field names, read from the designator itself.

A role is cramera's reading of a field, not a name CRAM defines: CRAM's action
designators have fields, such as an object designator or a target location, and take
the robot that performs them from the plan's context. The roles group those fields as
the agent, the object acted on, the effector it is acted on with and the location it is
acted at, so that actions with different fields can be shown alike.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import List, Optional

from cramera_protocol.document import JsonDocument, document_field


class DesignatorRole(StrEnum):
    """
    What a field of an action designator stands for in the action.
    """

    AGENT = "agent"
    """
    Who performs the action: the robot of the plan's context.
    """

    OBJECT = "object"
    """
    What the action acts on: what is taken, moved, opened or set down.
    """

    EFFECTOR = "effector"
    """
    The part of the agent the action acts with, such as an arm or a gripper.
    """

    LOCATION = "location"
    """
    Where the action acts: a pose the robot, its tool or the object is brought to.
    """

    INSTRUMENT = "instrument"
    """
    What the action acts by means of, other than the agent's own parts.
    """


class RoleSource(StrEnum):
    """
    Where a role's filler comes from.
    """

    FIELD = "field"
    """
    A field of the designator.
    """

    CONTEXT = "context"
    """
    The plan's context, which the designator does not name.
    """


class RoleEntityKey(StrEnum):
    """
    The keys of an entity a role names.
    """

    KEYS = "keys"
    """
    What the scene knows the entity's bodies by.
    """

    NAME = "name"
    """
    The entity's name in the world.
    """

    TYPE = "type"
    """
    The entity's class.
    """


@dataclass(kw_only=True)
class RoleEntity(JsonDocument):
    """
    An entity of the semantic digital twin that a role names: a body, a semantic
    annotation or a robot part.
    """

    keys: List[str] = document_field(RoleEntityKey.KEYS, default_factory=list)
    """
    What the scene lights up for the entity, as a query's highlight names it: a free
    object's published key, any other body's name, an annotation's bodies.
    """

    name: str = document_field(RoleEntityKey.NAME)
    """
    The entity's name in the world.
    """

    type_name: str = document_field(RoleEntityKey.TYPE)
    """
    The class name of the entity, such as Body, Handle or PR2LeftArm.
    """


class RoleSlotKey(StrEnum):
    """
    The keys of one role of an action designator.
    """

    FIELD = "field"
    """
    The designator's field.
    """

    ROLE = "role"
    """
    The role the field fills.
    """

    SOURCE = "source"
    """
    Where the role's filler comes from.
    """

    VALUE = "value"
    """
    The field's value as read.
    """

    ENTITIES = "entities"
    """
    The entities the value names.
    """

    REFERENCE = "reference"
    """
    The entity a pose is given relative to.
    """


@dataclass(kw_only=True)
class RoleSlot(JsonDocument):
    """
    One role of an action designator: the field that fills it and the entities of the
    semantic digital twin its value names.
    """

    field: str = document_field(RoleSlotKey.FIELD)
    """
    The field's protocol identifier; a field nested in another is named by the path
    to it, such as ``grasp.graspable``; a role from the context by what the context
    calls it, such as ``robot``.
    """

    role: DesignatorRole = document_field(RoleSlotKey.ROLE)
    """
    The role the field fills.
    """

    source: RoleSource = document_field(RoleSlotKey.SOURCE, default=RoleSource.FIELD)
    """
    Where the filler comes from.
    """

    value: str = document_field(RoleSlotKey.VALUE)
    """
    The value as the plan's parameters render it.
    """

    entities: List[RoleEntity] = document_field(
        RoleSlotKey.ENTITIES, default_factory=list
    )
    """
    The entities the value names; empty for a pose, which names only its reference.
    """

    reference: Optional[RoleEntity] = document_field(
        RoleSlotKey.REFERENCE, default=None
    )
    """
    The body a pose is expressed in, or None for a value that is no pose.
    """
