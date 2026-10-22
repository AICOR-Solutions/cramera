"""
Routes and the router that picks the route answering a request.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from http import HTTPStatus

from typing_extensions import Callable, List

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

    def answer(self, request: Request) -> Response:
        """
        :param request: A request.
        :return: The matching route's response; 404 when no route matches the path,
            405 when routes match the path but not the method.
        """
        method = HttpMethod.GET if request.method is HttpMethod.HEAD else request.method
        matching = [route for route in self.routes if route.matches(request.path)]
        if not matching:
            return Response.of_error(
                HTTPStatus.NOT_FOUND, f"Nothing is served at {request.path}."
            )
        for route in matching:
            if route.method is method:
                return route.answer(request)
        return Response.of_error(
            HTTPStatus.METHOD_NOT_ALLOWED,
            f"{request.path} does not answer {request.method.value}.",
        )
