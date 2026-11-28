"""
When the world's state is worth a snapshot: only once it is settled, and not more often
than the viewer can use; and when a performing plan's progress is worth publishing.

Planning code sets the world's state to check a candidate and restores it right after,
within one tick of the executor performing the plan, and the world reports both changes.
While a plan performs, a snapshot is therefore taken only after a tick, never from a
state change itself.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from typing_extensions import Any, Callable, Optional, Set

FRAME_INTERVAL = 1 / 30
"""
The shortest time between two snapshots, in seconds.
"""

PROGRESS_INTERVAL = 1 / 10
"""
The shortest time between two publications of a plan's progress, in seconds, unless a
node started or ended: the page shows no more.
"""

# %% pacing


@dataclass
class SnapshotPacing:
    """
    Decides when the publisher takes a state snapshot; the publisher's world lock guards
    it.
    """

    clock: Callable[[], float] = time.monotonic
    """
    The monotonic clock snapshots are spaced with.
    """

    interval: float = FRAME_INTERVAL
    """
    The shortest time between two snapshots, in seconds.
    """

    pending: bool = field(default=False, init=False)
    """
    Whether the state changed since the last snapshot.
    """

    last_snapshot: Optional[float] = field(default=None, init=False)
    """
    When the last snapshot was taken, or None before the first.
    """

    performing: Set[int] = field(default_factory=set, init=False)
    """
    The identities of the executors performing a plan in the world.
    """

    def state_changed(self) -> bool:
        """
        Note that the world's state changed.

        :return: Whether to take a snapshot now: never while a plan performs, whose
            ticks take them, else once the interval passed.
        """
        self.pending = True
        return not self.performing and self.is_due()

    def is_due(self) -> bool:
        """
        :return: Whether the state changed since the last snapshot and the interval passed.
        """
        return self.pending and (
            self.last_snapshot is None
            or self.clock() - self.last_snapshot >= self.interval
        )

    def plan_started(self, executor: Any) -> None:
        """
        :param executor: The executor that started performing a plan.
        """
        self.performing.add(id(executor))

    def plan_ended(self, executor: Any) -> bool:
        """
        :param executor: The executor whose plan stopped performing.
        :return: Whether the state changed since the last snapshot, so the plan's last
            state is taken.
        """
        self.performing.discard(id(executor))
        return self.pending

    def is_performing(self) -> bool:
        """
        :return: Whether a plan performs in the world.
        """
        return bool(self.performing)

    def taken(self) -> None:
        """
        Note that a snapshot was just taken.
        """
        self.pending = False
        self.last_snapshot = self.clock()


@dataclass
class ProgressPacing:
    """
    Decides when the publisher publishes a performing plan's progress, the plan and its
    statechart: at most once per :attr:`interval`, but at once when a node started or
    ended. The publisher's world lock guards it.
    """

    clock: Callable[[], float] = time.monotonic
    """
    The monotonic clock publications are spaced with.
    """

    interval: float = PROGRESS_INTERVAL
    """
    The shortest time between two publications, in seconds.
    """

    last_published: Optional[float] = field(default=None, init=False)
    """
    When the progress was published last, or None before the first time.
    """

    def is_due(self, changed: bool) -> bool:
        """
        :param changed: Whether a node started or ended in the tick.
        :return: Whether to publish the progress now; once it says so, the progress
            counts as published.
        """
        now = self.clock()
        if (
            not changed
            and self.last_published is not None
            and now - self.last_published < self.interval
        ):
            return False
        self.last_published = now
        return True
