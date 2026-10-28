"""
Holding a process's thread at its queries until the viewer moves it on.
"""

from __future__ import annotations

import threading
import time

from typing_extensions import List

from cramera_bridge.live.query_steps import HeldQueries, QueryStepBoard
from cramera_protocol.query_steps import (
    HeldStep,
    QuerySteps,
    StepAdvance,
    StepMoment,
    SteppingRequest,
)

ASKED = HeldStep(number=0, moment=StepMoment.ASKED)
"""
The first query, held where it was asked.
"""

ANSWERED = HeldStep(number=0, moment=StepMoment.ANSWERED)
"""
The first query, held where it was answered.
"""

WAIT_SECONDS = 10.0
"""
How long a test waits for a thread, in seconds.
"""

HELD_SECONDS = 0.2
"""
How long a test holds a process, in seconds.
"""

# %% helpers


def held_thread(control: HeldQueries, step: HeldStep, depth: int = 0):
    """
    :param control: What holds the thread.
    :param step: The step the thread is held at.
    :param depth: How many queries the step's query is asked inside.
    :return: The started thread, and the list it appends to each time it publishes.
    """
    published: List[bool] = []
    thread = threading.Thread(
        target=control.hold,
        args=(step, depth, lambda: published.append(control.held is not None)),
    )
    thread.start()
    return thread, published


def wait_until_held(control: HeldQueries) -> None:
    """
    :param control: What holds a thread that was just started.
    """
    deadline = time.monotonic() + WAIT_SECONDS
    while control.held is None and time.monotonic() < deadline:
        time.sleep(0.01)


# %% holding


def test_a_stepping_process_waits_until_moved_on_from_where_it_is_held():
    control = HeldQueries()
    thread, published = held_thread(control, ASKED)
    wait_until_held(control)
    control.advance(ANSWERED)
    thread.join(timeout=HELD_SECONDS)
    still_held = thread.is_alive()
    control.advance(ASKED)
    thread.join(timeout=WAIT_SECONDS)
    assert still_held
    assert not thread.is_alive()
    assert published == [True]
    assert control.held is None


def test_moving_on_from_no_step_moves_on_from_any():
    control = HeldQueries()
    thread, _ = held_thread(control, ASKED)
    wait_until_held(control)
    control.advance(None)
    thread.join(timeout=WAIT_SECONDS)
    assert not thread.is_alive()


def test_a_process_not_stepping_is_published_and_runs_on():
    control = HeldQueries(stepping=False)
    published = []
    control.hold(ASKED, 0, lambda: published.append(control.held))
    assert published == [None]


def test_nested_queries_are_held_only_while_the_viewer_holds_them():
    control = HeldQueries(holds_nested=False)
    assert control.holds_at(0)
    assert not control.holds_at(1)
    control.change_stepping(SteppingRequest(stepping=True, holds_nested=True))
    assert control.holds_at(1)


def test_stopping_the_stepping_lets_a_held_process_go():
    control = HeldQueries()
    thread, _ = held_thread(control, ASKED)
    wait_until_held(control)
    control.change_stepping(SteppingRequest(stepping=False))
    thread.join(timeout=WAIT_SECONDS)
    assert not thread.is_alive()
    assert not control.holds_at(0)


def test_releasing_lets_a_held_process_go_and_holds_it_nowhere_after():
    control = HeldQueries()
    thread, _ = held_thread(control, ASKED)
    wait_until_held(control)
    control.release()
    thread.join(timeout=WAIT_SECONDS)
    assert not thread.is_alive()
    assert not control.stepping


def test_the_viewer_moves_a_held_process_on_through_the_board():
    control = HeldQueries()
    board = QueryStepBoard()
    thread, _ = held_thread(control, ASKED)
    wait_until_held(control)
    board.publish(QuerySteps(stepping=True, held=control.held), control)
    board.advance(StepAdvance(held=board.current().held))
    thread.join(timeout=WAIT_SECONDS)
    assert not thread.is_alive()


# %% the run's clock


def test_the_running_time_stands_still_while_the_process_is_held():
    control = HeldQueries()
    thread, _ = held_thread(control, ASKED)
    wait_until_held(control)
    time.sleep(HELD_SECONDS)
    control.advance(ASKED)
    thread.join(timeout=WAIT_SECONDS)
    assert control.held_seconds >= HELD_SECONDS
    assert time.time() - control.running_time() >= HELD_SECONDS


def test_the_running_time_is_the_wall_clock_before_any_hold():
    assert abs(HeldQueries().running_time() - time.time()) < HELD_SECONDS
