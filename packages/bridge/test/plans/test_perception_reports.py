"""
Perception reports: what a step's perception query asked, every object that came back,
which one the step took and why the others not, told on the scene of the real Tracy's
table on 2026-11-12, where a red cube validated at one spot was seen 19 cm away at run
time and three table-wide searches then found nothing.
"""

from __future__ import annotations

from dataclasses import replace

from cramera_bridge.plans.perception_reports import (
    PerceptionAnswer,
    PerceptionSearch,
    ReportedDesignator,
)
from cramera_protocol.geometry import Bounds, Vector3
from cramera_protocol.plan_builder import (
    DetectionPurpose,
    ReportedObjectVerdict,
    SurfaceDepth,
)

GROUNDED = Vector3(0.6, 0.105, 0.905)
"""
Where validation saw the red cube.
"""


def around_the_grounded_spot(color: str = "red") -> PerceptionSearch:
    """
    :return: The search of a pick for its cube: a box reaching 7.5 cm from where the
        plan was validated, the cube asked for by its color.
    """
    return PerceptionSearch(
        target="red_cube",
        type="plannedgraspable",
        color=color,
        box=Bounds(
            Vector3(GROUNDED.x - 0.075, GROUNDED.y - 0.075, GROUNDED.z - 0.075),
            Vector3(GROUNDED.x + 0.075, GROUNDED.y + 0.075, GROUNDED.z + 0.075),
        ),
        grounded=GROUNDED,
        tolerance=0.02,
    )


def table_wide() -> PerceptionSearch:
    """
    :return: The search for the red cube on the whole table.
    """
    return PerceptionSearch(
        target="red_cube",
        type="plannedgraspable",
        color="red",
        box=Bounds(Vector3(0.0, -0.8, 0.8), Vector3(1.18, 0.8, 1.1)),
        table_wide=True,
    )


def cube(x: float, y: float, *colors: str) -> ReportedDesignator:
    """
    :return: A cube RoboKudo reported, as large as it reported the real cubes.
    """
    return ReportedDesignator(
        position=Vector3(x, y, 0.905),
        size=Vector3(0.066, 0.061, 0.022),
        colors=list(colors),
    )


TABLE_TOP = [
    ReportedDesignator(
        position=Vector3(0.82, 0.3, 0.9),
        size=Vector3(0.8, 0.5, 0.06),
        colors=["grey"],
    ),
    ReportedDesignator(
        position=Vector3(0.85, -0.3, 0.9),
        size=Vector3(0.8, 0.5, 0.08),
        colors=["grey"],
    ),
]
"""
The table top, which RoboKudo reported as two grey objects.
"""

# %% verdicts


def test_a_red_cube_seen_19_cm_away_lies_outside_the_box_looked_in():
    report = around_the_grounded_spot().report(
        PerceptionAnswer(objects=[cube(0.79, 0.145, "red")])
    )
    (seen,) = report.objects
    assert seen.verdict is ReportedObjectVerdict.OUTSIDE_BOX
    assert round(seen.distance, 2) == 0.19
    assert report.summary == (
        "The red cube was seen 19 cm from where the plan was validated, outside the "
        "search within 7.5 cm of where the plan was validated."
    )


def test_an_empty_answer_says_what_was_looked_for_and_where():
    report = table_wide().report(PerceptionAnswer(objects=[]))
    assert report.objects == []
    assert report.answered is True
    assert report.summary == "A table-wide search found no red object."


def test_an_unanswered_query_reports_no_objects():
    report = table_wide().report(PerceptionAnswer(objects=None))
    assert report.answered is False
    assert report.summary == (
        "The object recognition (RoboKudo) did not answer the search for the red cube."
    )


def test_the_cube_where_it_was_validated_is_taken():
    report = around_the_grounded_spot().report(
        PerceptionAnswer(objects=[cube(0.61, 0.105, "red")])
    )
    (seen,) = report.objects
    assert seen.verdict is ReportedObjectVerdict.ACCEPTED
    assert report.summary == (
        "The red cube was found 1 cm from where the plan was validated."
    )


def test_a_cube_inside_the_box_but_beyond_the_tolerance_stops_the_step():
    report = around_the_grounded_spot().report(
        PerceptionAnswer(objects=[cube(0.64, 0.105, "red")])
    )
    (seen,) = report.objects
    assert seen.verdict is ReportedObjectVerdict.TOO_FAR
    assert report.summary == (
        "The red cube was seen 4 cm from where the plan was validated; the step goes on "
        "only within 2 cm of where the plan was validated."
    )


