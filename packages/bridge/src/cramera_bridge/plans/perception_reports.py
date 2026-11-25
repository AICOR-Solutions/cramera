"""
Perception reports: what a step's perception query asked, every object the perception
reported, which one the step took and why it left the others, and the outcome in one
sentence a person reads beside the step.

The verdicts follow the rules a run applies: coraplex's RoboKudo client drops an object
of another color or type and one outside the box looked in, the detection takes the
first object left, and the step stops before moving when that object lies farther from
where the step expected it than the step allows. A step expects its objects where the plan
was validated with them, or, once it was planned again, where they were last seen.

What the perception checks, the type it names, is kept apart from what a person reads,
the object as the plan names it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from typing_extensions import List, Optional

from cramera_protocol.geometry import Bounds, Vector3
from cramera_protocol.plan_builder import (
    DetectionPurpose,
    PerceptionReport,
    ReportedObject,
    ReportedObjectVerdict,
    SurfaceDepth,
)

CENTIMETRES = 100.0
"""
Centimetres in a metre.
"""

MILLIMETRES = 1000.0
"""
Millimetres in a metre.
"""

VALIDATED_SPOT = "the plan"
"""
Where a step expects its objects until it is planned again, as a person reads it.
"""

LAST_SEEN_SPOT = "last seen"
"""
Where a step planned again expects its objects, as a person reads it.
"""

TAKEN_VERDICTS = (ReportedObjectVerdict.ACCEPTED, ReportedObjectVerdict.TOO_FAR)
"""
The verdicts of the object a step took.
"""

WRONG_KIND_VERDICTS = (
    ReportedObjectVerdict.WRONG_COLOR,
    ReportedObjectVerdict.WRONG_TYPE,
)
"""
The verdicts of an object of another kind than the one looked for.
"""

# %% answers


@dataclass(frozen=True)
class ReportedDesignator:
    """
    One object a perception reported, as it reported it.
    """

    position: Vector3
    """
    Where it was seen, in metres in the world's root.
    """

    size: Optional[Vector3] = None
    """
    The extent of the box around it, None when none was measured.
    """

    colors: List[str] = field(default_factory=list)
    """
    The colors it was seen in, most dominant first.
    """

    type: str = ""
    """
    The type it was reported as, empty when the perception did not classify it.
    """

    inside_surface: Optional[SurfaceDepth] = None
    """
    How far the plan's object looked for would lie inside the surface it stands on,
    put where this object was seen; None when inside none, or when the query looks for
    none of the plan's objects.
    """


@dataclass(frozen=True)
class PerceptionAnswer:
    """
    What a perception answered to one query.
    """

    objects: Optional[List[ReportedDesignator]]
    """
    Every object reported, in the order reported; None when the query went unanswered.
    """


# %% searches


def centimetres(metres: float) -> str:
    """
    :param metres: A distance.
    :return: It in whole centimetres, or in half ones below ten, as a person reads it.
    """
    value = metres * CENTIMETRES
    if value < 10 and round(value * 2) % 2 == 1:
        return f"{round(value * 2) / 2:g} cm"
    return f"{round(value)} cm"


def extent(size: Vector3) -> str:
    """
    :param size: The extent of a box.
    :return: It in centimetres to a tenth, as a person reads it: "6.1 × 5.6 × 1.7 cm".
    """
    sides = (size.x, size.y, size.z)
    return f"{' × '.join(f'{round(side * CENTIMETRES, 1):g}' for side in sides)} cm"


def sentence(text: str) -> str:
    """
    :param text: A sentence.
    :return: It starting with a capital letter.
    """
    return text[:1].upper() + text[1:]


def object_name(identifier: str) -> str:
    """
    :param identifier: The identity of one of the plan's objects, such as ``red_cube``.
    :return: It as a person names it, as the step cards do: "red cube".
    """
    return identifier.replace("_", " ")


def millimetres(metres: float) -> str:
    """
    :param metres: A distance.
    :return: It in whole millimetres, at least one, as a person reads it.
    """
    return f"{max(1, round(metres * MILLIMETRES))} mm"


@dataclass(frozen=True)
class PerceptionSearch:
    """
    What a step's perception query asks: an object of a type, maybe of a color, inside a
    box, and where the step expects it.
    """

    type: str
    """
    The type asked for, as the perception names it; what an object reported is checked
    against, never shown to a person.
    """

    box: Bounds
    """
    The box looked in, in metres in the world's root.
    """

    target: Optional[str] = None
    """
    The identity of the plan's object looked for, None when the query names none.
    """

    color: Optional[str] = None
    """
    The color asked for, None for any.
    """

    table_wide: bool = False
    """
    Whether the box is the whole table rather than one around where the plan was
    validated.
    """

    grounded: Optional[Vector3] = None
    """
    Where the step expects the object just before the query, None when it expects it
    nowhere in particular.
    """

    validated: Optional[Vector3] = None
    """
    Where the plan was validated with the object, when the step was planned again since
    with the object expected elsewhere, at :attr:`grounded`; None otherwise.
    """

    tolerance: Optional[float] = None
    """
    How far, in metres, from :attr:`grounded` the object may lie for the step to go on.
    """

    purpose: Optional[DetectionPurpose] = None
    """
    Why the step looked, None when it is not known.
    """

    expected_size: Optional[Vector3] = None
    """
    The extent of the box around the plan's object looked for, None when the query
    looks for none of the plan's objects.
    """

    size_tolerance: float = 0.3
    """
    By how much, as a share of the object's own extent, an extent measured may differ
    before the size counts as clearly different; the extents are compared from smallest
    to largest, as the object may lie turned.
    """

    def report(self, answer: PerceptionAnswer) -> PerceptionReport:
        """
        :param answer: What the perception answered.
        :return: The report of the query with every object judged.
        """
        objects = [] if answer.objects is None else self.judged(answer.objects)
        return PerceptionReport(
            target=self.target,
            looked_for=self.looked_for(),
            type=self.type,
            color=self.color,
            box=self.box,
            table_wide=self.table_wide,
            grounded=self.grounded,
            validated=self.validated,
            tolerance=self.tolerance,
            answered=answer.objects is not None,
            objects=objects,
            summary=self.summary(answer.objects is not None, objects),
            purpose=self.purpose,
            warnings=self.warnings(objects),
            expected_size=self.expected_size,
        )

    def judged(self, designators: List[ReportedDesignator]) -> List[ReportedObject]:
        """
        :param designators: The objects reported, in order.
        :return: Each with whether the step took it and why not.
        """
        judged = []
        taken = False
        for designator in designators:
            verdict = self.rejection(designator)
            if verdict is None and taken:
                verdict = ReportedObjectVerdict.NOT_CHOSEN
            if verdict is None:
                taken = True
                verdict = (
                    ReportedObjectVerdict.TOO_FAR
                    if self.is_too_far(designator.position)
                    else ReportedObjectVerdict.ACCEPTED
                )
            judged.append(
                ReportedObject(
                    position=designator.position,
                    size=designator.size,
                    colors=list(designator.colors),
                    type=designator.type,
                    verdict=verdict,
                    distance=self.distance(designator.position),
                    inside_surface=designator.inside_surface,
                    size_differs=(
                        verdict not in WRONG_KIND_VERDICTS
                        and self.size_differs(designator.size)
                    ),
                )
            )
        return judged

    def rejection(
        self, designator: ReportedDesignator
    ) -> Optional[ReportedObjectVerdict]:
        """
        :param designator: An object reported.
        :return: Why the step cannot take it, None when it could.
        """
        if (
            self.color is not None
            and designator.colors
            and self.color not in designator.colors
        ):
            return ReportedObjectVerdict.WRONG_COLOR
        if designator.type and designator.type.strip().lower() != self.type.lower():
            return ReportedObjectVerdict.WRONG_TYPE
        if not self.contains(designator.position):
            return ReportedObjectVerdict.OUTSIDE_BOX
        return None

    def size_differs(self, size: Optional[Vector3]) -> bool:
        """
        :param size: The extent of the box around an object reported, None when none
            was measured.
        :return: Whether it differs clearly from the plan's object's, see
            :attr:`size_tolerance`; False when either is unknown.
        """
        if size is None or self.expected_size is None:
            return False
        measured = sorted((size.x, size.y, size.z))
        expected = sorted(
            (self.expected_size.x, self.expected_size.y, self.expected_size.z)
        )
        return any(
            abs(mine - theirs) > self.size_tolerance * theirs
            for mine, theirs in zip(measured, expected)
        )

    def contains(self, position: Vector3) -> bool:
        """
        :param position: A position in the world's root.
        :return: Whether it lies inside the box looked in.
        """
        low, high = self.box.minimum, self.box.maximum
        return (
            low.x <= position.x <= high.x
            and low.y <= position.y <= high.y
            and low.z <= position.z <= high.z
        )

    def distance(self, position: Vector3) -> Optional[float]:
        """
        :param position: A position in the world's root.
        :return: How far it lies from where the step expects the object, horizontally,
            as the step measures it on the table; None when it expects no position.
        """
        if self.grounded is None:
            return None
        return math.hypot(position.x - self.grounded.x, position.y - self.grounded.y)

    def is_too_far(self, position: Vector3) -> bool:
        """
        :param position: Where the object taken was seen.
        :return: Whether it lies farther from where the step expects the object than
            the step allows.
        """
        distance = self.distance(position)
        return (
            distance is not None
            and self.tolerance is not None
            and distance > self.tolerance
        )

    # %% the sentence

    def looked_for(self) -> str:
        """
        :return: The object looked for as a person names it: "the red cube" for the
            plan's red_cube, else by its color.
        """
        if self.target:
            return f"the {object_name(self.target)}"
        return self.kind()

    def kind(self) -> str:
        """
        :return: "a red object", or "an object" for any color.
        """
        return f"a {self.color} object" if self.color else "an object"

    def name(self) -> str:
        """
        :return: The object looked for, shortly: "red cube", or "a red object".
        """
        return self.looked_for().removeprefix("the ")

    def reach(self) -> float:
        """
        :return: How far, in metres, the box looked in reaches from its middle.
        """
        return (self.box.maximum.x - self.box.minimum.x) / 2

    def spot(self) -> str:
        """
        :return: Where the step expects the object, which distances are measured from,
            as a person reads it.
        """
        return VALIDATED_SPOT if self.validated is None else LAST_SEEN_SPOT

    def away(self, position: Vector3, distance: float) -> str:
        """
        :param position: Where an object was seen.
        :param distance: How far it lies from where the step expects the object.
        :return: How far off it lies, such as "1 cm off", and for a step planned again
            from both where it was last seen and the plan's spot.
        """
        if self.validated is None:
            return f"{centimetres(distance)} off"
        from_validated = math.hypot(
            position.x - self.validated.x, position.y - self.validated.y
        )
        return (
            f"{centimetres(distance)} from {LAST_SEEN_SPOT}, "
            f"{centimetres(from_validated)} from {VALIDATED_SPOT}"
        )

    def summary(self, answered: bool, objects: List[ReportedObject]) -> str:
        """
        :param answered: Whether the perception answered.
        :param objects: The objects reported, judged.
        :return: Why the step looked, when it did not look for a detection step, and
            the outcome, shortly.
        """
        outcome = self.outcome(answered, objects)
        lead = self.lead()
        return sentence(outcome if lead is None else f"{lead}: {outcome}")

    def lead(self) -> Optional[str]:
        """
        :return: Why the step looked; None for a detection step's own detection or
            when it is not known.
        """
        return {
            DetectionPurpose.IN_PLACE_CHECK: "in-place check",
            DetectionPurpose.BEFORE_GRASP: "pre-grasp check",
            DetectionPurpose.TABLE_SEARCH: "table search",
        }.get(self.purpose)

    def outcome(self, answered: bool, objects: List[ReportedObject]) -> str:
        """
        :param answered: Whether the perception answered.
        :param objects: The objects reported, judged.
        :return: The outcome, shortly.
        """
        if not answered:
            return f"RoboKudo did not answer the search for {self.name()}."
        taken = self.taken(objects)
        if taken is not None:
            raised = self.raised(taken)
            return f"{self.found(taken)}{'; ' + raised if raised else ''}."
        outside = [
            seen
            for seen in objects
            if seen.verdict is ReportedObjectVerdict.OUTSIDE_BOX
        ]
        if outside and self.grounded is not None:
            nearest = min(outside, key=lambda seen: seen.distance)
            return (
                f"{self.name()} {self.away(nearest.position, nearest.distance)}, "
                f"outside the {centimetres(self.reach())} search."
            )
        nothing = f"no {self.color} object" if self.color else "nothing"
        others = len(objects)
        tail = "" if others == 0 else f" ({others} other{'s' if others > 1 else ''})"
        where = "on the table" if self.table_wide else self.where()
        return f"{nothing} found {where}{tail}."

    def where(self) -> str:
        """
        :return: Where the query looked, shortly.
        """
        if self.grounded is None:
            return "in the box"
        return f"within {centimetres(self.reach())}"

    @staticmethod
    def taken(objects: List[ReportedObject]) -> Optional[ReportedObject]:
        """
        :param objects: The objects reported, judged.
        :return: The one the step took, None when it took none.
        """
        return next((seen for seen in objects if seen.verdict in TAKEN_VERDICTS), None)

    # %% the warnings

    def warnings(self, objects: List[ReportedObject]) -> List[str]:
        """
        :param objects: The objects reported, judged.
        :return: What a person should know of the objects of the kind looked for: the
            one taken but not acted on, the nearest outside the box when none was
            taken, and those ignored beside the one taken.
        """
        taken = self.taken(objects)
        outside = [
            seen
            for seen in objects
            if seen.verdict is ReportedObjectVerdict.OUTSIDE_BOX
        ]
        if taken is None:
            return [self.not_used(outside)] if outside else []
        warnings = [self.mismeasured(taken)] if taken.size_differs else []
        if taken.verdict is ReportedObjectVerdict.TOO_FAR:
            warnings.append(
                sentence(
                    f"{self.name()} not acted on: {centimetres(taken.distance)} off, "
                    f"more than the {centimetres(self.tolerance)} allowed."
                )
            )
        not_chosen = sum(
            1 for seen in objects if seen.verdict is ReportedObjectVerdict.NOT_CHOSEN
        )
        if not_chosen:
            warnings.append(f"{self.more_matching(not_chosen)} ignored (first used).")
        if outside:
            warnings.append(
                f"{self.more_matching(len(outside))} outside the search ignored."
            )
        return warnings

    def not_used(self, outside: List[ReportedObject]) -> str:
        """
        :param outside: The objects of the kind looked for reported outside the box
            looked in, at least one.
        :return: That the nearest of them was not used, and why.
        """
        if self.grounded is None:
            return sentence(f"{self.name()} seen outside the box, not used.")
        nearest = min(outside, key=lambda seen: seen.distance)
        return sentence(
            f"{self.name()} seen {centimetres(nearest.distance)} off, outside the "
            f"search, not used."
        )

    def mismeasured(self, taken: ReportedObject) -> str:
        """
        :param taken: The object the step took, measured clearly unlike the plan's
            object.
        :return: That its size hints at a perception error.
        """
        return sentence(
            f"{self.name()} measured {extent(taken.size)}, expected "
            f"{extent(self.expected_size)}: likely a perception error."
        )

    @staticmethod
    def more_matching(count: int) -> str:
        """
        :param count: How many objects matching the search were left.
        :return: Them counted, such as "2 more matches".
        """
        return f"{count} more match{'es' if count > 1 else ''}"

    def raised(self, taken: ReportedObject) -> str:
        """
        :param taken: The object the step took.
        :return: How far it was reported inside the surface it stands on, which it
            was raised onto; empty when it lay inside none.
        """
        inside = taken.inside_surface
        if inside is None:
            return ""
        return (
            f"{millimetres(inside.depth)} inside the "
            f"{inside.surface.replace('_', ' ')}, raised onto it"
        )

    def found(self, taken: ReportedObject) -> str:
        """
        :param taken: The object the step took.
        :return: Where it was found, shortly.
        """
        if self.table_wide or taken.distance is None:
            return f"found {self.name()}"
        away = self.away(taken.position, taken.distance)
        if taken.verdict is ReportedObjectVerdict.TOO_FAR:
            return (
                f"{self.name()} {away}, more than the "
                f"{centimetres(self.tolerance)} allowed"
            )
        return f"{self.name()} {away}"
