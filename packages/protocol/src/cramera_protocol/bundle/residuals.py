"""
The residuals table, ``residuals.csv``: how far a replayed conversion strays from its
recording, per body and joint.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from enum import StrEnum

from typing_extensions import Dict, List, Self, Union

from cramera_protocol.exceptions import InvalidDocumentValue

# %% columns


class ResidualKind(StrEnum):
    """
    What a residual measures.
    """

    BODY = "body"
    """
    How far a replayed body is from its recorded pose.
    """

    JOINT = "joint"
    """
    How much of the recorded relative motion of a joint's bodies the joint cannot make.
    """


class ResidualColumn(StrEnum):
    """
    The columns of ``residuals.csv``, in their order.
    """

    KIND = "kind"
    """
    The :class:`ResidualKind`.
    """

    PATH = "path"
    """
    The USD path of the body or joint.
    """

    NAME = "name"
    """
    The link or joint name in its model.
    """

    MODEL = "model"
    """
    The model or object holding the link or joint.
    """

    LARGEST_DISTANCE = "largest_distance_mm"
    """
    The largest position error in millimetres.
    """

    LARGEST_ANGLE = "largest_angle_deg"
    """
    The largest orientation error in degrees.
    """

    FRAME = "frame"
    """
    The playback frame deviating most.
    """

    WITHIN_TOLERANCE = "within_tolerance"
    """
    Whether every frame lies within the tolerance.
    """


class TruthValue(StrEnum):
    """
    How the table writes a flag.
    """

    TRUE = "True"
    """
    The flag is set.
    """

    FALSE = "False"
    """
    The flag is not set.
    """

    @classmethod
    def of(cls, flag: bool) -> TruthValue:
        """
        :param flag: A flag.
        :return: The text the table writes for it.
        """
        return cls.TRUE if flag else cls.FALSE


CellValue = Union[str, int, float]
"""
The value of one cell before it is written as text.
"""


# %% rows


@dataclass(frozen=True)
class ResidualRow:
    """
    How far the playback strays from the recording for one body or joint.
    """

    kind: ResidualKind
    """
    What is measured.
    """

    path: str
    """
    The USD path of the body or joint.
    """

    name: str
    """
    The link or joint name in its model.
    """

    model: str
    """
    The model or object holding the link or joint, empty when none does.
    """

    largest_distance: float
    """
    The largest position error in millimetres.
    """

    largest_angle: float
    """
    The largest orientation error in degrees.
    """

    frame: int
    """
    The playback frame deviating most.
    """

    within_tolerance: bool
    """
    Whether every frame lies within the tolerance.
    """

    def cells(self) -> Dict[str, CellValue]:
        """
        :return: The row's values by column.
        """
        return {
            ResidualColumn.KIND: self.kind.value,
            ResidualColumn.PATH: self.path,
            ResidualColumn.NAME: self.name,
            ResidualColumn.MODEL: self.model,
            ResidualColumn.LARGEST_DISTANCE: self.largest_distance,
            ResidualColumn.LARGEST_ANGLE: self.largest_angle,
            ResidualColumn.FRAME: self.frame,
            ResidualColumn.WITHIN_TOLERANCE: TruthValue.of(self.within_tolerance).value,
        }

    @classmethod
    def from_cells(cls, cells: Dict[str, str]) -> Self:
        """
        :param cells: One row as the table's text, by column.
        :return: The row.
        :raises InvalidDocumentValue: When a cell does not hold a value of its column.
        """
        kinds = [member.value for member in ResidualKind]
        truth_values = [member.value for member in TruthValue]
        if cells[ResidualColumn.KIND] not in kinds:
            raise InvalidDocumentValue(
                cls.__name__,
                ResidualColumn.KIND,
                cells[ResidualColumn.KIND],
                f"one of {kinds}",
            )
        if cells[ResidualColumn.WITHIN_TOLERANCE] not in truth_values:
            raise InvalidDocumentValue(
                cls.__name__,
                ResidualColumn.WITHIN_TOLERANCE,
                cells[ResidualColumn.WITHIN_TOLERANCE],
                f"one of {truth_values}",
            )
        return cls(
            kind=ResidualKind(cells[ResidualColumn.KIND]),
            path=cells[ResidualColumn.PATH],
            name=cells[ResidualColumn.NAME],
            model=cells[ResidualColumn.MODEL],
            largest_distance=float(cells[ResidualColumn.LARGEST_DISTANCE]),
            largest_angle=float(cells[ResidualColumn.LARGEST_ANGLE]),
            frame=int(cells[ResidualColumn.FRAME]),
            within_tolerance=cells[ResidualColumn.WITHIN_TOLERANCE] == TruthValue.TRUE,
        )


# %% table


@dataclass
class ResidualsTable:
    """
    The content of ``residuals.csv``: the body residuals, then the joint residuals.
    """

    rows: List[ResidualRow] = field(default_factory=list)
    """
    The rows in table order.
    """

    def to_text(self) -> str:
        """
        :return: The table as CSV text with a header row; write it without newline
            translation.
        """
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=list(ResidualColumn))
        writer.writeheader()
        for row in self.rows:
            writer.writerow(row.cells())
        return stream.getvalue()

    @classmethod
    def from_text(cls, text: str) -> Self:
        """
        :param text: CSV text with a header row.
        :return: The table.
        :raises InvalidDocumentValue: When the header does not name the columns.
        """
        reader = csv.DictReader(io.StringIO(text, newline=""))
        columns = [member.value for member in ResidualColumn]
        if reader.fieldnames != columns:
            raise InvalidDocumentValue(
                cls.__name__, "header", reader.fieldnames, f"the columns {columns}"
            )
        return cls(rows=[ResidualRow.from_cells(cells) for cells in reader])
