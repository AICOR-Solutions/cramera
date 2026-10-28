"""
A stand-in for a robot demo the viewer runs: it records a bundle, fails, or runs until
it is stopped.

``python fake_run.py SCENES NAME [record|fail|wait]``
"""

import sys
import time
from pathlib import Path

scenes, name, behaviour = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
print(f"running {name}", flush=True)
if behaviour == "fail":
    print("the robot could not reach the vessel", flush=True)
    sys.exit(3)
if behaviour == "wait":
    while True:
        time.sleep(0.05)
(scenes / name).mkdir(parents=True)
(scenes / name / "scene.json").write_text("{}", encoding="utf-8")
print(f"saved {name}", flush=True)
