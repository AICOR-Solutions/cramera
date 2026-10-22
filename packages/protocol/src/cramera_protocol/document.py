"""
JSON documents declared as dataclasses: each field names its JSON key once, and the
document reads and writes itself from that declaration.
"""

from __future__ import annotations

import dataclasses
import functools
import types
import typing
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

from typing_extensions import (
    Any,
    Dict,
    List,
    Mapping,
    Optional,
    Self,
    Sequence,
    Tuple,
    Type,
)

from cramera_protocol.exceptions import (
    InvalidDocumentValue,
    MissingDocumentField,
    UnexpectedDocumentField,
    UnsupportedFieldType,
)

# %% values


class JsonValue(ABC):
    """
    A value that crosses the protocol boundary as JSON.
    """

    @classmethod
    @abstractmethod
    def from_json(cls, data: Any) -> Self:
        """
        Read the value from its JSON form.

        :param data: The decoded JSON value.
        :return: The value it describes.
        :raises InvalidDocumentValue: When ``data`` does not describe such a value.
        """

    @classmethod
    def read_at(cls, data: Any, location: ValueLocation) -> Self:
        """
        Read the value where it sits inside an enclosing document.

        :param data: The decoded JSON value.
        :param location: Where the value sits, for error messages.
        :return: The value it describes.
        """
        return cls.from_json(data)

    @abstractmethod
    def to_json(self) -> Any:
        """
        :return: The JSON-serializable form of this value.
        """


# %% field declaration


@dataclass(frozen=True)
class DocumentField:
    """
    How one dataclass field of a :class:`JsonDocument` appears in JSON.
    """

    key: str
    """
    The JSON key the field is written under.
    """

    legacy_keys: Tuple[str, ...] = ()
    """
    Keys earlier formats used for the same field; read, never written.
    """


@dataclass(frozen=True)
class ExtensionField:
    """
    Marks the field of a :class:`JsonDocument` that keeps the keys the document does not
    declare, so a reader passes data from newer writers and plugins on unchanged.
    """


def document_field(
    key: str,
    *,
    legacy_keys: Sequence[str] = (),
    default: Any = dataclasses.MISSING,
    default_factory: Any = dataclasses.MISSING,
) -> Any:
    """
    Declare a dataclass field of a :class:`JsonDocument`.

    :param key: The JSON key the field is read from and written to.
    :param legacy_keys: Keys earlier formats used for the same field.
    :param default: The value of the field when its key is absent.
    :param default_factory: Builds the value of the field when its key is absent.
    :return: The dataclass field.
    """
    metadata = {DocumentField: DocumentField(key=key, legacy_keys=tuple(legacy_keys))}
    return field(default=default, default_factory=default_factory, metadata=metadata)


def extension_field() -> Any:
    """
    Declare the field that keeps the undeclared keys of a :class:`JsonDocument`.

    :return: The dataclass field, an empty dictionary by default.
    """
    return field(default_factory=dict, metadata={ExtensionField: ExtensionField()})


# %% conversion context


@dataclass(frozen=True)
class ValueLocation:
    """
    Where a value sits inside a document, for error messages.
    """

    document: str
    """
    The name of the document class being read.
    """

    path: str = ""
    """
    The keys and positions from the document root to the value.
    """

    def child(self, step: Any) -> ValueLocation:
        """
        :param step: A key or a position below this location.
        :return: The location of the value at ``step``.
        """
        separator = "." if self.path else ""
        return ValueLocation(self.document, f"{self.path}{separator}{step}")

    def invalid(self, value: Any, expected: str) -> InvalidDocumentValue:
        """
        :param value: The value that does not fit.
        :param expected: A description of what fits.
        :return: The error naming this location.
        """
        return InvalidDocumentValue(self.document, self.path, value, expected)


# %% converters


class ValueConverter(ABC):
    """
    Reads and writes the JSON form of values of one annotated type.
    """

    @abstractmethod
    def read(self, data: Any, location: ValueLocation) -> Any:
        """
        :param data: The decoded JSON value.
        :param location: Where the value sits, for error messages.
        :return: The Python value.
        :raises InvalidDocumentValue: When ``data`` does not fit the type.
        """

    @abstractmethod
    def write(self, value: Any) -> Any:
        """
        :param value: A Python value of the converter's type.
        :return: Its JSON-serializable form.
        """


@dataclass(frozen=True)
class AnyConverter(ValueConverter):
    """
    Passes JSON values through unchanged, for fields typed ``Any``.
    """

    def read(self, data: Any, location: ValueLocation) -> Any:
        return data

    def write(self, value: Any) -> Any:
        return value


