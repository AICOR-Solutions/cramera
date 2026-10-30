"""
Segmind segmenting a run into events while it goes on, so a recording carries what it
saw.

The run is segmented the way segmind segments a run of its own: its detectors of every
kind watch the run's objects, the free objects and the things a robot takes hold of, and
are ticked on a thread of their own that holds the world's lock while it reads the
world. A demo that segments its run with segmind therefore gets the same events into its
recording that it reports itself.

What segmind detects leaves this module as the protocol's :class:`DetectedEvent`: its
kind named by :func:`~cramera_bridge.names.detected_event_kind`, its bodies by the keys
the viewer shows them under.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from typing_extensions import List, Optional

from cramera_bridge.live.detected_events import DetectedEventSource
from cramera_bridge.names import detected_event_kind
from cramera_bridge.questions.highlights import HighlightKeys
from cramera_bridge.questions.live import WorldHighlightKeys
from cramera_bridge.world_objects import WorldObjects
from cramera_protocol.bundle.scene import DetectedEvent
from segmind.datastructures.events import EventWithTrackedObjects
from segmind.event_segmentation import Segmind
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.world_entity import Body

EVENT_NAME_SEPARATOR = " "
"""
What separates the object's name from the event type in an event's name.
"""

# %% detection


@dataclass
class DetectionRecorder(DetectedEventSource):
    """
    Segmind watching the objects of one world, from :meth:`start` until :meth:`stop`.
    """

    world: World
    """
    The world the run takes place in.
    """

    keys: Optional[HighlightKeys] = None
    """
    Maps a body to the keys the viewer shows it under; when None, the world's free
    objects are keyed as the live publisher keys them and any other body by its name.
    """

    segmentation: Optional[Segmind] = field(default=None, init=False)
    """
    Segmind with its detectors compiled, once compiled; None while the world holds no
    object to watch.
    """

    def watched_bodies(self) -> List[Body]:
        """
        :return: The run's objects as the live publisher lists them: the free objects
            and the things a robot takes hold of.
        """
        return WorldObjects(self.world).objects()

    def compile(self) -> DetectionRecorder:
        """
        Compile segmind's detectors of every kind for the objects the world holds now,
        without ticking them.

        :return: This recorder.
        """
        bodies = self.watched_bodies()
        self.segmentation = (
            Segmind.create_for_bodies(self.world, bodies) if bodies else None
        )
        return self

    def start(self) -> DetectionRecorder:
        """
        Compile the detectors and tick them on their own thread until :meth:`stop`.

        :return: This recorder.
        """
        self.compile()
        if self.segmentation is not None:
            self.segmentation.start()
        return self

    def tick(self) -> None:
        """
        Let the detectors look at the world as it stands now, once.
        """
        if self.segmentation is not None:
            self.segmentation.tick()

    @property
    def is_watching(self) -> bool:
        """
        Whether the detectors are being ticked on their thread.
        """
        return self.segmentation is not None and self.segmentation.is_watching

    def stop(self) -> None:
        """
        Stop ticking the detectors once they have seen the world at rest; what they
        detected stays readable, and stopping a recorder that does not tick changes
        nothing.
        """
        if self.is_watching:
            self.segmentation.stop()

    def events(self) -> List[DetectedEvent]:
        """
        :return: Everything detected so far, oldest first; nothing before
            :meth:`compile`.
        """
        if self.segmentation is None:
            return []
        keys = (
            WorldHighlightKeys(WorldObjects(self.world).objects)
            if self.keys is None
            else self.keys
        )
        return [
            self.describe(event, keys)
            for event in self.segmentation.event_logger.get_events()
        ]

    @staticmethod
    def describe(event: EventWithTrackedObjects, keys: HighlightKeys) -> DetectedEvent:
        """
        :param event: An event segmind detected; every event it detects is about
            tracked objects.
        :param keys: Maps a body to the keys the viewer shows it under.
        :return: The event as a scene bundle carries it, named by the full names of the
            bodies it is about, on no frame yet.
        """
        event_type = type(event).__name__
        tracked = str(event.tracked_object.name)
        return DetectedEvent(
            name=EVENT_NAME_SEPARATOR.join((tracked, event_type)),
            event_type=event_type,
            timestamp=event.timestamp.isoformat(),
            tracked_object=tracked,
            with_object=(
                None if event.with_object is None else str(event.with_object.name)
            ),
            kind=detected_event_kind(event),
            keys=list(
                dict.fromkeys(
                    key for body in event.tracked_objects for key in keys.keys_of(body)
                )
            ),
        )
