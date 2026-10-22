"""
A stand-in for the generated demo of ${name} (${file_name}) that ignores a request to
end, so it has to be killed.
"""

import signal
import threading

DEMO = r"""
${demo}
"""

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    print("ignoring termination", flush=True)
    threading.Event().wait()
