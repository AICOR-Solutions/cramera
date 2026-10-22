"""
A WebDriver server that answers like a browser driver showing a viewer page.
"""

from __future__ import annotations

import base64
import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from typing_extensions import Any, Dict, List, Optional

from cramera.screenshot import WebDriverEndpoint, WebDriverKey
from cramera_protocol.events import PageReportKey

MIMIC_SESSION = "mimic"
"""
The identity of the only session the mimic creates.
"""

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
"""
The bytes every PNG file starts with; the mimic's screenshot is just this.
"""


@dataclass
class MimicWebDriver:
    """
    Answers the WebDriver requests a screenshot sends; the page reports the given states
    one after another.
    """

    states: List[Optional[str]]
    """
    The page states the state script returns, in order; the last one repeats.
    """

    status: str = "Scene shown"
    """
    The status line the page reports.
    """

    requests: List[str] = field(default_factory=list)
    """
    The method and path of every request received.
    """

    server: Optional[ThreadingHTTPServer] = None
    """
    The listening server while started.
    """

    def start(self) -> int:
        """
        :return: The port the mimic listens on.
        """
        mimic = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                self.reply(mimic.answer("POST", self.path, self.read_body()))

            def do_GET(self) -> None:
                self.reply(mimic.answer("GET", self.path, None))

            def do_DELETE(self) -> None:
                self.reply(mimic.answer("DELETE", self.path, None))

            def read_body(self) -> Any:
                length = int(self.headers.get("Content-Length", "0"))
                return json.loads(self.rfile.read(length)) if length else None

            def reply(self, value: Any) -> None:
                body = json.dumps({WebDriverKey.VALUE: value}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *arguments: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self.server.server_address[1]

    def stop(self) -> None:
        """
        Stop the mimic.
        """
        self.server.shutdown()
        self.server.server_close()

    def answer(self, method: str, path: str, body: Any) -> Any:
        """
        :param method: The request method.
        :param path: The request path.
        :param body: The decoded JSON body.
        :return: The ``value`` of the answer.
        """
        self.requests.append(f"{method} {path}")
        endpoint = WebDriverEndpoint(MIMIC_SESSION)
        if path == endpoint.new_session():
            return {WebDriverKey.SESSION_IDENTIFIER: MIMIC_SESSION}
        if path == endpoint.script():
            state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
            return {PageReportKey.STATE: state, PageReportKey.STATUS: self.status}
        if path == endpoint.screenshot():
            return base64.b64encode(PNG_SIGNATURE).decode()
        return None

    def calls(self) -> Dict[str, int]:
        """
        :return: How often each request was received.
        """
        counts: Dict[str, int] = {}
        for request in self.requests:
            counts[request] = counts.get(request, 0) + 1
        return counts
