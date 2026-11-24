"""
Reading the images RoboKudo's pipelines publish, in a ROS context the listener owns.
"""

from __future__ import annotations

import struct
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass

import pytest

rclpy = pytest.importorskip("rclpy")

from rclpy.context import Context
from rclpy.publisher import Publisher
from sensor_msgs.msg import Image
from typing_extensions import Iterator, List

from cramera_bridge.live.perception_images import SeenImage
from cramera_bridge.live.ros_perception_images import (
    RoboKudoImageListener,
    image_title,
)
from cramera_protocol.bundle.scene import PerceptionImageSource

TOPIC = "/cramera_test_pipeline/ClusterColorAnnotator/output_image"
"""
The topic the test publishes on, named as a RoboKudo visualizer names it.
"""

DELIVERY_TIMEOUT_SECONDS = 10.0
"""
How long the test waits for a published image to arrive.
"""

POLL_SECONDS = 0.05
"""
How often the test publishes and looks whether the image arrived.
"""


def red_pixel() -> Image:
    """
    :return: An image of one red pixel, encoded blue first.
    """
    return Image(height=1, width=1, encoding="bgr8", step=3, data=bytes([0, 0, 255]))


def test_an_image_published_while_a_step_ran_is_one_of_its_images():
    listener = RoboKudoImageListener().start()
    sender_context = Context()
    rclpy.init(context=sender_context)
    node = rclpy.create_node("cramera_test_robokudo", context=sender_context)
    publisher = node.create_publisher(Image, TOPIC, 1)
    before = listener.images(None, None, [])
    listener.observe_started()
    deadline = time.monotonic() + DELIVERY_TIMEOUT_SECONDS
    waiting = threading.Event()
    seen = []
    while not seen and time.monotonic() < deadline:
        publisher.publish(red_pixel())
        waiting.wait(POLL_SECONDS)
        seen = listener.images(None, None, [])
    listener.observe_started()
    after_next_start = listener.images(None, None, [])
    thread = listener.thread
    listener.stop()
    node.destroy_node()
    sender_context.try_shutdown()
    assert before == []
    (image,) = seen
    assert (image.title, image.source) == (
        "ClusterColorAnnotator",
        PerceptionImageSource.ROBOKUDO,
    )
    assert image.png.startswith(b"\x89PNG")
    assert after_next_start == []
    assert not thread.is_alive()
    assert listener.context.ok() is False


def test_an_image_is_titled_by_its_annotator_else_its_pipeline():
    assert image_title(TOPIC) == "ClusterColorAnnotator"
    assert image_title("/demo/output_image") == "demo"


def test_a_step_subscribes_to_the_image_topics_there_are_when_it_starts():
    """
    A pipeline that started publishing a moment before a step is listened to during the
    step, not only once the listener next looks for topics.
    """
    listener = RoboKudoImageListener().start()
    sender_context = Context()
    rclpy.init(context=sender_context)
    node = rclpy.create_node("cramera_test_robokudo", context=sender_context)
    node.create_publisher(Image, TOPIC, 1)
    deadline = time.monotonic() + DELIVERY_TIMEOUT_SECONDS
    waiting = threading.Event()
    while TOPIC not in listener.image_topics() and time.monotonic() < deadline:
        waiting.wait(POLL_SECONDS)
    listener.observe_started()
    subscribed = list(listener.subscriptions)
    listener.stop()
    node.destroy_node()
    sender_context.try_shutdown()

    assert subscribed == [TOPIC]


# %% which images are kept, and how


@dataclass
class PublishingPipeline:
    """
    Publishes images on :data:`TOPIC` as a RoboKudo visualizer does, to a listener.
    """

    listener: RoboKudoImageListener
    """
    The listener the images are published to.
    """

    publisher: Publisher
    """
    Publishes on :data:`TOPIC`.
    """

    def images_once_delivered(self, image: Image) -> List[SeenImage]:
        """
        Publish an image until the listener holds one that arrived since a step started.

        :param image: The image.
        :return: The step's images once one arrived, empty when none did in time.
        """
        self.listener.observe_started()
        deadline = time.monotonic() + DELIVERY_TIMEOUT_SECONDS
        waiting = threading.Event()
        while time.monotonic() < deadline:
            self.publisher.publish(image)
            waiting.wait(POLL_SECONDS)
            with self.listener.lock:
                arrived = TOPIC in self.listener.newest and (
                    self.listener.newest[TOPIC][0] >= self.listener.step_started
                )
            if arrived:
                return self.listener.images(None, None, [])
        return []


@contextmanager
def publishing_to(listener: RoboKudoImageListener) -> Iterator[PublishingPipeline]:
    """
    :param listener: A listener, started while the block runs.
    :return: A pipeline publishing to it.
    """
    listener.start()
    sender_context = Context()
    rclpy.init(context=sender_context)
    node = rclpy.create_node("cramera_test_robokudo", context=sender_context)
    yield PublishingPipeline(listener, node.create_publisher(Image, TOPIC, 1))
    listener.stop()
    node.destroy_node()
    sender_context.try_shutdown()


def red_image(width: int, height: int) -> Image:
    """
    :return: A red image of the size, encoded blue first.
    """
    return Image(
        height=height,
        width=width,
        encoding="bgr8",
        step=3 * width,
        data=bytes([0, 0, 255] * width * height),
    )


def png_size(png: bytes) -> tuple[int, int]:
    """
    :return: The width and height a PNG file's header gives.
    """
    return struct.unpack(">II", png[16:24])


def test_a_blank_image_a_visualizer_publishes_for_an_annotator_drawing_nothing_is_left_out():
    blank = Image(height=2, width=2, encoding="bgr8", step=6, data=bytes(12))

    with publishing_to(RoboKudoImageListener()) as pipeline:
        delivered = pipeline.images_once_delivered(blank)

    assert delivered == []


def test_an_image_wider_than_the_listener_keeps_is_shrunk_to_fit():
    with publishing_to(RoboKudoImageListener(largest_width=2)) as pipeline:
        (image,) = pipeline.images_once_delivered(red_image(width=4, height=2))

    assert png_size(image.png) == (2, 1)


def test_the_images_of_a_step_wait_for_one_still_on_its_way():
    """
    A pipeline publishes what it drew just after it answered, so the images of a step
    asked for once it was answered are waited for, up to the listener's timeout.
    """
    listener = RoboKudoImageListener(arrival_timeout=DELIVERY_TIMEOUT_SECONDS)
    with publishing_to(listener) as pipeline:
        pipeline.images_once_delivered(red_image(width=1, height=1))
        listener.observe_started()
        late = threading.Timer(0.5, pipeline.publisher.publish, [red_pixel()])
        late.start()
        images = listener.images(None, None, [])
        late.join()

    assert [image.title for image in images] == [image_title(TOPIC)]
