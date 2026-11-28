"""
The registry of namespaced identifiers that installed packages contribute through entry
points, read from their metadata alone.
"""

from __future__ import annotations

import sys
from importlib.metadata import PathDistribution
from pathlib import Path

import pytest

from cramera_protocol.exceptions import (
    DuplicateNamespace,
    DuplicateRegistryAlias,
    DuplicateRegistryId,
    MalformedRegistryId,
    UnknownRegistryId,
)
from cramera_protocol.registry import (
    DeclaredEntryPoint,
    IdKind,
    IdStatus,
    Registry,
    RegistryGroup,
    RegistryId,
)

# %% helpers


def declared(distribution: str, group: str, name: str, value: str):
    return DeclaredEntryPoint(
        distribution=distribution, group=group, name=name, value=value
    )


def cram_and_example() -> Registry:
    return Registry.from_declarations(
        [
            declared("cramera-bridge", RegistryGroup.NAMESPACES, "cram", "coraplex"),
            declared(
                "cramera-bridge",
                RegistryGroup.ROBOTS,
                "tracy",
                "semantic_digital_twin.robots.tracy:Tracy",
            ),
            declared(
                "cramera-bridge",
                RegistryGroup.ACTIONS,
                "pick_up",
                "coraplex.robot_plans.actions.core.pick_up:PickUpAction",
            ),
            declared(
                "cramera-bridge",
                RegistryGroup.ACTIONS,
                "detect",
                "coraplex.robot_plans.actions.core.misc:DetectAction",
            ),
            declared("cramera-bridge", RegistryGroup.ALIASES, "Tracy", "cram.tracy"),
            declared(
                "cramera-bridge", RegistryGroup.ALIASES, "PickUpAction", "cram.pick_up"
            ),
            declared(
                "cramera-bridge",
                RegistryGroup.ACTION_FIELDS,
                "detect.region",
                "detection_box",
            ),
            declared(
                "example-robots",
                RegistryGroup.NAMESPACES,
                "example",
                "example_robots",
            ),
            declared(
                "example-robots",
                RegistryGroup.ROBOTS,
                "walker_s2",
                "example_robots.walker_s2:WalkerS2",
            ),
        ]
    )


# %% identifiers


def test_an_identifier_is_its_namespace_and_its_name():
    identifier = RegistryId.parse("example.walker_s2")
    assert identifier == RegistryId(namespace="example", name="walker_s2")
    assert str(identifier) == "example.walker_s2"


def test_a_field_identifier_keeps_the_dots_after_its_namespace():
    assert RegistryId.parse("cram.detect.region").name == "detect.region"


@pytest.mark.parametrize("text", ["", "tracy", ".tracy", "cram.", "Cram.tracy"])
def test_text_that_is_no_namespaced_identifier_is_refused(text):
    with pytest.raises(MalformedRegistryId):
        RegistryId.parse(text)


# %% resolving


def test_robots_and_actions_resolve_by_their_namespaced_identifiers():
    registry = cram_and_example()
    walker = registry.resolve(IdKind.ROBOT, "example.walker_s2")
    assert walker.module == "example_robots.walker_s2"
    assert walker.attribute == "WalkerS2"
    assert walker.path == "example_robots.walker_s2.WalkerS2"
    assert walker.distribution == "example-robots"
    pick_up = registry.resolve(IdKind.ACTION, "cram.pick_up")
    assert pick_up.identifier == RegistryId("cram", "pick_up")


def test_the_identifiers_saved_today_keep_resolving():
    registry = cram_and_example()
    tracy = registry.resolve(IdKind.ROBOT, "cram.tracy")
    assert registry.resolve(IdKind.ROBOT, "tracy") == tracy
    assert registry.resolve(IdKind.ROBOT, "Tracy") == tracy
    assert registry.resolve(IdKind.ACTION, "PickUpAction").identifier == RegistryId(
        "cram", "pick_up"
    )


