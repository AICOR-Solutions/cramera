"""
A demo's side of its ownership: ending once the owner's pipe closes.
"""

from __future__ import annotations

import os
import signal
import threading

from cramera_plan_builder import lifeline
from cramera_plan_builder.lifeline import Lifeline


def closed_pipe(written: bytes) -> int:
    """
    :param written: What the owner wrote before going away.
    :return: The read end of a pipe whose write end is closed.
    """
    reading, writing = os.pipe()
    os.write(writing, written)
    os.close(writing)
    return reading


def test_the_end_is_called_once_the_input_ends():
    ended = threading.Event()
    descriptor = closed_pipe(b"anything the owner wrote")
    Lifeline(descriptor, end=ended.set).watch().join()
    os.close(descriptor)
    assert ended.is_set()


def test_without_an_end_the_process_is_asked_to_terminate(monkeypatch):
    sent = []
    monkeypatch.setattr(lifeline.os, "kill", lambda *arguments: sent.append(arguments))
    descriptor = closed_pipe(b"")
    Lifeline(descriptor).watch().join()
    os.close(descriptor)
    assert sent == [(os.getpid(), signal.SIGTERM)]
