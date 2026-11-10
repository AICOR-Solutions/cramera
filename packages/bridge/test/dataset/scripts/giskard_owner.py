"""
Starts a Giskard that simulates Tracy, prints the process identity of its launch and
waits until it is killed.
"""

import threading

from cramera_bridge.real_robot import GiskardLaunchFile, GiskardProcess

if __name__ == "__main__":
    with GiskardProcess(GiskardLaunchFile.STANDALONE).running() as launch:
        print(launch.pid, flush=True)
        threading.Event().wait()
