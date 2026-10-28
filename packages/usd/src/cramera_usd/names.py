"""
Names the converter hands out: unique among each other, and derived from prim paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePosixPath

from typing_extensions import Dict, List, Set

# %% vocabulary


class GeneratedName(StrEnum):
    """
    Names and name parts the converter makes up for things the stage does not name.
    """

    WORLD = "world"
    """
    The root link of a stage without a default prim, standing for the world.
    """

    ATTACHMENT = "attachment"
    """
    The fixed joint holding a link without an authored joint at its authored pose.
    """


class NameSeparator(StrEnum):
    """
    The separators inside names the converter builds.
    """

    PRIM_PATH = "/"
    """
    Between the elements of a prim path.
    """

    FLATTENED_PATH = "__"
    """
    Between the prim path elements a link or joint name is made of.
    """

    NUMBER = "_"
    """
    Between a repeated name and the number that makes it unique.
    """

    GENERATED_PART = "_"
    """
    Between a name and the generated part appended to it.
    """

    MODEL_PREFIX = "/"
    """
    Between a model's prefix and a joint name in the trajectory.
    """

    OBJECT_NAME = "_"
    """
    Between the prim path elements an object's name is made of.
    """


FIRST_REPEAT_NUMBER = 2
"""
The number appended to a name asked for the second time.
"""

# %% names


@dataclass
class UniqueNames:
    """
    Names unique among each other: a name asked for again gets a number appended,
    starting from two.
    """

    used: Set[str] = field(default_factory=set)
    """
    The names handed out so far.
    """

    def claim(self, wanted: str) -> str:
        """
        :param wanted: The name asked for.
        :return: The wanted name, numbered when it is taken already.
        """
        name = wanted
        number = FIRST_REPEAT_NUMBER
        while name in self.used:
            name = f"{wanted}{NameSeparator.NUMBER}{number}"
            number += 1
        self.used.add(name)
        return name

    def claim_each(self, wanted: Dict[str, str]) -> Dict[str, str]:
        """
        :param wanted: The name asked for per key.
        :return: A unique name for every key, claimed in the order of the keys.
        """
        return {key: self.claim(name) for key, name in wanted.items()}


@dataclass
class PrimNames:
    """
    Unique names derived from prim paths: the default prim's prefix is dropped, path
    separators become double underscores, and a repeated name gets a number appended.
    """

    default_prim: str
    """
    The path of the stage's default prim, or an empty string without one.
    """

    names: UniqueNames = field(default_factory=UniqueNames)
    """
    The names handed out so far.
    """

    by_path: Dict[str, str] = field(default_factory=dict)
    """
    The name handed out per path.
    """

    def name_of(self, path: str) -> str:
        """
        :param path: An absolute prim path.
        :return: The path's unique name; the same path always gets the same name.
        """
        if path in self.by_path:
            return self.by_path[path]
        relative = path
        prefix = f"{self.default_prim}{NameSeparator.PRIM_PATH}"
        if self.default_prim and path.startswith(prefix):
            relative = path[len(prefix) :]
        flattened = relative.strip(NameSeparator.PRIM_PATH).replace(
            NameSeparator.PRIM_PATH, NameSeparator.FLATTENED_PATH
        )
        name = self.names.claim(flattened or GeneratedName.WORLD.value)
        self.by_path[path] = name
        return name


@dataclass(frozen=True)
class PrimPath:
    """
    The path of a prim as text, for code that does not read the stage.
    """

    text: str
    """
    The absolute prim path.
    """

    @property
    def name(self) -> str:
        """
        The prim's own name, the last element of its path.
        """
        return PurePosixPath(self.text).name

    @property
    def elements(self) -> List[str]:
        """
        The path's elements, the empty root element first.
        """
        return self.text.split(NameSeparator.PRIM_PATH)

    def holds(self, other: str) -> bool:
        """
        :param other: Another absolute prim path.
        :return: Whether the other prim is this prim or lies below it.
        """
        return other == self.text or other.startswith(
            f"{self.text}{NameSeparator.PRIM_PATH}"
        )

    def strictly_holds(self, other: str) -> bool:
        """
        :param other: Another absolute prim path.
        :return: Whether the other prim lies below this prim.
        """
        return other.startswith(f"{self.text}{NameSeparator.PRIM_PATH}")

    def child(self, name: str) -> str:
        """
        :param name: A prim name.
        :return: The path of the child of that name.
        """
        return f"{self.text}{NameSeparator.PRIM_PATH}{name}"


# %% object names


@dataclass
class SameNamedPrims:
    """
    Prims that share their name, each told apart by the elements of its path that lie
    between the leading and the trailing elements all of them share.
    """

    paths: List[PrimPath]
    """
    The prims' paths.
    """

    start: int = field(init=False)
    """
    The number of leading path elements all prims share, leaving each prim at least one
    element.
    """

    end: int = field(init=False)
    """
    The number of trailing path elements all prims share, leaving each prim at least one
    element after :attr:`start`.
    """

    def __post_init__(self) -> None:
        shortest = min(len(path.elements) for path in self.paths)
        self.start = self.shared_length(
            [path.elements for path in self.paths], shortest - 1
        )
        self.end = self.shared_length(
            [path.elements[::-1] for path in self.paths], shortest - self.start - 1
        )

    @staticmethod
    def shared_length(sequences: List[List[str]], limit: int) -> int:
        """
        :param sequences: Sequences of path elements.
        :param limit: The most elements to count.
        :return: The number of leading elements all sequences share, at most the limit.
        """
        length = 0
        while length < limit and len({sequence[length] for sequence in sequences}) == 1:
            length += 1
        return length

    def distinguishing_name(self, path: PrimPath) -> str:
        """
        :param path: The path of one of the prims.
        :return: The elements of its path between those all prims share, joined; the
            prim's own name when it is the only prim.
        """
        elements = path.elements
        return NameSeparator.OBJECT_NAME.join(
            elements[self.start : len(elements) - self.end]
        )


@dataclass
class ObjectNames:
    """
    Unique names for the objects prims stand for.

    An object takes its prim's name where no other object's prim has that name; prims of
    one name are told apart by the elements of their paths that differ, so
    ``/World/Assets/chair/Actor_0000/Geom/body`` beside
    ``/World/Assets/book/Actor_0003/Geom/body`` becomes ``chair_Actor_0000``. A name
    taken already gets a number appended.
    """

    paths: List[str]
    """
    The prim paths of the objects, in the order their names are claimed.
    """

    by_path: Dict[str, str] = field(init=False)
    """
    The name of each object, by its prim path.
    """

    def __post_init__(self) -> None:
        prims = [PrimPath(path) for path in self.paths]
        by_name: Dict[str, List[PrimPath]] = {}
        for prim in prims:
            by_name.setdefault(prim.name, []).append(prim)
        groups = {name: SameNamedPrims(paths) for name, paths in by_name.items()}
        self.by_path = UniqueNames().claim_each(
            {prim.text: groups[prim.name].distinguishing_name(prim) for prim in prims}
        )