def test_the_table_top_and_the_other_cubes_are_reported_in_their_colors():
    report = around_the_grounded_spot().report(
        PerceptionAnswer(
            objects=[
                *TABLE_TOP,
                cube(0.77, 0.57, "blue", "white"),
                cube(0.6, 0.1, "red"),
            ]
        )
    )
    assert [seen.verdict for seen in report.objects] == [
        ReportedObjectVerdict.WRONG_COLOR,
        ReportedObjectVerdict.WRONG_COLOR,
        ReportedObjectVerdict.WRONG_COLOR,
        ReportedObjectVerdict.ACCEPTED,
    ]
    assert report.objects[2].colors == ["blue", "white"]


def test_a_second_cube_that_would_do_is_not_chosen():
    report = table_wide().report(
        PerceptionAnswer(objects=[cube(0.79, 0.145, "red"), cube(0.6, 0.1, "red")])
    )
    assert [seen.verdict for seen in report.objects] == [
        ReportedObjectVerdict.ACCEPTED,
        ReportedObjectVerdict.NOT_CHOSEN,
    ]
    assert report.summary == "A table-wide search found the red cube."


def test_an_object_of_another_type_is_not_taken():
    other = ReportedDesignator(
        position=Vector3(0.6, 0.1, 0.905), colors=["red"], type="bowl"
    )
    report = around_the_grounded_spot().report(PerceptionAnswer(objects=[other]))
    (seen,) = report.objects
    assert seen.verdict is ReportedObjectVerdict.WRONG_TYPE
    assert report.summary == (
        "No red object was found within 7.5 cm of where the plan was validated; "
        "1 other object was reported."
    )


# %% a cube reported inside the table


def cube_inside_the_table(depth: float) -> ReportedDesignator:
    """
    :return: The red cube where it was validated, reported `depth` metres inside the
        table.
    """
    return ReportedDesignator(
        position=Vector3(0.61, 0.105, GROUNDED.z - depth),
        colors=["red"],
        inside_surface=SurfaceDepth(surface="table", depth=depth),
    )


def test_a_cube_reported_a_few_millimetres_inside_the_table_says_it_was_raised():
    report = around_the_grounded_spot().report(
        PerceptionAnswer(objects=[cube_inside_the_table(0.004)])
    )
    (seen,) = report.objects
    assert seen.inside_surface.depth == 0.004
    assert report.summary.endswith(
        "The red cube was reported 4 mm inside the table and was raised onto it."
    )


def test_a_cube_reported_centimetres_inside_the_table_says_it_was_raised():
    report = around_the_grounded_spot().report(
        PerceptionAnswer(objects=[cube_inside_the_table(0.04)])
    )
    assert report.summary.endswith(
        "The red cube was reported 40 mm inside the table and was raised onto it."
    )


def test_a_cube_resting_on_the_table_says_nothing_of_it():
    report = around_the_grounded_spot().report(
        PerceptionAnswer(objects=[cube(0.61, 0.105, "red")])
    )
    assert "table" not in report.summary


# %% naming the object and where it is measured from


def test_the_object_looked_for_is_named_as_the_person_knows_it():
    report = around_the_grounded_spot().report(PerceptionAnswer(objects=[]))
    assert report.looked_for == "the red cube"
    assert report.type == "plannedgraspable"


def test_an_object_of_the_plan_is_checked_by_its_type_not_by_its_name():
    report = around_the_grounded_spot().report(
        PerceptionAnswer(
            objects=[
                ReportedDesignator(
                    position=Vector3(0.6, 0.1, 0.905),
                    colors=["red"],
                    type="PlannedGraspable",
                )
            ]
        )
    )
    assert report.objects[0].verdict is ReportedObjectVerdict.ACCEPTED


def test_an_object_no_plan_names_is_named_by_its_color_at_the_start_of_a_sentence():
    search = PerceptionSearch(
        type="plannedgraspable",
        color="red",
        box=Bounds(Vector3(0.5, 0.0, 0.85), Vector3(0.7, 0.2, 1.0)),
    )
    report = search.report(PerceptionAnswer(objects=[cube(0.6, 0.1, "red")]))
    assert report.looked_for == "a red object"
    assert report.summary == "A red object was found in the box looked in."


LAST_SEEN = Vector3(0.79, 0.145, 0.905)
"""
Where the table-wide search found the red cube, 19 cm from where the plan was validated,
and the step was planned again with it.
"""


