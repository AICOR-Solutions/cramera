"""
Which pages may talk to the viewer: pages served from this machine, by its local name or
by the address a request arrived at.

Other devices of the network need the viewer's key and may only read. Behind a password-
checking proxy on this machine, every request is another device's, and such devices may
also make the changes routes offer them.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass, field
from http import HTTPStatus
from urllib.parse import urlsplit

from typing_extensions import FrozenSet, Optional

from cramera.http.addresses import is_loopback
from cramera.http.messages import Header, HttpMethod, Request, Response
from cramera.http.routing import Route

LOCAL_HOSTS: FrozenSet[str] = frozenset({"localhost", "127.0.0.1", "::1"})
"""
The host names of this machine.
"""

KEY_PARAMETER = "key"
"""
The query parameter another device's first request carries the key in.
"""

KEY_COOKIE = "cramera_key"
"""
The cookie that carries the key in another device's later requests.
"""

# %% policy


@dataclass(frozen=True)
class OriginPolicy:
    """
    Refuses requests from pages of other origins and requests addressed to other host
    names, so neither another website nor a rebound domain name can reach the viewer or
    a live publisher.

    A server listening beyond the loopback address is also reached by the address a
    request arrived at, which is how a phone of the same network opens the viewer. A
    request from another device must carry the :attr:`key` and may read, but not change
    anything.

    Behind a proxy (:attr:`proxied`), every request is another device's; it needs no key,
    since the proxy checked the password, and may also make the changes a route offers
    other devices (:attr:`~cramera.http.routing.Route.remote_changes`). A route only this
    machine may use (:attr:`~cramera.http.routing.Route.local_only`) is refused to other
    devices either way.
    """

    allowed_hosts: FrozenSet[str] = field(default=LOCAL_HOSTS)
    """
    The host names requests may address and pages may be served from, besides the
    address a request arrived at.
    """

    key: Optional[str] = None
    """
    The key requests from other devices must carry, in the query of the address the
    viewer names or in the cookie the answer to it sets; None refuses other devices.
    """

    proxied: bool = False
    """
    Whether every request comes through a reverse proxy on this machine that checked its
    password, so it counts as another device's and that device may control runs.
    """

    def refusal(
        self, request: Request, route: Optional[Route] = None
    ) -> Optional[Response]:
        """
        :param request: A request.
        :param route: The route that answers it, or None when none does.
        :return: A 403 response when the request must not be answered, else None.
        """
        if not self.is_allowed_host(request.header(Header.HOST), request):
            return Response.of_error(
                HTTPStatus.FORBIDDEN, "This host name is not served."
            )
        origin = request.header(Header.ORIGIN)
        if origin is not None and not self.is_allowed_origin(origin, request):
            return Response.of_error(
                HTTPStatus.FORBIDDEN, "Pages of this origin are refused."
            )
        if self.is_from_this_machine(request):
            return None
        if not self.is_admitted(request):
            return Response.of_error(
                HTTPStatus.FORBIDDEN,
                "Other devices open the address with the key the viewer named when it "
                "started.",
            )
        if route is not None and route.local_only:
            return Response.of_error(
                HTTPStatus.FORBIDDEN,
                "Only the machine that serves the viewer may ask this.",
            )
        if request.method.changes() and not self.lets_change(route):
            return Response.of_error(HTTPStatus.FORBIDDEN, self.change_refusal())
        return None

    def lets_change(self, route: Optional[Route]) -> bool:
        """
        :param route: The route that answers another device's change, or None.
        :return: Whether that device may make the change: only behind the proxy, and
            only where the route offers it.
        """
        return self.proxied and route is not None and route.remote_changes

    def change_refusal(self) -> str:
        """
        :return: Why another device may not make a change.
        """
        if self.proxied:
            return (
                "Over the network the viewer only starts, stops and steps runs; "
                "everything else stays with the machine that serves it."
            )
        return (
            "Other devices may only watch; ask, run and save on the machine that "
            "serves the viewer."
        )

    def is_allowed_host(self, host: Optional[str], request: Request) -> bool:
        """
        :param host: The ``Host`` header, with or without a port.
        :param request: The request it addresses.
        :return: Whether it names an allowed host or the address the request arrived at.
        """
        if host is None:
            return False
        return self.is_served(urlsplit(f"//{host}").hostname, request)

    def is_allowed_origin(self, origin: str, request: Request) -> bool:
        """
        :param origin: The ``Origin`` header.
        :param request: The request it comes with.
        :return: Whether it is an http or https origin of an allowed host or of the
            address the request arrived at.
        """
        parts = urlsplit(origin)
        return parts.scheme in ("http", "https") and self.is_served(
            parts.hostname, request
        )

    def is_served(self, hostname: Optional[str], request: Request) -> bool:
        """
        :param hostname: A host name or IP address, as a URL names it.
        :param request: The request it comes with.
        :return: Whether it is an allowed host or the address the request arrived at; a
            name other than an allowed one is refused, so a rebound domain name is.
        """
        return hostname in self.allowed_hosts or hostname == request.server_address

    def is_from_this_machine(self, request: Request) -> bool:
        """
        :param request: A request.
        :return: Whether it was sent from this machine: from a loopback address, or
            from the address it arrived at; behind the proxy no request is.
        """
        if self.proxied:
            return False
        return (
            is_loopback(request.client_address)
            or request.client_address == request.server_address
        )

    def is_admitted(self, request: Request) -> bool:
        """
        :param request: A request from another device.
        :return: Whether it carries the key, in its query or its cookie; behind the
            proxy every request is, since the proxy checked its password.
        """
        if self.proxied:
            return True
        offered = request.parameters().get(KEY_PARAMETER, [])
        offered.append(request.cookie(KEY_COOKIE))
        return any(self.is_key(candidate) for candidate in offered)

    def is_key(self, candidate: Optional[str]) -> bool:
        """
        :param candidate: A key a request offers, or None.
        :return: Whether it is the key, compared in constant time.
        """
        if not self.key or candidate is None:
            return False
        return hmac.compare_digest(candidate.encode(), self.key.encode())

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
            allowed origin, and keeping the key in a cookie when the request's query
            carries it.
        """
        origin = request.header(Header.ORIGIN)
        if origin is not None:
            response.headers[Header.ALLOW_ORIGIN] = origin
            response.headers[Header.VARY] = Header.ORIGIN.value
        if any(map(self.is_key, request.parameters().get(KEY_PARAMETER, []))):
            # the page's own requests carry no query, so the key goes on in a cookie
            response.headers[Header.SET_COOKIE] = (
                f"{KEY_COOKIE}={self.key}; Path=/; HttpOnly; SameSite=Strict"
            )
        return response
