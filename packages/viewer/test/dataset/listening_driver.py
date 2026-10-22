"""
A stand-in for a WebDriver program: listens on the port given as ``--port=N`` until it
is terminated.
"""

import signal
import socket
import sys

port = int(
    next(argument for argument in sys.argv if argument.startswith("--port=")).split(
        "="
    )[1]
)
listener = socket.socket()
listener.bind(("127.0.0.1", port))
listener.listen()
signal.sigwait({signal.SIGTERM})
