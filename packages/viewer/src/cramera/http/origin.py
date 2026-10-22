"""
Which pages may talk to the viewer: only pages served from this machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from http import HTTPStatus
from urllib.parse import urlsplit

from typing_extensions import FrozenSet, Optional

from cramera.http.messages import Header, HttpMethod, Request, Response

LOCAL_HOSTS: FrozenSet[str] = frozenset({"localhost", "127.0.0.1", "::1"})
"""
The host names of this machine.
"""

# %% policy


@dataclass(frozen=True)
class OriginPolicy:
    """
    Refuses requests from pages of other origins and requests addressed to other host
    names, so neither another website nor a rebound domain name can reach the viewer or
    a live publisher.
    """

    allowed_hosts: FrozenSet[str] = field(default=LOCAL_HOSTS)
    """
    The host names requests may address and pages may be served from.
    """

    def refusal(self, request: Request) -> Optional[Response]:
        """
        :param request: A request.
        :return: A 403 response when the request must not be answered, else None.
        """
        if not self.is_allowed_host(request.header(Header.HOST)):
            return Response.of_error(
                HTTPStatus.FORBIDDEN, "This host name is not served."
            )
        origin = request.header(Header.ORIGIN)
        if origin is not None and not self.is_allowed_origin(origin):
            return Response.of_error(
                HTTPStatus.FORBIDDEN, "Pages of this origin are refused."
            )
        return None

    def is_allowed_host(self, host: Optional[str]) -> bool:
        """
        :param host: The ``Host`` header, with or without a port.
        :return: Whether it names an allowed host.
        """
        if host is None:
            return False
        return urlsplit(f"//{host}").hostname in self.allowed_hosts

    def is_allowed_origin(self, origin: str) -> bool:
        """
        :param origin: The ``Origin`` header.
        :return: Whether it is an http or https origin of an allowed host.
        """
        parts = urlsplit(origin)
        return (
            parts.scheme in ("http", "https") and parts.hostname in self.allowed_hosts
        )

    def preflight(self, request: Request) -> Response:
        """
        :param request: An ``OPTIONS`` request that passed :meth:`refusal`.
        :return: The answer allowing the page's cross-origin request.
        """
        response = Response(status=HTTPStatus.NO_CONTENT)
        response.headers[Header.ALLOW_METHODS] = ", ".join(
            method.value for method in (HttpMethod.GET, HttpMethod.POST)
        )
        response.headers[Header.ALLOW_HEADERS] = Header.CONTENT_TYPE.value
        return self.addressed(request, response)

    def addressed(self, request: Request, response: Response) -> Response:
        """
        :param request: A request that passed :meth:`refusal`.
        :param response: Its response.
        :return: The response, readable by the requesting page when that page has an
            allowed origin.
        """
        origin = request.header(Header.ORIGIN)
        if origin is not None:
            response.headers[Header.ALLOW_ORIGIN] = origin
            response.headers[Header.VARY] = Header.ORIGIN.value
        return response
