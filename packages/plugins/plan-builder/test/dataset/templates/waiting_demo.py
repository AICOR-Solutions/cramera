"""
A stand-in for the generated demo of ${name} (${file_name}): it reports its arguments,
then a staged demo waits until its owner goes away or it is stopped, and any other demo
ends at once.
"""

import json
import signal
import sys
import threading

from cramera.lifeline import Lifeline

DEMO = r"""
${demo}
"""

if __name__ == "__main__":
    print(
        "plan", json.loads(DEMO)["plan"]["name"], "arguments", *sys.argv[1:], flush=True
    )
    if "--stage" in sys.argv:
        ended = threading.Event()
        signal.signal(signal.SIGTERM, lambda number, frame: ended.set())
        Lifeline(sys.stdin.fileno(), end=ended.set).watch()
        ended.wait()
        print("stage ended", flush=True)
