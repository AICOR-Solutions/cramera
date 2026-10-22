"""
A demo's side of its ownership: ending once the owner's pipe closes.
"""

from __future__ import annotations

import io
import os
import signal
import threading

from cramera_plan_builder import lifeline
from cramera_plan_builder.lifeline import Lifeline


def test_the_end_is_called_once_the_input_ends():
    ended = threading.Event()
    Lifeline(io.BytesIO(b"anything the owner wrote"), end=ended.set).watch().join()
    assert ended.is_set()


def test_without_an_end_the_process_is_asked_to_terminate(monkeypatch):
    sent = []
    monkeypatch.setattr(lifeline.os, "kill", lambda *arguments: sent.append(arguments))
    Lifeline(io.BytesIO(b"")).watch().join()
    assert sent == [(os.getpid(), signal.SIGTERM)]
