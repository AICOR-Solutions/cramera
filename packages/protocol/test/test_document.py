"""
Reading and writing documents declared with document fields.
"""

from __future__ import annotations

import pytest

from cramera_protocol.document import DocumentLayout
from cramera_protocol.exceptions import (
    InvalidDocumentValue,
    MissingDocumentField,
    UnexpectedDocumentField,
    UnsupportedFieldType,
)
from cramera_protocol.geometry import Pose

from .dataset.documents import (
    ColorName,
    DocumentWithPlainField,
    DocumentWithSet,
    DocumentWithUnion,
    OpenDocument,
    SampleDocument,
    SampleKey,
)

# %% reading


def test_every_field_kind_is_read(read_json):
    document = SampleDocument.from_json(read_json("sample_document.json"))
    assert document.title == "root"
    assert document.count == 3
    assert document.ratio == 2.0
    assert isinstance(document.ratio, float)
    assert document.enabled is True
    assert document.color is ColorName.BLUE
    assert document.poses == [Pose(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0)]
    assert document.table == {"a": [1.5, 2.5]}
    assert document.children[0].children[0].title == "grandchild"
    assert document.anything == {"free": ["form"]}


def test_absent_fields_take_their_defaults():
    document = SampleDocument.from_json({SampleKey.TITLE: "only a title"})
    assert document.count is None
    assert document.ratio == 1.0
    assert document.poses == []
    assert document.children == []


def test_defaults_are_not_shared_between_documents():
    first = SampleDocument.from_json({SampleKey.TITLE: "first"})
    second = SampleDocument.from_json({SampleKey.TITLE: "second"})
    first.poses.append(Pose(0, 0, 0, 0, 0, 0, 1))
    assert second.poses == []


def test_a_legacy_key_is_read(read_json):
    document = SampleDocument.from_json(
        read_json("sample_document_with_legacy_title.json")
    )
    assert document.title == "from an earlier format"


def test_the_current_key_wins_over_a_legacy_key(read_json):
    document = SampleDocument.from_json(
        read_json("sample_document_with_both_titles.json")
    )
    assert document.title == "both"


def test_undeclared_keys_are_kept_by_an_extension_field(read_json):
    data = read_json("open_document.json")
    document = OpenDocument.from_json(data)
    assert document.extensions == {"plugin": {"key": 1}, "another": [True]}
    assert document.to_json() == data


# %% writing


def test_a_document_round_trips(read_json):
    document = SampleDocument.from_json(read_json("sample_document.json"))
    assert SampleDocument.from_json(document.to_json()) == document


def test_writing_uses_the_current_key_and_leaves_out_absent_values(read_json):
    document = SampleDocument.from_json(
        read_json("sample_document_with_legacy_title.json")
    )
    written = document.to_json()
    assert written[SampleKey.TITLE] == "from an earlier format"
    assert SampleKey.OLD_TITLE not in written
    assert SampleKey.COUNT not in written
    assert written[SampleKey.POSES] == []


def test_an_enumeration_member_is_written_as_its_value(read_json):
    written = SampleDocument.from_json(read_json("sample_document.json")).to_json()
    assert written[SampleKey.COLOR] == ColorName.BLUE.value


# %% refusals


def test_a_missing_required_key_is_refused():
    with pytest.raises(MissingDocumentField) as raised:
        SampleDocument.from_json({})
    assert raised.value.key == SampleKey.TITLE


@pytest.mark.parametrize(
    "file_name, location",
    [
        ("sample_document_with_flag_as_count.json", SampleKey.COUNT),
        ("sample_document_with_number_as_flag.json", SampleKey.ENABLED),
        ("sample_document_with_unknown_color.json", SampleKey.COLOR),
        ("sample_document_with_text_in_table.json", "table.a.1"),
        ("sample_document_with_list_as_table.json", SampleKey.TABLE),
        ("sample_document_with_numeric_child_title.json", "children.0.title"),
    ],
)
def test_a_value_of_the_wrong_type_is_refused_where_it_is(
    read_json, file_name, location
):
    with pytest.raises(InvalidDocumentValue) as raised:
        SampleDocument.from_json(read_json(f"invalid/{file_name}"))
    assert raised.value.location == location


def test_an_undeclared_key_is_refused_without_an_extension_field(read_json):
    with pytest.raises(UnexpectedDocumentField) as raised:
        SampleDocument.from_json(
            read_json("invalid/sample_document_with_unknown_key.json")
        )
    assert raised.value.keys == ("unknown",)


def test_a_document_that_is_not_an_object_is_refused(read_json):
    with pytest.raises(InvalidDocumentValue):
        SampleDocument.from_json(read_json("invalid/scene_as_list.json"))


@pytest.mark.parametrize(
    "document_class", [DocumentWithPlainField, DocumentWithUnion, DocumentWithSet]
)
def test_a_field_documents_cannot_hold_is_refused_when_its_class_is_used(
    document_class,
):
    with pytest.raises(UnsupportedFieldType):
        DocumentLayout.of(document_class)


def test_errors_read_as_sentences():
    error = MissingDocumentField("Scene", "name")
    assert str(error) == error.message()
    assert "name" in str(error)
