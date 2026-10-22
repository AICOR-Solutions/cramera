"""
Serving a presentation with the viewer's own server: only the presentation's bundles,
only from this machine, and pages that load nothing from elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from typing_extensions import List, Optional

from cramera.application import ViewerApplication
from cramera.http.messages import Request, Response
from cramera.http.origin import OriginPolicy
from cramera.http.server import HttpServer, RequestAnswerer
from cramera.locations import DataLocations
from cramera.plugins import PluginLoader, ViewerPlugin
from cramera.scenes import SceneCatalog
from cramera_offline.isolation import InheritedSocketServer
from cramera_offline.presentation import PresentationDirectory

# %% headers


class PresentationHeader(StrEnum):
    """
    The headers that confine a presentation page.
    """

    CONTENT_SECURITY_POLICY = "Content-Security-Policy"
    """
    Where the page may load scripts, styles, images and data from.
    """

    PERMISSIONS_POLICY = "Permissions-Policy"
    """
    Which devices the page may use.
    """


@dataclass(frozen=True)
class PresentationPolicy:
    """
    What a presentation page may load and use: only its own origin, no camera and no
    microphone.
    """

    content_security_policy: str = (
        "default-src 'self'; connect-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
        "font-src 'self' data:; worker-src 'self' blob:; object-src 'none'; "
        "base-uri 'self'; form-action 'self'"
    )
    """
    The page's content security policy; inline scripts stay allowed for the import map
    of the viewer's page, inline styles for the plots.
    """

    permissions_policy: str = "camera=(), microphone=(), geolocation=()"
    """
    The page's permissions policy.
    """


@dataclass(frozen=True)
class PresentationAnswerer(RequestAnswerer):
    """
    Answers like the viewer and adds the presentation's policy headers to every answer.
    """

    presentation_policy: PresentationPolicy = field(default_factory=PresentationPolicy)
    """
    What the page may load and use.
    """

    def answer(self, request: Request) -> Response:
        response = super().answer(request)
        response.headers[PresentationHeader.CONTENT_SECURITY_POLICY] = (
            self.presentation_policy.content_security_policy
        )
        response.headers[PresentationHeader.PERMISSIONS_POLICY] = (
            self.presentation_policy.permissions_policy
        )
        return response


# %% server


@dataclass
class PresentationServer:
    """
    Builds the viewer server of one presentation.
    """

    presentation: PresentationDirectory
    """
    The presentation to serve.
    """

    plugins: List[ViewerPlugin] = field(default_factory=lambda: PluginLoader().load())
    """
    The installed viewer plugins, the offline plugin among them.
    """

    def answerer(self) -> PresentationAnswerer:
        """
        :return: The viewer's routes over the presentation's bundles alone.
        """
        directory = self.presentation.scene_directory()
        application = ViewerApplication(
            catalog=SceneCatalog([directory]),
            locations=DataLocations(
                data=self.presentation.path, shared_scenes=directory.path
            ),
            plugins=self.plugins,
        )
        return PresentationAnswerer(router=application.router(), policy=OriginPolicy())

    def server(self, host: str, port: int, descriptor: Optional[int]) -> HttpServer:
        """
        :param host: The loopback address to listen on.
        :param port: The port to listen on; 0 picks a free port.
        :param descriptor: An inherited listening socket to answer on instead, or
            None to open one.
        :return: The server, not yet started.
        """
        if descriptor is not None:
            return InheritedSocketServer(
                answerer=self.answerer(), descriptor=descriptor
            )
        return HttpServer(answerer=self.answerer(), host=host, port=port)
