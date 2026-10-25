"""
A task that ignores termination so shutdown must reap it by force.
"""

import signal
import time

signal.signal(signal.SIGTERM, signal.SIG_IGN)
print("ready", flush=True)
time.sleep(60)