@dataclass(frozen=True)
class PrimitiveConverter(ValueConverter):
    """
    Converts ``bool``, ``int``, ``float`` and ``str`` values.
    """

    primitive: type
    """
    The Python type of the value.
    """

    def read(self, data: Any, location: ValueLocation) -> Any:
        if not self.fits(data):
            raise location.invalid(data, self.primitive.__name__)
        if self.primitive is float:
            return float(data)
        return data

    def fits(self, data: Any) -> bool:
        """
        :param data: A decoded JSON value.
        :return: Whether it is a value of :attr:`primitive`; JSON numbers without a
            fraction count as floats, booleans never count as numbers.
        """
        if isinstance(data, bool):
            return self.primitive is bool
        if self.primitive is float:
            return isinstance(data, (int, float))
        return isinstance(data, self.primitive)

    def write(self, value: Any) -> Any:
        return value


@dataclass(frozen=True)
class EnumConverter(ValueConverter):
    """
    Converts members of an :class:`~enum.Enum` through their values.
    """

    enumeration: Type[Enum]
    """
    The enumeration whose members are read.
    """

    def read(self, data: Any, location: ValueLocation) -> Any:
        allowed = [member.value for member in self.enumeration]
        if data not in allowed:
            raise location.invalid(data, f"one of {allowed}")
        return self.enumeration(data)

    def write(self, value: Any) -> Any:
        return value.value


@dataclass(frozen=True)
class OptionalConverter(ValueConverter):
    """
    Converts values that may be ``None``.
    """

    inner: ValueConverter
    """
    The converter of the value when it is present.
    """

    def read(self, data: Any, location: ValueLocation) -> Any:
        if data is None:
            return None
        return self.inner.read(data, location)

    def write(self, value: Any) -> Any:
        if value is None:
            return None
        return self.inner.write(value)


@dataclass(frozen=True)
class ListConverter(ValueConverter):
    """
    Converts JSON arrays into lists.
    """

    item: ValueConverter
    """
    The converter of each element.
    """

    def read(self, data: Any, location: ValueLocation) -> Any:
        if not isinstance(data, list):
            raise location.invalid(data, "a list")
        return [
            self.item.read(element, location.child(index))
            for index, element in enumerate(data)
        ]

    def write(self, value: Any) -> Any:
        return [self.item.write(element) for element in value]


@dataclass(frozen=True)
class DictionaryConverter(ValueConverter):
    """
    Converts JSON objects with free keys into dictionaries.
    """

    item: ValueConverter
    """
    The converter of each value.
    """

    def read(self, data: Any, location: ValueLocation) -> Any:
        if not isinstance(data, dict):
            raise location.invalid(data, "an object")
        return {
            key: self.item.read(element, location.child(key))
            for key, element in data.items()
        }

    def write(self, value: Any) -> Any:
        return {key: self.item.write(element) for key, element in value.items()}


@dataclass(frozen=True)
class JsonValueConverter(ValueConverter):
    """
    Converts values whose class reads and writes itself.
    """

    value_class: Type[JsonValue]
    """
    The class of the value.
    """

    def read(self, data: Any, location: ValueLocation) -> Any:
        return self.value_class.read_at(data, location)

    def write(self, value: Any) -> Any:
        return value.to_json()


# %% converter selection


@dataclass(frozen=True)
class ConverterFactory:
    """
    Chooses the converter for a field's type annotation.
    """

    document: str
    """
    The name of the document class whose fields are converted, for error messages.
    """

    def converter_for(self, field_name: str, annotation: Any) -> ValueConverter:
        """
        :param field_name: The Python name of the field.
        :param annotation: The field's resolved type annotation.
        :return: The converter of values of that type.
        :raises UnsupportedFieldType: When documents cannot hold values of the type.
        """
        origin = typing.get_origin(annotation)
        arguments = typing.get_args(annotation)
        if annotation is Any:
            return AnyConverter()
        if origin in (typing.Union, types.UnionType):
            return self.optional_converter(field_name, annotation, arguments)
        if origin in (list, List, Sequence):
            return ListConverter(self.converter_for(field_name, arguments[0]))
        if origin in (dict, Dict, Mapping):
            return DictionaryConverter(self.converter_for(field_name, arguments[1]))
        if annotation in (bool, int, float, str):
            return PrimitiveConverter(annotation)
        if isinstance(annotation, type) and issubclass(annotation, Enum):
            return EnumConverter(annotation)
        if isinstance(annotation, type) and issubclass(annotation, JsonValue):
            return JsonValueConverter(annotation)
        raise UnsupportedFieldType(self.document, field_name, str(annotation))

    def optional_converter(
        self, field_name: str, annotation: Any, arguments: Tuple[Any, ...]
    ) -> ValueConverter:
        """
        :param field_name: The Python name of the field.
        :param annotation: The union annotation.
        :param arguments: The members of the union.
        :return: The converter of an optional value.
        :raises UnsupportedFieldType: For unions other than ``X | None``.
        """
        present = [argument for argument in arguments if argument is not type(None)]
        if len(present) != 1 or len(arguments) != 2:
            raise UnsupportedFieldType(self.document, field_name, str(annotation))
        return OptionalConverter(self.converter_for(field_name, present[0]))


# %% document layout


