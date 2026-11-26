"""
What a query box may offer: the variables, types, keywords and classes one query's
namespace holds, and the members that follow a name's dot.
"""

from __future__ import annotations

import inspect
import sys
import types
import typing
from dataclasses import dataclass, field

from krrood.class_diagrams.attribute_introspector import DataclassOnlyIntrospector
from krrood.entity_query_language.scope import eql_factory_namespace
from typing_extensions import Any, Dict, List, Optional

from cramera_protocol.questions import VocabularyEntry, VocabularyKind
from cramera_bridge.questions.exceptions import UnknownVocabularyName
from cramera_bridge.questions.knowledge import QueryDomain
from cramera_bridge.questions.workspace_classes import WorkspaceClassIndex

PRIVATE_PREFIX = "_"
"""
The prefix of the members a query box does not offer.
"""

MEMBER_SEPARATOR = "."
"""
Separates the members of a path such as ``body.global_pose``.
"""


# %% vocabulary


@dataclass
class QueryVocabulary:
    """
    Every name one query's namespace answers to, described for the query box.
    """

    domains: List[QueryDomain] = field(default_factory=list)
    """
    The ready-made variables.
    """

    extra_names: Dict[str, Any] = field(default_factory=dict)
    """
    Further names placed in reach of queries.
    """

    class_index: WorkspaceClassIndex = field(default_factory=WorkspaceClassIndex)
    """
    The workspace classes a query may name.
    """

    def entries(self) -> List[VocabularyEntry]:
        """
        :return: Variables, their types, further names, keywords, then the workspace's
            classes, each name once.
        """
        offered: Dict[str, VocabularyEntry] = {}
        for entry in (
            self.variables()
            + self.further_names()
            + self.keywords()
            + self.workspace_classes()
        ):
            offered.setdefault(entry.name, entry)
        return list(offered.values())

    def members_of(self, name: str) -> List[VocabularyEntry]:
        """
        :param name: A type's name or a variable's, optionally followed by members, such
            as ``body.global_pose``.
        :return: Fields, then properties, then methods of the type the name or its last
            member has, each name once.
        :raises UnknownVocabularyName: When no type of that name is in reach, or a member
            of the path has no type a query box can follow.
        """
        root, *path = name.split(MEMBER_SEPARATOR)
        owner = self.type_named(root)
        for member in path:
            owner = None if owner is None else self.member_type(owner, member)
        if owner is None:
            raise UnknownVocabularyName(name)
        members: Dict[str, VocabularyEntry] = {}
        for member in (
            self.fields_of(owner)
            + self.declared_members(owner, VocabularyKind.PROPERTY)
            + self.declared_members(owner, VocabularyKind.METHOD)
        ):
            members.setdefault(member.name, member)
        return list(members.values())

    # %% where names come from

    def variables(self) -> List[VocabularyEntry]:
        """
        :return: The ready-made variables, then the types they range over.
        """
        variables = [
            VocabularyEntry(
                name=domain.name,
                kind=VocabularyKind.VARIABLE,
                detail=f"ranges over {domain.entity_type.__name__}",
                module=domain.entity_type.__module__,
                type_name=domain.entity_type.__name__,
            )
            for domain in self.domains
        ]
        return variables + [
            self.type_entry(domain.entity_type) for domain in self.domains
        ]

    def further_names(self) -> List[VocabularyEntry]:
        """
        :return: The names placed in reach beside the variables.
        """
        return [
            (
                self.type_entry(value)
                if isinstance(value, type)
                else VocabularyEntry(
                    name=name,
                    kind=VocabularyKind.VALUE,
                    detail=self.summary_of(value) or type(value).__name__,
                    module=type(value).__module__,
                    type_name=type(value).__name__,
                )
            )
            for name, value in self.extra_names.items()
        ]

    def keywords(self) -> List[VocabularyEntry]:
        """
        :return: The entity query language's own keywords.
        """
        return [
            VocabularyEntry(
                name=name, kind=VocabularyKind.FACTORY, detail=self.summary_of(value)
            )
            for name, value in sorted(eql_factory_namespace().items())
        ]

    def workspace_classes(self) -> List[VocabularyEntry]:
        """
        :return: Every workspace class by name, with the module the name resolves to.
        """
        entries = []
        for name in self.class_index.names():
            candidates = self.class_index.candidates(name)
            entries.append(
                VocabularyEntry(
                    name=name,
                    kind=VocabularyKind.CLASS,
                    detail=candidates[0].docstring_summary,
                    module=candidates[0].module,
                    type_name=name,
                    further_modules=len(candidates) - 1,
                )
            )
        return entries

    def type_entry(self, entity_type: type) -> VocabularyEntry:
        """
        :param entity_type: A type.
        :return: The type as the query box offers it.
        """
        return VocabularyEntry(
            name=entity_type.__name__,
            kind=VocabularyKind.ENTITY_TYPE,
            detail=self.summary_of(entity_type),
            module=entity_type.__module__,
            type_name=entity_type.__name__,
        )

    # %% members

    def type_named(self, name: str) -> Optional[type]:
        """
        :param name: A type's name or a variable's.
        :return: The type it stands for or ranges over, or None.
        """
        for domain in self.domains:
            if name in (domain.name, domain.entity_type.__name__):
                return domain.entity_type
        if name in self.extra_names:
            placed = self.extra_names[name]
            return placed if isinstance(placed, type) else type(placed)
        resolved = self.class_index.resolve(name)
        return resolved if isinstance(resolved, type) else None

    def member_type(self, owner: type, member: str) -> Optional[type]:
        """
        :param owner: A type.
        :param member: The name of one of its fields or properties.
        :return: The class the member's annotation names, read through ``Optional`` and
            a type variable's bound, or None when it names no class.
        """
        attribute = inspect.getattr_static(owner, member, None)
        if isinstance(attribute, property):
            function = attribute.fget
            return self.class_of(
                getattr(function, "__annotations__", {}).get("return"),
                sys.modules.get(function.__module__),
            )
        for declaring_type in inspect.getmro(owner):
            annotations = vars(declaring_type).get("__annotations__", {})
            if member in annotations:
                annotation = annotations[member]
                module = sys.modules.get(declaring_type.__module__)
                if isinstance(annotation, str):
                    annotation = (
                        vars(module).get(annotation, annotation)
                        if module
                        else annotation
                    )
                if isinstance(annotation, typing.TypeVar):
                    annotation = self.type_argument(owner, annotation) or annotation
                return self.class_of(annotation, module)
        return None

    @staticmethod
    def type_argument(owner: type, parameter: typing.TypeVar) -> Optional[Any]:
        """
        :param owner: A class whose bases may fill in type parameters, such as
            ``class Arm(HasEndEffector[EndEffector])``.
        :param parameter: A type parameter of one of its bases.
        :return: The type the nearest base fills it with, or None where none does.
        """
        for declaring_type in inspect.getmro(owner):
            for base in getattr(declaring_type, "__orig_bases__", ()):
                origin = typing.get_origin(base)
                parameters = getattr(origin, "__parameters__", ())
                if parameter in parameters:
                    argument = typing.get_args(base)[parameters.index(parameter)]
                    if not isinstance(argument, typing.TypeVar):
                        return argument
        return None

    def class_of(
        self, annotation: Any, module: Optional[types.ModuleType]
    ) -> Optional[type]:
        """
        :param annotation: A type annotation.
        :param module: The module the annotation was written in, whose names an
            annotation written as text uses.
        :return: The class it names: an optional value's class, a type variable's
            bound, a generic's origin, a name written as text or as a forward
            reference resolved in its module
            else through the workspace classes; None for a union of several classes or
            no class.
        """
        if isinstance(annotation, typing.ForwardRef):
            return self.class_written(annotation.__forward_arg__, module)
        if isinstance(annotation, str):
            return self.class_written(annotation, module)
        if isinstance(annotation, typing.TypeVar):
            return self.class_of(annotation.__bound__, module)
        arguments = [
            argument
            for argument in typing.get_args(annotation)
            if argument is not type(None)
        ]
        origin = typing.get_origin(annotation)
        if origin in (typing.Union, types.UnionType):
            return self.class_of(arguments[0], module) if len(arguments) == 1 else None
        if origin is not None:
            return origin if isinstance(origin, type) else None
        return annotation if isinstance(annotation, type) else None

    def class_written(
        self, text: str, module: Optional[types.ModuleType]
    ) -> Optional[type]:
        """
        :param text: An annotation written as text, such as ``Optional[Body]``.
        :param module: The module it was written in.
        :return: The class it names, evaluated among the module's names, else the class
            of that name in reach of a query.
        """
        namespace = {**vars(typing), **(vars(module) if module else {})}
        try:
            evaluated = eval(text, namespace)
        except Exception:
            return self.type_named(text.strip("'\""))
        return self.class_of(evaluated, module)

    @staticmethod
    def fields_of(owner: type) -> List[VocabularyEntry]:
        """
        :param owner: A type.
        :return: Its public dataclass fields, as krrood's introspector finds them.
        """
        return [
            VocabularyEntry(
                name=discovered.public_name,
                kind=VocabularyKind.FIELD,
                detail=str(discovered.field.type),
                module=owner.__module__,
                type_name=owner.__name__,
            )
            for discovered in DataclassOnlyIntrospector().discover(owner_cls=owner)
        ]

    def declared_members(
        self, owner: type, kind: VocabularyKind
    ) -> List[VocabularyEntry]:
        """
        Read the classes themselves, so describing a type never runs a property.

        :param owner: A type.
        :param kind: :attr:`VocabularyKind.PROPERTY` or :attr:`VocabularyKind.METHOD`.
        :return: The public members of that kind, the type's own first.
        """
        collected = []
        for declaring_type in inspect.getmro(owner):
            for name, attribute in vars(declaring_type).items():
                if (
                    name.startswith(PRIVATE_PREFIX)
                    or self.kind_of(attribute) is not kind
                ):
                    continue
                collected.append(
                    VocabularyEntry(
                        name=name,
                        kind=kind,
                        detail=self.summary_of(attribute),
                        module=declaring_type.__module__,
                        type_name=declaring_type.__name__,
                    )
                )
        return collected

    @staticmethod
    def kind_of(attribute: Any) -> Optional[VocabularyKind]:
        """
        :param attribute: An attribute as its class holds it.
        :return: Whether it is a property or a method, or None for neither.
        """
        if isinstance(attribute, property):
            return VocabularyKind.PROPERTY
        if inspect.isroutine(attribute) or isinstance(
            attribute, (classmethod, staticmethod)
        ):
            return VocabularyKind.METHOD
        return None

    @staticmethod
    def summary_of(value: Any) -> str:
        """
        :param value: Anything carrying a docstring.
        :return: The docstring's first line, or an empty text.
        """
        documentation = (inspect.getdoc(value) or "").strip()
        return documentation.splitlines()[0] if documentation else ""