def test_the_default_namespace_is_left_out_of_the_public_name():
    registry = cram_and_example()
    assert registry.public_name(registry.resolve(IdKind.ROBOT, "Tracy")) == "tracy"
    walker = registry.resolve(IdKind.ROBOT, "example.walker_s2")
    assert registry.public_name(walker) == "example.walker_s2"


def test_every_name_of_an_entry_has_one_public_name():
    registry = cram_and_example()
    for name in ("cram.tracy", "tracy", "Tracy"):
        assert registry.public_name_of(IdKind.ROBOT, name) == "tracy"
    assert registry.public_name_of(IdKind.ROBOT, "example.walker_s2") == (
        "example.walker_s2"
    )
    assert registry.public_name_of(IdKind.ROBOT, "acme.digger") == "acme.digger"


def test_a_short_name_resolves_only_in_the_default_namespace():
    with pytest.raises(UnknownRegistryId):
        cram_and_example().resolve(IdKind.ROBOT, "walker_s2")


def test_an_identifier_resolves_only_as_its_own_kind():
    with pytest.raises(UnknownRegistryId):
        cram_and_example().resolve(IdKind.ACTION, "cram.tracy")


def test_the_aliases_of_an_entry_are_listed():
    registry = cram_and_example()
    assert registry.aliases_of(registry.resolve(IdKind.ROBOT, "cram.tracy")) == [
        "Tracy"
    ]


def test_an_entry_is_found_by_the_class_it_names():
    registry = cram_and_example()
    found = registry.entry_of_path(
        IdKind.ACTION, "coraplex.robot_plans.actions.core.pick_up.PickUpAction"
    )
    assert found is not None and found.identifier == RegistryId("cram", "pick_up")
    assert registry.entry_of_path(IdKind.ACTION, "elsewhere.Swirling") is None


def test_the_entries_of_one_kind_are_listed_by_identifier():
    registry = cram_and_example()
    assert [str(entry.identifier) for entry in registry.entries(IdKind.ROBOT)] == [
        "cram.tracy",
        "example.walker_s2",
    ]


def test_a_renamed_field_resolves_to_its_attribute():
    registry = cram_and_example()
    detect = registry.resolve(IdKind.ACTION, "detect")
    assert registry.field_attribute(detect, "region") == "detection_box"
    assert registry.field_identifier(detect, "detection_box") == "region"
    assert registry.field_attribute(detect, "color") == "color"
    assert registry.field_identifier(detect, "color") == "color"


# %% missing packages


def test_an_identifier_of_a_namespace_not_installed_is_reported_unavailable():
    registry = cram_and_example()
    assert registry.status(IdKind.ROBOT, "example.walker_s2") == IdStatus.AVAILABLE
    assert registry.status(IdKind.ROBOT, "tracy") == IdStatus.AVAILABLE
    assert (
        registry.status(IdKind.ROBOT, "acme.digger") == IdStatus.NAMESPACE_NOT_INSTALLED
    )
    assert registry.status(IdKind.ROBOT, "example.walker_s3") == IdStatus.UNKNOWN
    assert registry.status(IdKind.ACTION, "swirling") == IdStatus.UNKNOWN


def test_resolving_an_identifier_of_a_missing_package_says_which_namespace_is_missing():
    with pytest.raises(UnknownRegistryId) as raised:
        cram_and_example().resolve(IdKind.ROBOT, "acme.digger")
    assert "acme" in str(raised.value)
    assert raised.value.status == IdStatus.NAMESPACE_NOT_INSTALLED


def test_a_package_without_a_declared_namespace_uses_its_distribution_name():
    registry = Registry.from_declarations(
        [declared("Acme-Robots", RegistryGroup.ROBOTS, "digger", "acme.digger:Digger")]
    )
    assert str(registry.entries(IdKind.ROBOT)[0].identifier) == "acme_robots.digger"


# %% duplicates