@dataclass(frozen=True)
class FieldLayout:
    """
    One declared field of a document with the converter of its values.
    """

    name: str
    """
    The Python name of the field.
    """

    declaration: DocumentField
    """
    The JSON key and legacy keys of the field.
    """

    converter: ValueConverter
    """
    The converter of the field's values.
    """

    required: bool
    """
    Whether the field has no default, so its key must be present.
    """


@dataclass(frozen=True)
class DocumentLayout:
    """
    The declared fields and the extension field of one document class.
    """

    fields: Tuple[FieldLayout, ...]
    """
    The declared fields in declaration order.
    """

    extension: Optional[str]
    """
    The Python name of the field keeping undeclared keys, if the class has one.
    """

    @classmethod
    def of(cls, document_class: Type[JsonDocument]) -> DocumentLayout:
        """
        :param document_class: A dataclass derived from :class:`JsonDocument`.
        :return: Its layout, computed once per class.
        """
        return layout_of(document_class)

    @classmethod
    def build(cls, document_class: Type[JsonDocument]) -> DocumentLayout:
        """
        :param document_class: A dataclass derived from :class:`JsonDocument`.
        :return: Its layout.
        :raises UnsupportedFieldType: When a field is neither declared with
            :func:`document_field` nor with :func:`extension_field`.
        """
        hints = typing.get_type_hints(document_class)
        factory = ConverterFactory(document_class.__name__)
        layouts: List[FieldLayout] = []
        extension: Optional[str] = None
        for declared in dataclasses.fields(document_class):
            if ExtensionField in declared.metadata:
                extension = declared.name
                continue
            if DocumentField not in declared.metadata:
                raise UnsupportedFieldType(
                    document_class.__name__, declared.name, "an undeclared JSON key"
                )
            required = (
                declared.default is dataclasses.MISSING
                and declared.default_factory is dataclasses.MISSING
            )
            layouts.append(
                FieldLayout(
                    name=declared.name,
                    declaration=declared.metadata[DocumentField],
                    converter=factory.converter_for(
                        declared.name, hints[declared.name]
                    ),
                    required=required,
                )
            )
        return cls(fields=tuple(layouts), extension=extension)

    def known_keys(self) -> frozenset[str]:
        """
        :return: Every key the declared fields read, current and legacy.
        """
        keys = set()
        for layout in self.fields:
            keys.add(layout.declaration.key)
            keys.update(layout.declaration.legacy_keys)
        return frozenset(keys)


@functools.cache
def layout_of(document_class: Type[JsonDocument]) -> DocumentLayout:
    """
    :param document_class: A dataclass derived from :class:`JsonDocument`.
    :return: Its layout; classes do not change, so the layout is kept per class.
    """
    return DocumentLayout.build(document_class)


# %% documents


@dataclass(kw_only=True)
class JsonDocument(JsonValue):
    """
    A JSON object whose keys are declared on dataclass fields with
    :func:`document_field`.
    """

    @classmethod
    def from_json(cls, data: Any) -> Self:
        return cls.read_at(data, ValueLocation(cls.__name__))

    @classmethod
    def read_at(cls, data: Any, location: ValueLocation) -> Self:
        """
        Read the document from its JSON object, see :meth:`JsonValue.read_at`.

        :param data: The decoded JSON object.
        :param location: Where the document sits, for error messages.
        :return: The document.
        :raises MissingDocumentField: When a key without a default is absent.
        :raises UnexpectedDocumentField: When undeclared keys are present and the class
            keeps no extension field.
        :raises InvalidDocumentValue: When a value does not fit its field.
        """
        if not isinstance(data, dict):
            raise location.invalid(data, "an object")
        layout = DocumentLayout.of(cls)
        values: Dict[str, Any] = {}
        for field_layout in layout.fields:
            key = cls.present_key(field_layout.declaration, data)
            if key is None:
                if field_layout.required:
                    raise MissingDocumentField(
                        cls.__name__, field_layout.declaration.key
                    )
                continue
            values[field_layout.name] = field_layout.converter.read(
                data[key], location.child(key)
            )
        unknown = {
            key: value for key, value in data.items() if key not in layout.known_keys()
        }
        if layout.extension is not None:
            values[layout.extension] = unknown
        elif unknown:
            raise UnexpectedDocumentField(cls.__name__, tuple(sorted(unknown)))
        return cls(**values)

    @staticmethod
    def present_key(declaration: DocumentField, data: Dict[str, Any]) -> Optional[str]:
        """
        :param declaration: The keys a field may be stored under.
        :param data: The JSON object being read.
        :return: The key holding the field's value, the current key first, or None.
        """
        for key in (declaration.key, *declaration.legacy_keys):
            if key in data:
                return key
        return None

    def to_json(self) -> Dict[str, Any]:
        """
        :return: The JSON object of this document; fields holding None are left out.
        """
        layout = DocumentLayout.of(type(self))
        values = vars(self)
        result: Dict[str, Any] = {}
        for field_layout in layout.fields:
            value = values[field_layout.name]
            if value is None:
                continue
            result[field_layout.declaration.key] = field_layout.converter.write(value)
        if layout.extension is not None:
            result.update(values[layout.extension])
        return result
