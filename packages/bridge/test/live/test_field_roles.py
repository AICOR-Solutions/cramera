"""
Field roles a plugin adds: a domain's actions name their roles' fillers by fields cramera does not know (a carrier a
vehicle tows, a shelf a box is handed to), so a plugin registers them in the entry point group ``cramera.field_roles``;
it may add fields but not change the role of one cramera reads already.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from cramera_bridge import names
from cramera_bridge.exceptions import ConflictingFieldRole
from cramera_bridge.names import FIELD_ROLES, FieldRole, field_roles
from cramera_protocol.designator_roles import DesignatorRole


@dataclass
class FakeEntryPoint:
    name: str
    roles: dict

    def load(self):
        return lambda: self.roles


@pytest.fixture
def plugins(monkeypatch):
    def install(*entry_points):
        monkeypatch.setattr(names, "entry_points", lambda group: list(entry_points))
        field_roles.cache_clear()

    yield install
    field_roles.cache_clear()


def test_without_plugins_the_roles_are_cramera_s_own(plugins):
    plugins()
    assert field_roles() == FIELD_ROLES


def test_a_plugin_adds_the_roles_of_its_fields(plugins):
    plugins(FakeEntryPoint("transport", {"holder": FieldRole(DesignatorRole.LOCATION),
                                         "carried": FieldRole(DesignatorRole.OBJECT)}))
    roles = field_roles()
    assert roles["holder"] == FieldRole(DesignatorRole.LOCATION)
    assert roles["carried"] == FieldRole(DesignatorRole.OBJECT)
    assert roles["arm"] == FIELD_ROLES["arm"]


def test_a_plugin_may_repeat_a_role_but_not_change_it(plugins):
    plugins(FakeEntryPoint("same", {"arm": FIELD_ROLES["arm"]}))
    assert field_roles()["arm"] == FIELD_ROLES["arm"]
    plugins(FakeEntryPoint("other", {"arm": FieldRole(DesignatorRole.OBJECT)}))
    with pytest.raises(ConflictingFieldRole):
        field_roles()
