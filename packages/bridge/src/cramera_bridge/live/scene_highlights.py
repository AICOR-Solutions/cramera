"""
What the scene lights up, outlines and frames for the things an answer is about.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy
from typing_extensions import TYPE_CHECKING, Any, Iterable, List

from cramera_bridge.geometry import POSE_PRECISION, SIZE_PRECISION, NumericPose
from cramera_bridge.questions.highlights import HighlightKeys
from cramera_protocol.geometry import Vector3
from cramera_protocol.resolutions import RegionOutline, SceneHighlight
from semantic_digital_twin.world_description.world_entity import Region

if TYPE_CHECKING:
    from semantic_digital_twin.world import World

# %% highlights


@dataclass(frozen=True)
class SceneHighlighter:
    """
    Turns the native things an answer is about into what the viewer lights up: links and
    free objects by their keys, and regions, which the scene draws no geometry for, as
    boxes.
    """

    world: World
    """
    The world the things belong to.
    """

    keys: HighlightKeys
    """
    Maps a thing to the keys of the links and free objects it lights up.
    """

    def highlight(
        self, about: Iterable[Any], framed: Iterable[Any] = ()
    ) -> SceneHighlight:
        """
        :param about: The things the answer is about: bodies, annotations and regions.
        :param framed: The things the camera moves onto.
        :return: What the scene shows of them.
        """
        about = list(about)
        framed = list(framed)
        return SceneHighlight(
            keys=self.keys_of(about),
            regions=[self.outline(region) for region in self.regions_of(about)],
            framed=self.keys_of(framed)
            + [str(region.name) for region in self.regions_of(framed)],
        )

    def keys_of(self, things: List[Any]) -> List[str]:
        """
        :param things: Native things.
        :return: The keys they light up, each once, in the order first named.
        """
        return list(
            dict.fromkeys(key for thing in things for key in self.keys.keys_of(thing))
        )

    @staticmethod
    def regions_of(things: List[Any]) -> List[Region]:
        """
        :param things: Native things.
        :return: The regions among them with an area to draw.
        """
        return [
            thing for thing in things if isinstance(thing, Region) and thing.area.shapes
        ]

    def outline(self, region: Region) -> RegionOutline:
        """
        :param region: A region with an area.
        :return: The box around its area, where the region is in the world now.
        """
        box = region.area.as_bounding_box_collection_in_frame(region).bounding_box()
        center = box.center.to_np()[:3]
        region_pose = self.world.compute_forward_kinematics_np(self.world.root, region)
        box_pose = region_pose @ numpy.block(
            [[numpy.eye(3), center.reshape(3, 1)], [numpy.zeros((1, 3)), 1.0]]
        )
        return RegionOutline(
            identifier=str(region.name),
            pose=NumericPose.of_matrix(box_pose).published(POSE_PRECISION),
            size=Vector3(
                *(round(float(extent), SIZE_PRECISION) for extent in box.dimensions)
            ),
        )
