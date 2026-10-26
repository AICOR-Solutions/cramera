"""
Routes and the router that picks the route answering a request.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from http import HTTPStatus

from typing_extensions import Callable, List, Optional

from cramera.http.messages import HttpMethod, Request, Response

RequestHandler = Callable[[Request], Response]
"""
A function that answers a request.
"""

PrefixHandler = Callable[[Request, str], Response]
"""
A function that answers a request, given the part of its path after a prefix.
"""

# %% routes


@dataclass(frozen=True)
class Route(ABC):
    """
    Answers requests of one method whose paths it matches.
    """

    method: HttpMethod
    """
    The method the route answers.
    """

    streams_body: bool = field(default=False, kw_only=True)
    """
    Whether the route reads the request body itself, from :attr:`Request.stream`,
    instead of the server reading it into memory first; for uploads larger than memory.
    """

    @abstractmethod
    def matches(self, path: str) -> bool:
        """
        :param path: A request path.
        :return: Whether this route answers requests for the path.
        """

    @abstractmethod
    def answer(self, request: Request) -> Response:
        """
        :param request: A request whose path this route matches.
        :return: The response.
        """


@dataclass(frozen=True)
class ExactRoute(Route):
    """
    A route for one path.
    """

    path: str
    """
    The path the route answers.
    """

    handler: RequestHandler
    """
    Answers the requests.
    """

    def matches(self, path: str) -> bool:
        return path == self.path

    def answer(self, request: Request) -> Response:
        return self.handler(request)


@dataclass(frozen=True)
class PrefixRoute(Route):
    """
    A route for every path below a prefix; the handler receives the rest of the path.
    """

    prefix: str
    """
    The path prefix, ending in ``/``.
    """

    handler: PrefixHandler
    """
    Answers the requests, given the path after the prefix.
    """

    def matches(self, path: str) -> bool:
        return path.startswith(self.prefix)

    def answer(self, request: Request) -> Response:
        return self.handler(request, request.path[len(self.prefix) :])


# %% router


@dataclass
class Router:
    """
    Picks the first route that answers a request; earlier routes win.
    """

    routes: List[Route] = field(default_factory=list)
    """
    The routes, in the order they are tried.
    """

    def add(self, route: Route) -> None:
        """
        :param route: A route tried after the routes added before it.
        """
        self.routes.append(route)

    def route(self, method: HttpMethod, path: str) -> Optional[Route]:
        """
        :param method: A request's method.
        :param path: A request's path.
        :return: The route that answers such a request, or None.
        """
        wanted = HttpMethod.GET if method is HttpMethod.HEAD else method
        return next(
            (
                route
                for route in self.routes
                if route.matches(path) and route.method is wanted
            ),
            None,
        )

    def streams_body(self, method: HttpMethod, path: str) -> bool:
        """
        :param method: A request's method.
        :param path: A request's path.
        :return: Whether the route answering such a request reads its body itself.
        """
        route = self.route(method, path)
        return route is not None and route.streams_body

    def answer(self, request: Request) -> Response:
        """
        :param request: A request.
        :return: The matching route's response; 404 when no route matches the path,
            405 when routes match the path but not the method.
        """
        if not any(route.matches(request.path) for route in self.routes):
            return Response.of_error(
                HTTPStatus.NOT_FOUND, f"Nothing is served at {request.path}."
            )
        route = self.route(request.method, request.path)
        if route is not None:
            return route.answer(request)
        return Response.of_error(
            HTTPStatus.METHOD_NOT_ALLOWED,
            f"{request.path} does not answer {request.method.value}.",
        )
