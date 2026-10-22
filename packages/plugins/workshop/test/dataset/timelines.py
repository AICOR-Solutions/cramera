"""
Recorded frame times and the stages a plan ran in them, to cut into steps.
"""

from __future__ import annotations

from cramera_workshop.timeline import StagePeriod

FRAME_INTERVAL = 0.25
"""
The time between two recorded frames, in seconds.
"""

FIRST_FRAME = 100.0
"""
The wall-clock time of the first frame, in seconds since the epoch.
"""

FRAME_TIMES = [FIRST_FRAME + index * FRAME_INTERVAL for index in range(10)]
"""
Ten frames recorded at a steady rate.
"""

FETCH = StagePeriod(stage="Fetch", start=99.5, end=100.8)
"""
A stage that began before the first frame and ended between the fourth and fifth.
"""

CARRY = StagePeriod(stage="Carry", start=100.9, end=101.6)
"""
A stage that ran from the fifth to the seventh frame.
"""

BLINK = StagePeriod(stage="Blink", start=101.6, end=101.7)
"""
A stage that ran between two frames, so no frame shows it.
"""

PLACE = StagePeriod(stage="Place", start=101.7, end=103.0)
"""
A stage that ran from the eighth frame until after the last.
"""

SHARED_END = StagePeriod(stage="Touch", start=100.0, end=100.75)
"""
A stage that ended at the very frame the next one begins at.
"""

SHARED_START = StagePeriod(stage="Lift", start=100.75, end=102.0)
"""
The stage beginning at that frame.
"""
