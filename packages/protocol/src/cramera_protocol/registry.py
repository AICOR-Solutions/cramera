"""
The registry of namespaced identifiers: the robots, actions and action fields installed
packages contribute through entry points.

A package declares its namespace once, in the entry-point group
:attr:`RegistryGroup.NAMESPACES`, and its robots and actions in
:attr:`RegistryGroup.ROBOTS` and :attr:`RegistryGroup.ACTIONS`: the entry point's name
is the identifier's name inside the namespace, its value the class (``module:Class``). The
registry is read from the packages' metadata alone; it never loads an entry point, so
building it imports no module of the declaring packages. Loading the class behind an
identifier is the job of the package that runs it, such as the bridge.

Identifiers are ``<namespace>.<name>``, such as ``example.walker_s2``. Those of the
default namespace :attr:`RegistryNamespace.DEFAULT` may be written without it, so the
names plans and robot profiles saved before the registry existed, such as ``tracy``,
keep resolving; older names, such as ``Tracy``, are declared as aliases in
:attr:`RegistryGroup.ALIASES`.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field
from enum import StrEnum
from importlib.metadata import Distribution, distributions

from typing_extensions import Dict, Iterable, List, Optional, Self, Set, Tuple

from cramera_protocol.exceptions import (
    DuplicateNamespace,
    DuplicateRegistryAlias,
    DuplicateRegistryId,
    MalformedRegistryId,
    UnknownRegistryId,
)

# %% names


class RegistryGroup(StrEnum):
    """
    The entry-point groups the registry reads.
    """

    NAMESPACES = "cramera.namespaces"
    """
    One entry per package: its name is the package's namespace; its value names the
    package's top-level module and is never loaded.
    """

    ROBOTS = "cramera.robots"
    """
    The package's robots: the name is the robot's name in the namespace, the value its
    robot annotation class, ``module:Class``.
    """

    ACTIONS = "cramera.actions"
    """
    The package's actions (skills): the name is the action's name in the namespace, the
    value its action class, ``module:Class``.
    """

    ACTION_FIELDS = "cramera.action_fields"
    """
    The fields of the package's actions whose identifier differs from the class's
    attribute: the name is ``<action name>.<field identifier>``, the value the
    attribute. A field without an entry is identified by its attribute.
    """

    ALIASES = "cramera.aliases"
    """
    Older names of identifiers: the name is the alias, the value the namespaced
    identifier it stands for.
    """


class RegistryNamespace(StrEnum):
    """
    The namespaces the registry treats specially.
    """

    DEFAULT = "cram"
    """
    The namespace whose identifiers may be written without it: CRAM's own robots and
    actions, whose names plans saved before namespaces existed.
    """


class IdKind(StrEnum):
    """
    What an identifier names.
    """

    ROBOT = "robot"
    """
    A robot.
    """

    ACTION = "action"
    """
    An action, the skill a plan step performs.
    """


class IdStatus(StrEnum):
    """
    Whether a name resolves among the installed packages.
    """

    AVAILABLE = "available"
    """
    An installed package declares it.
    """

    NAMESPACE_NOT_INSTALLED = "namespace_not_installed"
    """
    Its namespace belongs to a package that is not installed.
    """

    UNKNOWN = "unknown"
    """
    No installed package declares it although its namespace is installed, or it is a
    short name the default namespace lacks.
    """


# %% identifiers


@dataclass(frozen=True, order=True)
class RegistryId:
    """
    A namespaced identifier.
    """

    namespace: str
    """
    The namespace of the package declaring it.
    """

    name: str
    """
    Its name inside the namespace.
    """

    @classmethod
    def parse(cls, text: str) -> Self:
        """
        :param text: ``<namespace>.<name>``.
        :return: The identifier.
        :raises MalformedRegistryId: When the text has no namespace or no name.
        """
        match = re.fullmatch(r"([a-z][a-z0-9_]*)\.(.+)", text)
        if match is None:
            raise MalformedRegistryId(text)
        return cls(namespace=match.group(1), name=match.group(2))

    @staticmethod
    def is_namespaced(text: str) -> bool:
        """
        :param text: A name.
        :return: Whether it is written with a namespace.
        """
        return re.fullmatch(r"[a-z][a-z0-9_]*\..+", text) is not None

    def __str__(self) -> str:
        return f"{self.namespace}.{self.name}"


# %% declarations


@dataclass(frozen=True)
class DeclaredEntryPoint:
    """
    One entry point a package's metadata declares, as text.
    """

    distribution: str
    """
    The name of the package declaring it.
    """

    group: str
    """
    The entry-point group.
    """

    name: str
    """
    The entry point's name.
    """

    value: str
    """
    The entry point's value, never loaded.
    """


@dataclass(frozen=True)
class RegistryEntry:
    """
    A robot or an action an installed package declares.
    """

    kind: IdKind
    """
    What it is.
    """

    identifier: RegistryId
    """
    Its namespaced identifier.
    """

    target: str
    """
    The class behind it, ``module:Class``, as the entry point names it.
    """

    distribution: str
    """
    The package declaring it.
    """

    @property
    def module(self) -> str:
        """
        :return: The module defining the class.
        """
        return self.target.partition(":")[0].strip()

    @property
    def attribute(self) -> str:
        """
        :return: The class's name in its module.
        """
        return self.target.partition(":")[2].strip()

    @property
    def path(self) -> str:
        """
        :return: The class's dotted path, ``module.Class``.
        """
        return f"{self.module}.{self.attribute}"


def distribution_namespace(distribution: str) -> str:
    """
    :param distribution: A package's name.
    :return: The namespace of a package that declares none: its normalized name.
    """
    return re.sub(r"[-_.]+", "_", distribution).lower()


# %% registry


@dataclass
class Registry:
    """
    The identifiers the installed packages declare.
    """

    namespaces: Dict[str, str] = field(default_factory=dict)
    """
    The package owning each namespace, by namespace.
    """

    declared: Dict[Tuple[IdKind, RegistryId], RegistryEntry] = field(
        default_factory=dict
    )
    """
    The entries by kind and identifier.
    """

    aliases: Dict[str, RegistryId] = field(default_factory=dict)
    """
    The identifier each alias stands for.
    """

    field_attributes: Dict[RegistryId, Dict[str, str]] = field(default_factory=dict)
    """
    The attribute of each field identifier that differs from it, by action identifier.
    """

    # %% building

    @classmethod
    def from_declarations(cls, declarations: Iterable[DeclaredEntryPoint]) -> Self:
        """
        :param declarations: The entry points of the registry's groups.
        :return: The registry they declare.
        :raises DuplicateNamespace: When two packages claim one namespace or a package
            claims two.
        :raises DuplicateRegistryId: When an identifier is declared twice.
        :raises DuplicateRegistryAlias: When an alias is declared twice or is already
            another entry's name.
        :raises UnknownRegistryId: When an alias stands for an identifier nobody
            declares.
        """
        declarations = list(declarations)
        registry = cls()
        owned: Dict[str, str] = {}
        for declaration in declarations:
            if declaration.group == RegistryGroup.NAMESPACES:
                registry.claim(declaration.name, declaration.distribution, owned)
        for declaration in declarations:
            if declaration.group not in (RegistryGroup.ROBOTS, RegistryGroup.ACTIONS):
                continue
            namespace = registry.namespace_of(declaration.distribution, owned)
            kind = (
                IdKind.ROBOT
                if declaration.group == RegistryGroup.ROBOTS
                else IdKind.ACTION
            )
            identifier = RegistryId(namespace, declaration.name)
            if (kind, identifier) in registry.declared:
                raise DuplicateRegistryId(kind, str(identifier))
            registry.declared[kind, identifier] = RegistryEntry(
                kind=kind,
                identifier=identifier,
                target=declaration.value,
                distribution=declaration.distribution,
            )
        for declaration in declarations:
            if declaration.group == RegistryGroup.ACTION_FIELDS:
                action, _, field_identifier = declaration.name.rpartition(".")
                namespace = registry.namespace_of(declaration.distribution, owned)
                registry.field_attributes.setdefault(
                    RegistryId(namespace, action), {}
                )[field_identifier] = declaration.value
        for declaration in declarations:
            if declaration.group == RegistryGroup.ALIASES:
                registry.add_alias(declaration.name, declaration.value)
        return registry

    def claim(self, namespace: str, distribution: str, owned: Dict[str, str]) -> None:
        """
        :param namespace: A namespace a package declares.
        :param distribution: The package.
        :param owned: The namespace of each package so far, by package; extended.
        :raises DuplicateNamespace: When the namespace is taken or the package has one.
        """
        if namespace in self.namespaces:
            raise DuplicateNamespace(
                namespace, (self.namespaces[namespace], distribution)
            )
        if distribution in owned:
            raise DuplicateNamespace(namespace, (distribution,))
        self.namespaces[namespace] = distribution
        owned[distribution] = namespace

    def namespace_of(self, distribution: str, owned: Dict[str, str]) -> str:
        """
        :param distribution: A package declaring entries.
        :param owned: The namespace of each package that declares one, by package.
        :return: The package's namespace: declared, else its normalized name.
        """
        namespace = owned.get(distribution, distribution_namespace(distribution))
        self.namespaces.setdefault(namespace, distribution)
        return namespace

    def add_alias(self, alias: str, target: str) -> None:
        """
        :param alias: An older name.
        :param target: The namespaced identifier it stands for.
        :raises DuplicateRegistryAlias: When the alias is taken.
        :raises UnknownRegistryId: When nobody declares the target.
        """
        identifier = RegistryId.parse(target)
        if not any((kind, identifier) in self.declared for kind in IdKind):
            raise UnknownRegistryId("identifier", target, IdStatus.UNKNOWN)
        taken = alias in self.aliases or any(
            self.declared_entry(kind, alias) is not None for kind in IdKind
        )
        if taken:
            raise DuplicateRegistryAlias(alias)
        self.aliases[alias] = identifier

    @classmethod
    def from_distributions(
        cls, installed: Optional[Iterable[Distribution]] = None
    ) -> Self:
        """
        :param installed: Packages, by default those of the running environment; a
            package found twice on the path is read where it is found first.
        :return: The registry their metadata declares, without loading any entry point.
        """
        groups = {group.value for group in RegistryGroup}
        seen: Set[str] = set()
        declarations = []
        for distribution in distributions() if installed is None else installed:
            name = distribution.metadata["Name"]
            if name is None or distribution_namespace(name) in seen:
                continue
            seen.add(distribution_namespace(name))
            declarations.extend(
                DeclaredEntryPoint(
                    distribution=name,
                    group=entry_point.group,
                    name=entry_point.name,
                    value=entry_point.value,
                )
                for entry_point in distribution.entry_points
                if entry_point.group in groups
            )
        return cls.from_declarations(declarations)

    @classmethod
    @functools.cache
    def installed(cls) -> Self:
        """
        :return: The registry of the running environment's packages, read once.
        """
        return cls.from_distributions()

    # %% resolving

    def declared_entry(self, kind: IdKind, name: str) -> Optional[RegistryEntry]:
        """
        :param kind: What the name names.
        :param name: A namespaced identifier or a short name of the default namespace.
        :return: The entry, or None; aliases are not consulted.
        """
        if RegistryId.is_namespaced(name):
            found = self.declared.get((kind, RegistryId.parse(name)))
            if found is not None:
                return found
        return self.declared.get(
            (kind, RegistryId(RegistryNamespace.DEFAULT.value, name))
        )

    def find(self, kind: IdKind, name: str) -> Optional[RegistryEntry]:
        """
        :param kind: What the name names.
        :param name: A namespaced identifier, a short name of the default namespace or
            an alias.
        :return: The entry, or None when no installed package declares it.
        """
        found = self.declared_entry(kind, name)
        if found is None and name in self.aliases:
            return self.declared.get((kind, self.aliases[name]))
        return found

    def resolve(self, kind: IdKind, name: str) -> RegistryEntry:
        """
        :param kind: What the name names.
        :param name: A namespaced identifier, a short name of the default namespace or
            an alias.
        :return: The entry.
        :raises UnknownRegistryId: When no installed package declares it; it says
            whether the name's package is missing.
        """
        found = self.find(kind, name)
        if found is None:
            raise UnknownRegistryId(kind, name, self.status(kind, name))
        return found

    def status(self, kind: IdKind, name: str) -> IdStatus:
        """
        :param kind: What the name names.
        :param name: A name a plan or a profile uses.
        :return: Whether it is available, and if not, why.
        """
        if self.find(kind, name) is not None:
            return IdStatus.AVAILABLE
        if (
            RegistryId.is_namespaced(name)
            and RegistryId.parse(name).namespace not in self.namespaces
        ):
            return IdStatus.NAMESPACE_NOT_INSTALLED
        return IdStatus.UNKNOWN

    def entries(self, kind: IdKind) -> List[RegistryEntry]:
        """
        :param kind: What the entries name.
        :return: The entries of that kind, by identifier.
        """
        return sorted(
            (entry for entry in self.declared.values() if entry.kind == kind),
            key=lambda entry: entry.identifier,
        )

    def entry_of_path(self, kind: IdKind, path: str) -> Optional[RegistryEntry]:
        """
        :param kind: What the entry names.
        :param path: A class's dotted path, ``module.Class``.
        :return: The entry naming the class, or None.
        """
        return next(
            (entry for entry in self.entries(kind) if entry.path == path), None
        )

    def public_name(self, entry: RegistryEntry) -> str:
        """
        :param entry: An entry.
        :return: The name documents use for it: its short name in the default
            namespace, else its namespaced identifier.
        """
        if entry.identifier.namespace == RegistryNamespace.DEFAULT:
            return entry.identifier.name
        return str(entry.identifier)

    def public_name_of(self, kind: IdKind, name: str) -> str:
        """
        :param kind: What the name names.
        :param name: Any name of an entry: namespaced, short or an alias.
        :return: The entry's :meth:`public_name`, or the name unchanged when no
            installed package declares it.
        """
        found = self.find(kind, name)
        return name if found is None else self.public_name(found)

    def aliases_of(self, entry: RegistryEntry) -> List[str]:
        """
        :param entry: An entry.
        :return: Its aliases, sorted.
        """
        return sorted(
            alias
            for alias, identifier in self.aliases.items()
            if identifier == entry.identifier
        )

    # %% fields

    def field_attribute(self, action: RegistryEntry, identifier: str) -> str:
        """
        :param action: An action's entry.
        :param identifier: One of its field identifiers.
        :return: The class attribute the field is.
        """
        return self.field_attributes.get(action.identifier, {}).get(
            identifier, identifier
        )

    def field_identifier(self, action: RegistryEntry, attribute: str) -> str:
        """
        :param action: An action's entry.
        :param attribute: One of its class's field attributes.
        :return: The field's identifier.
        """
        for identifier, renamed in self.field_attributes.get(
            action.identifier, {}
        ).items():
            if renamed == attribute:
                return identifier
        return attribute