def where_it_was_last_seen() -> PerceptionSearch:
    """
    :return: The search of the pick planned again where the cube was last seen.
    """
    return PerceptionSearch(
        target="red_cube",
        type="plannedgraspable",
        color="red",
        box=Bounds(
            Vector3(LAST_SEEN.x - 0.075, LAST_SEEN.y - 0.075, LAST_SEEN.z - 0.075),
            Vector3(LAST_SEEN.x + 0.075, LAST_SEEN.y + 0.075, LAST_SEEN.z + 0.075),
        ),
        grounded=LAST_SEEN,
        validated=GROUNDED,
        tolerance=0.02,
    )


def test_a_step_planned_again_says_it_measures_from_where_the_cube_was_last_seen():
    report = where_it_was_last_seen().report(
        PerceptionAnswer(objects=[cube(0.79, 0.145, "red")])
    )
    assert report.validated == GROUNDED
    assert report.summary == (
        "The red cube was found 0 cm from where it was last seen, 19 cm from where "
        "the plan was validated."
    )


def test_nothing_found_where_the_cube_was_last_seen_says_so():
    report = where_it_was_last_seen().report(PerceptionAnswer(objects=[]))
    assert report.summary == (
        "No red object was found within 7.5 cm of where it was last seen."
    )


# %% why the step looked


def test_a_look_before_grasping_says_so_before_what_it_found():
    search = PerceptionSearch(
        target="red_cube",
        type="plannedgraspable",
        box=Bounds(Vector3(0.5, 0.0, 0.85), Vector3(0.7, 0.2, 1.0)),
        purpose=DetectionPurpose.BEFORE_GRASP,
    )
    report = search.report(PerceptionAnswer(objects=[cube(0.6, 0.1, "red")]))
    assert report.purpose is DetectionPurpose.BEFORE_GRASP
    assert report.summary == (
        "Looked again just before grasping: the red cube was found in the box looked "
        "in."
    )


def test_a_check_before_the_step_moves_says_so_before_what_it_found():
    report = replace(
        around_the_grounded_spot(), purpose=DetectionPurpose.IN_PLACE_CHECK
    ).report(PerceptionAnswer(objects=[cube(0.61, 0.105, "red")]))
    assert report.summary == (
        "Checked before the step moved that the object still lies where the plan "
        "expects it: the red cube was found 1 cm from where the plan was validated."
    )


def test_the_search_after_losing_the_object_says_so_before_what_it_found():
    report = replace(table_wide(), purpose=DetectionPurpose.TABLE_SEARCH).report(
        PerceptionAnswer(objects=[])
    )
    assert report.summary == (
        "Searched the table again, the object not being where the plan expected it: "
        "a table-wide search found no red object."
    )


def test_a_detect_steps_own_detection_says_only_what_it_found():
    report = replace(table_wide(), purpose=DetectionPurpose.STEP).report(
        PerceptionAnswer(objects=[cube(0.6, 0.1, "red")])
    )
    assert report.summary == "A table-wide search found the red cube."


# %% warnings


def test_a_cube_seen_outside_the_box_warns_that_it_was_not_used():
    report = around_the_grounded_spot().report(
        PerceptionAnswer(objects=[cube(0.79, 0.145, "red"), *TABLE_TOP])
    )
    assert report.warnings == [
        "The red cube seen 19 cm from where the plan was validated was not used: the "
        "step acts only on the red cube found inside the box it looked in."
    ]


def test_a_cube_beyond_the_tolerance_warns_that_the_step_did_not_go_on():
    report = around_the_grounded_spot().report(
        PerceptionAnswer(objects=[cube(0.64, 0.105, "red")])
    )
    assert report.warnings == [
        "The red cube was not acted on: it lies 4 cm from where the plan was "
        "validated, farther than the 2 cm the step allows."
    ]


def test_a_second_cube_that_would_do_warns_that_it_was_ignored():
    report = table_wide().report(
        PerceptionAnswer(objects=[cube(0.79, 0.145, "red"), cube(0.6, 0.1, "red")])
    )
    assert report.warnings == [
        "1 more object matching the search was ignored; the step used the first one "
        "reported."
    ]


def test_a_cube_outside_the_box_beside_the_one_used_warns_that_it_was_ignored():
    report = around_the_grounded_spot().report(
        PerceptionAnswer(objects=[cube(0.61, 0.105, "red"), cube(0.79, 0.145, "red")])
    )
    assert report.warnings == [
        "1 more object matching the search, outside the box looked in, was ignored."
    ]


def test_the_cube_used_where_it_was_validated_warns_of_nothing():
    report = around_the_grounded_spot().report(
        PerceptionAnswer(objects=[cube(0.61, 0.105, "red"), *TABLE_TOP])
    )
    assert report.warnings == []
