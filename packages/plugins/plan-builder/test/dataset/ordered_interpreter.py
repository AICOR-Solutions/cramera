#!/usr/bin/env python3
"""
Stands in for the interpreter running a cramera-bridge command: called as
``<interpreter> -m <module> <order file> <answer file> [<expected order file>]``, it says
its process id, waits until its input closes and then does what the order's
``behaviour`` says: ``answer`` writes its process id and the behaviour of the order it
was told to expect, ``hang`` sleeps, ``crash`` answers and fails, ``raise`` prints
warnings and fails with a traceback whose exception says why on two lines.
"""

import json
import os
import sys
import time

print(f"process {os.getpid()}", flush=True)
_, _, order_file, answer_file, *expected_file = sys.argv[1:]
expected = None
if expected_file:
    with open(expected_file[0], encoding="utf-8") as expected_order:
        expected = json.load(expected_order)["behaviour"]
sys.stdin.read()
with open(order_file, encoding="utf-8") as order:
    behaviour = json.load(order)["behaviour"]
if behaviour == "raise":
    print("UserWarning: a warning before the failure", flush=True)
    raise RuntimeError("RoboKudo did not answer within 30 s\nSuggestion: read its log.")
if behaviour == "hang":
    time.sleep(60)
with open(answer_file, "w", encoding="utf-8") as answer:
    json.dump({"pid": os.getpid(), "expected": expected}, answer)
if behaviour == "crash":
    sys.exit(1)
