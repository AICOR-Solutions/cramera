"""
Errors raised while reading or writing protocol documents.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import TYPE_CHECKING, Any, Tuple

if TYPE_CHECKING:
    from cramera_protocol.registry import IdStatus

# %% base


@dataclass
class ProtocolError(Exception):
    """
    A protocol document or message that cannot be read or written.
    """

    def __post_init__(self) -> None:
        super().__init__(self.message())

    def message(self) -> str:
        """
        :return: The sentence a person reads when this error is raised.
        """
        return type(self).__name__


# %% versions


@dataclass
class UnsupportedProtocolVersion(ProtocolError):
    """
    A document or answer written by a protocol version this package cannot read.
    """

    found: str
    """
    The version the document declares.
    """

    supported: str
    """
    The version this package reads and writes.
    """

    def message(self) -> str:
        return (
            f"Protocol version {self.found} is not supported; "
            f"this cramera reads version {self.supported}."
        )


@dataclass
class MalformedProtocolVersion(ProtocolError):
    """
    A version text that is not two non-negative integers separated by a dot.
    """

    text: str
    """
    The text that was read as a version.
    """

    def message(self) -> str:
        return f"{self.text!r} is not a protocol version such as '1.0'."


# %% documents


@dataclass
class MissingDocumentField(ProtocolError):
    """
    A document that lacks a field without a default.
    """

    document: str
    """
    The name of the document class being read.
    """

    key: str
    """
    The JSON key that is missing.
    """

    def message(self) -> str:
        return f"{self.document} needs the key {self.key!r}."


@dataclass
class UnexpectedDocumentField(ProtocolError):
    """
    A document that holds keys its class does not declare.
    """

    document: str
    """
    The name of the document class being read.
    """

    keys: Tuple[str, ...]
    """
    The undeclared keys, sorted.
    """

    def message(self) -> str:
        return f"{self.document} does not know the keys {list(self.keys)}."


@dataclass
class InvalidDocumentValue(ProtocolError):
    """
    A value whose JSON type does not match the field it is read into.
    """

    document: str
    """
    The name of the document or value class being read.
    """

    location: str
    """
    The key or position of the value inside the document.
    """

    value: Any
    """
    The value that was read.
    """

    expected: str
    """
    A description of the value the field accepts.
    """

    def message(self) -> str:
        return (
            f"{self.document}.{self.location} expects {self.expected}, "
            f"got {self.value!r}."
        )


@dataclass
class UnsupportedFieldType(ProtocolError):
    """
    A document class that declares a field type the document reader cannot convert.
    """

    document: str
    """
    The name of the document class.
    """

    field_name: str
    """
    The Python name of the field.
    """

    annotation: str
    """
    The field's type annotation.
    """

    def message(self) -> str:
        return (
            f"{self.document}.{self.field_name} has the type {self.annotation}, "
            f"which protocol documents cannot hold."
        )


# %% registry


@dataclass
class RegistryError(ProtocolError):
    """
    An identifier registry that installed packages declare inconsistently, or an
    identifier it does not know.
    """


@dataclass
class MalformedRegistryId(RegistryError):
    """
    A text that is no namespaced identifier ``<namespace>.<name>``.
    """

    text: str
    """
    The text.
    """

    def message(self) -> str:
        return (
            f"{self.text!r} is no namespaced identifier: it needs a namespace of "
            f"lowercase letters, digits and underscores, a dot and a name."
        )


@dataclass
class DuplicateNamespace(RegistryError):
    """
    A namespace two packages claim, or a package claiming two namespaces.
    """

    namespace: str
    """
    The namespace claimed twice, or the second one a package claims.
    """

    distributions: Tuple[str, ...]
    """
    The packages involved.
    """

    def message(self) -> str:
        return (
            f"The namespace {self.namespace!r} conflicts between the packages "
            f"{', '.join(self.distributions)}: every package declares one namespace "
            f"and no two packages share one."
        )


@dataclass
class DuplicateRegistryId(RegistryError):
    """
    An identifier declared twice.
    """

    kind: str
    """
    What the identifier names, such as a robot.
    """

    identifier: str
    """
    The identifier.
    """

    def message(self) -> str:
        return f"The {self.kind} {self.identifier!r} is declared twice."


@dataclass
class DuplicateRegistryAlias(RegistryError):
    """
    An alias declared twice, or one that is also an identifier or a short name.
    """

    alias: str
    """
    The alias.
    """

    def message(self) -> str:
        return (
            f"The alias {self.alias!r} is declared twice or is already the name of "
            f"another entry."
        )


@dataclass
class UnknownRegistryId(RegistryError):
    """
    A name that no installed package declares.
    """

    kind: str
    """
    What the name was looked up as, such as a robot.
    """

    name: str
    """
    The name.
    """

    status: IdStatus
    """
    Why it is not available.
    """

    def message(self) -> str:
        namespace = self.name.partition(".")[0]
        if self.status == "namespace_not_installed":
            return (
                f"The {self.kind} {self.name!r} is unavailable: no installed package "
                f"declares the namespace {namespace!r}."
            )
        return f"No installed package declares the {self.kind} {self.name!r}."


# %% sites


@dataclass
class SiteError(ProtocolError):
    """
    A site file that cannot be read as a site.
    """


@dataclass
class MissingSiteFormatVersion(SiteError):
    """
    A site file that does not declare the format version it is written in.
    """

    site: str
    """
    The site's identity.
    """

    def message(self) -> str:
        return (
            f"The site {self.site!r} declares no formatVersion; every site file "
            f"declares the version of the site format it is written in."
        )


@dataclass
class DuplicateSiteRobot(SiteError):
    """
    A site naming one robot twice.
    """

    site: str
    """
    The site's identity.
    """

    robot: str
    """
    The robot named twice.
    """

    def message(self) -> str:
        return f"The site {self.site!r} names the robot {self.robot!r} twice."


@dataclass
class DuplicateSiteZone(SiteError):
    """
    A site naming one zone twice.
    """

    site: str
    """
    The site's identity.
    """

    zone: str
    """
    The zone named twice.
    """

    def message(self) -> str:
        return f"The site {self.site!r} names the zone {self.zone!r} twice."


@dataclass
class InvalidSiteRobotPose(SiteError):
    """
    A robot pose whose orientation is no unit quaternion.
    """

    site: str
    """
    The site's identity.
    """

    robot: str
    """
    The robot the pose stands.
    """

    norm: float
    """
    The length of the pose's quaternion.
    """

    def message(self) -> str:
        return (
            f"The site {self.site!r} stands the robot {self.robot!r} at a pose whose "
            f"quaternion has length {self.norm:.4f}, not 1."
        )


@dataclass
class UnsetSiteVariable(SiteError):
    """
    A site path naming an environment variable that is not set, such as the directory
    of data kept outside every repository.
    """

    path: str
    """
    The path as the site writes it.
    """

    variable: str
    """
    The variable that is not set.
    """

    def message(self) -> str:
        return (
            f"The site path {self.path!r} names the environment variable "
            f"{self.variable!r}, which is not set; set it to where that data lies on "
            f"this machine."
        )
