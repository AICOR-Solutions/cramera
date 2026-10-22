"""
The robot plan ${name}, composed in the cramera plan builder.

``python ${file_name}`` builds the plan's world, lets the selected robot perform its
steps while the run is published to the viewer, and saves the recording into the local
scenes directory. ``--stage`` only builds the world and publishes it until the process
is stopped, so its objects can be placed by hand; ``--port`` chooses where it is
published.
"""

from __future__ import annotations

import sys

from cramera_plan_builder.cram.command import PlanDemoCommand

DEMO = r"""
${demo}
"""
"""

The plan and where its environment was found, as the plan builder wrote them.
"""

if __name__ == "__main__":
    PlanDemoCommand.of_text(DEMO).main(sys.argv[1:])
