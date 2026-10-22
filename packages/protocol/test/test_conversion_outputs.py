"""
The files a stage conversion writes besides the scene: semantics, the conversion report
and the residuals table.
"""

from __future__ import annotations

import pytest

from cramera_protocol.bundle.conversion_report import (
    AnimationSummaryKey,
    ConversionReport,
    ConversionReportKey,
    DetachedBodyKey,
    ExcludedPrimKey,
    ExclusionReason,
    ReportCount,
)
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.residuals import (
    ResidualColumn,
    ResidualKind,
    ResidualsTable,
    TruthValue,
)
from cramera_protocol.bundle.semantics import (
    LengthUnit,
    PrimSemanticsKey,
    SemanticNamespace,
    Semantics,
    SemanticsKey,
    UpAxis,
)
from cramera_protocol.exceptions import InvalidDocumentValue

CONVERTED = "converted_bundle"
"""
The converted environment bundle of the dataset.
"""

REPLAY = "converted_replay"
"""
The converted replay of a recorded run.
"""

# %% semantics


def test_semantics_group_attributes_by_namespace(read_json):
    data = read_json(f"{CONVERTED}/{BundleFile.SEMANTICS}")
    semantics = Semantics.from_json(data)
    assert (semantics.units, semantics.up_axis) == (LengthUnit.METRES, UpAxis.Z)
    path, entry = next(
        (path, entry)
        for path, entry in data[SemanticsKey.PRIMS].items()
        if SemanticNamespace.ONTOLOGY in entry
    )
    read = semantics.prims[path]
    assert read.link == entry[PrimSemanticsKey.LINK]
    assert read.ontology == entry[SemanticNamespace.ONTOLOGY]
    assert read.semantic_digital_twin == entry[SemanticNamespace.SEMANTIC_DIGITAL_TWIN]
    assert read.model is None


def test_semantics_are_written_as_they_were_read(read_json):
    for bundle in (CONVERTED, REPLAY):
        data = read_json(f"{bundle}/{BundleFile.SEMANTICS}")
        assert Semantics.from_json(data).to_json() == data


def test_semantics_of_a_replay_name_the_model_of_each_link(read_json):
    data = read_json(f"{REPLAY}/{BundleFile.SEMANTICS}")
    semantics = Semantics.from_json(data)
    for path, entry in data[SemanticsKey.PRIMS].items():
        assert semantics.prims[path].model == entry[PrimSemanticsKey.MODEL]


# %% conversion report


def test_a_report_of_an_environment_lists_what_was_left_out(read_json):
    data = read_json(f"{CONVERTED}/{BundleFile.CONVERSION_REPORT}")
    report = ConversionReport.from_json(data)
    assert [(item.path, item.reason) for item in report.excluded] == [
        (item[ExcludedPrimKey.PATH], ExclusionReason(item[ExcludedPrimKey.REASON]))
        for item in data[ConversionReportKey.EXCLUDED]
    ]
    assert [item.parent_body for item in report.detached] == [
        item[DetachedBodyKey.PARENT_BODY] for item in data[ConversionReportKey.DETACHED]
    ]
    assert report.animation is None


def test_a_report_without_a_playback_drops_its_empty_animation(read_json):
    data = read_json(f"{CONVERTED}/{BundleFile.CONVERSION_REPORT}")
    written = ConversionReport.from_json(data).to_json()
    assert ConversionReportKey.ANIMATION not in written
    assert {key: value for key, value in data.items() if value is not None} == written


def test_a_report_of_a_replay_summarises_the_playback(read_json):
    data = read_json(f"{REPLAY}/{BundleFile.CONVERSION_REPORT}")
    report = ConversionReport.from_json(data)
    summary = data[ConversionReportKey.ANIMATION]
    assert report.animation.frame_count == summary[AnimationSummaryKey.FRAME_COUNT]
    assert report.animation.objects == summary[AnimationSummaryKey.OBJECTS]
    assert report.to_json() == data


def test_joint_counts_are_keyed_by_joint_type(read_json):
    data = read_json(f"{REPLAY}/{BundleFile.CONVERSION_REPORT}")
    counts = ConversionReport.from_json(data).counts
    assert ReportCount.JOINTS.of_type("prismatic") in counts


# %% residuals


def residuals_text(dataset) -> str:
    """
    :param dataset: The directory holding the test documents.
    :return: The residuals table of the converted replay, as written.
    """
    path = dataset / REPLAY / BundleFile.RESIDUALS
    return path.read_bytes().decode("utf-8")


def test_residuals_are_read_row_by_row(dataset):
    table = ResidualsTable.from_text(residuals_text(dataset))
    kinds = [row.kind for row in table.rows]
    assert kinds == sorted(kinds, key=list(ResidualKind).index)
    assert all(row.within_tolerance for row in table.rows)


def test_residuals_are_written_as_they_were_read(dataset):
    text = residuals_text(dataset)
    assert ResidualsTable.from_text(text).to_text() == text


def test_a_residuals_table_names_its_columns():
    header = ResidualsTable().to_text().strip()
    assert header.split(",") == [member.value for member in ResidualColumn]


def test_a_residuals_table_with_other_columns_is_refused(dataset):
    text = residuals_text(dataset).replace(ResidualColumn.FRAME, "step", 1)
    with pytest.raises(InvalidDocumentValue):
        ResidualsTable.from_text(text)


@pytest.mark.parametrize(
    "column, value",
    [(ResidualColumn.KIND, "link"), (ResidualColumn.WITHIN_TOLERANCE, "yes")],
)
def test_a_residual_row_with_an_unknown_value_is_refused(dataset, column, value):
    table = ResidualsTable.from_text(residuals_text(dataset))
    cells = {key: str(cell) for key, cell in table.rows[0].cells().items()}
    cells[column] = value
    text = ResidualsTable().to_text() + ",".join(cells.values()) + "\r\n"
    with pytest.raises(InvalidDocumentValue):
        ResidualsTable.from_text(text)


def test_flags_are_written_as_their_truth_values():
    assert [TruthValue.of(flag) for flag in (True, False)] == [
        TruthValue.TRUE,
        TruthValue.FALSE,
    ]
