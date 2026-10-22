"""
The HTTP server: one socket and one serving thread, owned by a context.
"""

from __future__ import annotations

import logging
import socket
import sys
import threading
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from typing_extensions import Optional, Self, Tuple, Type

from cramera.exceptions import ViewerError
from cramera.http.messages import CacheDirective, Header, HttpMethod, Request, Response
from cramera.http.origin import OriginPolicy
from cramera.http.routing import Router
from cramera_protocol.exceptions import ProtocolError

logger = logging.getLogger(__name__)
"""
The logger of the HTTP server.
"""

# %% answering


@dataclass(frozen=True)
class RequestAnswerer:
    """
    Answers a request through the origin policy and the router, and turns protocol and
    viewer errors into error responses.
    """

    router: Router
    """
    The routes.
    """

    policy: OriginPolicy
    """
    Which pages and host names are answered.
    """

    def answer(self, request: Request) -> Response:
        """
        :param request: A request.
        :return: The response to send.
        """
        refusal = self.policy.refusal(request)
        if refusal is not None:
            return refusal
        if request.method is HttpMethod.OPTIONS:
            return self.policy.preflight(request)
        return self.policy.addressed(request, self.routed(request))

    def routed(self, request: Request) -> Response:
        """
        The HTTP boundary is where a refused request becomes an answer, so this is where
        viewer and protocol errors are caught.

        :param request: A request the policy allows.
        :return: The router's response, or the error response of a refused request.
        """
        try:
            return self.router.answer(request)
        except ViewerError as error:
            return Response.of_error(error.status(), error.message())
        except ProtocolError as error:
            return Response.of_error(HTTPStatus.BAD_REQUEST, error.message())


# %% request handler


class RequestHandler(BaseHTTPRequestHandler):
    """
    Adapts the standard library's request handler to :class:`RequestAnswerer`.
    """

    answerer: RequestAnswerer
    """
    Set on the subclass each server creates.
    """

    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        self.respond(HttpMethod.GET)

    def do_HEAD(self) -> None:
        self.respond(HttpMethod.HEAD)

    def do_POST(self) -> None:
        self.respond(HttpMethod.POST)

    def do_OPTIONS(self) -> None:
        self.respond(HttpMethod.OPTIONS)

    def respond(self, method: HttpMethod) -> None:
        """
        Read the request, answer it and write the response.

        :param method: The request's method.
        """
        target = urlsplit(self.path)
        length = int(self.headers.get(Header.CONTENT_LENGTH, "0") or "0")
        request = Request(
            method=method,
            path=unquote(target.path),
            query=target.query,
            headers=dict(self.headers.items()),
            body=self.rfile.read(length) if length else b"",
        )
        response = self.answerer.answer(request)
        self.send_response(response.status)
        self.send_header(Header.CONTENT_TYPE, response.media_type)
        self.send_header(Header.CONTENT_LENGTH, str(len(response.body)))
        self.send_header(Header.CACHE_CONTROL, CacheDirective.NO_STORE)
        for name, value in response.headers.items():
            self.send_header(name, value)
        self.end_headers()
        if method is not HttpMethod.HEAD:
            self.wfile.write(response.body)

    def log_message(self, format: str, *arguments: object) -> None:
        logger.debug(format, *arguments)


# %% server


class ViewerHttpServer(ThreadingHTTPServer):
    """
    A threading HTTP server whose socket family follows its host, and for which a client
    that closes its connection before the answer is written is no error.
    """

    daemon_threads = True

    def __init__(self, address: Tuple[str, int], handler: Type[RequestHandler]) -> None:
        """
        :param address: The host and port to listen on; a host with ``:`` is IPv6.
        :param handler: Answers the requests.
        """
        self.address_family = socket.AF_INET6 if ":" in address[0] else socket.AF_INET
        super().__init__(address, handler)

    def handle_error(self, request: object, client_address: Tuple[str, int]) -> None:
        """
        A browser closing a connection, for example when a page is left or a newer
        request replaces an older one, is logged; other errors are reported as usual.
        """
        if isinstance(sys.exc_info()[1], ConnectionError):
            logger.debug("%s closed the connection before the answer", client_address)
            return
        super().handle_error(request, client_address)


@dataclass
class HttpServer:
    """
    Serves a router on one address from a background thread between
    :meth:`start` and :meth:`stop`, or for the duration of a ``with`` block.
    """

    answerer: RequestAnswerer
    """
    Answers the requests.
    """

    host: str = "127.0.0.1"
    """
    The address to listen on.
    """

    port: int = 0
    """
    The port to listen on; 0 picks a free port.
    """

    server: Optional[ThreadingHTTPServer] = field(default=None, init=False)
    """
    The listening server while started.
    """

    thread: Optional[threading.Thread] = field(default=None, init=False)
    """
    The serving thread while started.
    """

    def start(self) -> Self:
        """
        Open the socket and start serving.

        :return: This server.
        """
        handler: Type[RequestHandler] = type(
            "BoundRequestHandler", (RequestHandler,), {"answerer": self.answerer}
        )
        self.server = ViewerHttpServer((self.host, self.port), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def stop(self) -> None:
        """
        Stop serving, close the socket and wait for the serving thread.
        """
        if self.server is None:
            return
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.server = None
        self.thread = None

    def bound_port(self) -> int:
        """
        :return: The port the started server listens on.
        """
        return self.server.server_address[1]

    def url(self) -> str:
        """
        :return: The base URL of the started server.
        """
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.bound_port()}"

    def __enter__(self) -> Self:
        return self.start()

    def __exit__(self, *exception: object) -> None:
        self.stop()
