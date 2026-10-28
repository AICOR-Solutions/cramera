"""
What the viewer's page reads from the live publisher on this machine, relayed through
the viewer's own origin.

The publisher answers this machine only, since a query runs code. A page opened from
another device of the network, such as a phone, reaches only the viewer, so the viewer
reads the publisher for it: the observations the page follows a run by, and nothing that
changes the run.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from http import HTTPStatus
from http.client import HTTPConnection, HTTPException
from urllib.parse import urlencode

from typing_extensions import FrozenSet, Mapping

from cramera.exceptions import LivePublisherUnreachable, UnknownLiveRead
from cramera.http.addresses import url_of
from cramera.http.messages import Header, HttpMethod, MediaType, Request, Response
from cramera_protocol.live import LIVE_HOST, LIVE_PORT, LiveRoute
from cramera_protocol.live_messages import LiveParameter

RELAYED_READS: Mapping[LiveRoute, FrozenSet[LiveParameter]] = {
    LiveRoute.INFO: frozenset(),
    LiveRoute.STATE: frozenset(),
    LiveRoute.PLAN: frozenset(),
    LiveRoute.STATECHART: frozenset(),
    LiveRoute.RECORDING: frozenset(),
    LiveRoute.LIVE_SCENE: frozenset(),
    LiveRoute.RESOLUTIONS: frozenset(),
    LiveRoute.QUERY_STEPS: frozenset({LiveParameter.REVISION}),
    LiveRoute.PERCEPTION_IMAGE: frozenset({LiveParameter.KEY}),
}
"""
The routes the page reads to follow a run, each with the query parameters it takes; no
other route, and no other parameter, is relayed.
"""

RELAY_TIMEOUT = 30.0
"""
Seconds to wait for the publisher's answer, which includes bundling its world the first
time the page asks for the live scene.
"""

MEDIA_TYPES: Mapping[str, MediaType] = {
    media_type.value: media_type for media_type in MediaType
}
"""
The media types the viewer answers in, by the ``Content-Type`` that names them.
"""

# %% relay


@dataclass(frozen=True)
class LiveRelay:
    """
    Reads the live publisher on this machine for pages that cannot reach it themselves.
    """

    host: str = LIVE_HOST
    """
    The address the publisher listens on, one of this machine's own.
    """

    port: int = LIVE_PORT
    """
    The port the publisher listens on.
    """

    timeout: float = RELAY_TIMEOUT
    """
    Seconds to wait for the publisher's answer.
    """

    def address(self) -> str:
        """
        :return: The publisher's base URL.
        """
        return url_of(self.host, self.port)

    def answer(self, request: Request, route: str) -> Response:
        """
        :param request: A read below the relay's prefix.
        :param route: The publisher's route, relative to the prefix.
        :return: The publisher's answer, as it gave it.
        :raises UnknownLiveRead: When the page does not read the route.
        :raises LivePublisherUnreachable: When no live publisher answers.
        """
        path = f"/{route}"
        if path not in RELAYED_READS:
            raise UnknownLiveRead(route)
        pairs = [
            (name, value)
            for name, values in request.parameters().items()
            if name in RELAYED_READS[path]
            for value in values
        ]
        return self.read(f"{path}?{urlencode(pairs)}" if pairs else path)

    def read(self, target: str) -> Response:
        """
        The relay is where a publisher that does not answer becomes an answer, so this
        is where connection errors are caught.

        :param target: The path and query of a read.
        :return: The publisher's answer.
        :raises LivePublisherUnreachable: When no live publisher answers.
        """
        connection = HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            with closing(connection):
                connection.request(HttpMethod.GET, target)
                answer = connection.getresponse()
                body = answer.read()
        except (OSError, HTTPException) as error:
            raise LivePublisherUnreachable(
                self.address(), str(error) or type(error).__name__
            ) from error
        media_type = MEDIA_TYPES.get(answer.getheader(Header.CONTENT_TYPE, ""))
        if media_type is None:
            raise LivePublisherUnreachable(
                self.address(), "the service answering there is no live publisher"
            )
        return Response(
            status=HTTPStatus(answer.status), body=body, media_type=media_type
        )
