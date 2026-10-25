"""
The shared cabinet collision panels describe usable boxes and leave the drawer bay open.
"""

import math

from cramera_protocol.laboratory.cabinet import CabinetPart, CabinetStructure


def test_the_cabinet_panels_have_finite_centres_and_positive_extents():
    cabinet = CabinetStructure()
    assert cabinet.name == "laboratory_cabinet"
    panels = cabinet.panels()
    assert {panel.part for panel in panels} == set(CabinetPart)
    for panel in panels:
        assert len(panel.center) == len(panel.size) == 3
        assert all(math.isfinite(value) for value in (*panel.center, *panel.size))
        assert all(value > 0 for value in panel.size)


def test_the_drawer_opening_remains_clear_between_the_worktop_and_shelf():
    # A point in the drawer bay may be occupied by the moving drawer, but no fixed
    # cabinet panel should fill the opening.
    opening = (-0.52, -0.20, 0.72)
    for panel in CabinetStructure().panels():
        assert any(
            abs(point - center) > size / 2
            for point, center, size in zip(opening, panel.center, panel.size)
        )
