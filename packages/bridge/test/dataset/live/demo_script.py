"""
A demo file the live command runs; it records the arguments it was given, and whether
the plan executors it would create are shown in the viewer.
"""

import os
import sys
from pathlib import Path

from cramera_bridge.coraplex_backend import CoraplexBackendRegistration

REGISTERED = "registered"
"""
Recorded after the arguments while a registration shows the demo's plan executors.
"""

UNREGISTERED = "unregistered"
"""
Recorded after the arguments while no registration does.
"""

shown = CoraplexBackendRegistration.current() is not None
Path(os.environ["CRAMERA_TEST_DEMO_OUTPUT"]).write_text(
    " ".join(sys.argv[1:] + [REGISTERED if shown else UNREGISTERED]), encoding="utf-8"
)