def test_two_packages_claiming_one_namespace_are_rejected():
    with pytest.raises(DuplicateNamespace):
        Registry.from_declarations(
            [
                declared("one", RegistryGroup.NAMESPACES, "cram", "one"),
                declared("two", RegistryGroup.NAMESPACES, "cram", "two"),
            ]
        )


def test_a_package_declaring_two_namespaces_is_rejected():
    with pytest.raises(DuplicateNamespace):
        Registry.from_declarations(
            [
                declared("one", RegistryGroup.NAMESPACES, "cram", "one"),
                declared("one", RegistryGroup.NAMESPACES, "acme", "one"),
            ]
        )


def test_an_identifier_declared_twice_is_rejected():
    with pytest.raises(DuplicateRegistryId):
        Registry.from_declarations(
            [
                declared("one", RegistryGroup.ROBOTS, "tracy", "a:Tracy"),
                declared("one", RegistryGroup.ROBOTS, "tracy", "b:Tracy"),
            ]
        )


def test_an_alias_declared_twice_or_shadowing_an_identifier_is_rejected():
    with pytest.raises(DuplicateRegistryAlias):
        Registry.from_declarations(
            [
                declared("one", RegistryGroup.ROBOTS, "tracy", "a:Tracy"),
                declared("one", RegistryGroup.ALIASES, "Tracy", "one.tracy"),
                declared("two", RegistryGroup.ALIASES, "Tracy", "one.tracy"),
            ]
        )
    with pytest.raises(DuplicateRegistryAlias):
        Registry.from_declarations(
            [
                declared("cram", RegistryGroup.NAMESPACES, "cram", "c"),
                declared("cram", RegistryGroup.ROBOTS, "tracy", "a:Tracy"),
                declared("cram", RegistryGroup.ROBOTS, "pr2", "a:PR2"),
                declared("cram", RegistryGroup.ALIASES, "pr2", "cram.tracy"),
            ]
        )


def test_an_alias_of_an_identifier_nobody_declares_is_rejected():
    with pytest.raises(UnknownRegistryId):
        Registry.from_declarations(
            [declared("one", RegistryGroup.ALIASES, "Tracy", "one.tracy")]
        )


# %% metadata only


@pytest.fixture
def installed_robot_package(tmp_path: Path) -> PathDistribution:
    """
    :return: A distribution whose robot module raises when it is imported, on the path.
    """
    module = tmp_path / "exploding_robots.py"
    module.write_text("raise RuntimeError('the registry imported me')\n")
    info = tmp_path / "exploding_robots-1.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: exploding-robots\nVersion: 1.0\n"
    )
    (info / "entry_points.txt").write_text(
        "[cramera.namespaces]\nboom = exploding_robots\n\n"
        "[cramera.robots]\ndigger = exploding_robots:Digger\n\n"
        "[cramera.actions]\ndig = exploding_robots:DigAction\n"
    )
    sys.path.insert(0, str(tmp_path))
    yield PathDistribution(info)
    sys.path.remove(str(tmp_path))


def test_building_the_registry_imports_no_module_of_the_declaring_packages(
    installed_robot_package,
):
    registry = Registry.from_distributions([installed_robot_package])
    assert "exploding_robots" not in sys.modules
    assert str(registry.resolve(IdKind.ROBOT, "boom.digger").identifier) == (
        "boom.digger"
    )
    assert registry.resolve(IdKind.ACTION, "boom.dig").attribute == "DigAction"


def test_the_installed_registry_is_read_from_the_environments_packages():
    registry = Registry.installed()
    assert registry is Registry.installed()
    assert isinstance(registry.entries(IdKind.ROBOT), list)


def test_a_distribution_found_twice_on_the_path_is_read_once(installed_robot_package):
    registry = Registry.from_distributions(
        [installed_robot_package, installed_robot_package]
    )
    assert len(registry.entries(IdKind.ROBOT)) == 1
