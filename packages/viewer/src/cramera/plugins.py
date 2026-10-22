"""
Viewer plugins: packages that add routes, browser modules and capabilities.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path

from typing_extensions import Callable, Iterable, List, Optional

from cramera.exceptions import DuplicatePlugin, InvalidPluginName
from cramera.http.messages import HttpMethod
from cramera.http.routing import RequestHandler
from cramera.locations import DataLocations
from cramera.scenes import SceneCatalog
from cramera_protocol.live import Capability
from cramera_protocol.viewer import PluginGroup, PluginInfo, ViewerRoute

# %% plugin interface


@dataclass(frozen=True)
class PluginContext:
    """
    What the viewer gives a plugin to build its routes from.
    """

    catalog: SceneCatalog
    """
    The scenes the viewer shows.
    """

    locations: DataLocations
    """
    Where cramera keeps its data.
    """


@dataclass(frozen=True)
class PluginRoute:
    """
    One route of a plugin, served at ``/api/plugins/<plugin>/<path>``.
    """

    method: HttpMethod
    """
    The method the route answers.
    """

    path: str
    """
    The route's path below the plugin's prefix, without a leading ``/``.
    """

    handler: RequestHandler
    """
    Answers the requests.
    """


class ViewerPlugin(ABC):
    """
    A package that extends the viewer.
    """

    @abstractmethod
    def name(self) -> str:
        """
        :return: The plugin's name: lowercase letters, digits and ``-``; it is also
            the plugin's route segment.
        """

    @abstractmethod
    def version(self) -> str:
        """
        :return: The plugin's version.
        """

    def capabilities(self) -> List[Capability]:
        """
        :return: What the plugin adds; nothing by default.
        """
        return []

    def routes(self, context: PluginContext) -> List[PluginRoute]:
        """
        :param context: What the viewer offers the plugin.
        :return: The plugin's routes; none by default.
        """
        return []

    def web_directory(self) -> Optional[Path]:
        """
        :return: The directory of the plugin's browser files, or None for a plugin
            without any.
        """
        return None

    def module(self) -> Optional[str]:
        """
        :return: The plugin's browser module, relative to :meth:`web_directory`, or
            None for a plugin without one.
        """
        return None

    def info(self) -> PluginInfo:
        """
        :return: The plugin as the browser learns about it.
        """
        module = self.module()
        return PluginInfo(
            name=self.name(),
            version=self.version(),
            module=(
                None
                if module is None
                else f"{ViewerRoute.PLUGIN_FILES}{self.name()}/{module}"
            ),
            capabilities=self.capabilities(),
        )


PluginFactory = Callable[[], ViewerPlugin]
"""
What a plugin's entry point names: a callable that creates the plugin.
"""


# %% discovery


@dataclass
class PluginLoader:
    """
    Creates the installed plugins from their entry points.
    """

    entry_points: Iterable[EntryPoint] = field(
        default_factory=lambda: entry_points(group=PluginGroup.VIEWER)
    )
    """
    The entry points of the viewer's plugin group.
    """

    def load(self) -> List[ViewerPlugin]:
        """
        :return: The plugins, sorted by name.
        :raises InvalidPluginName: When a plugin's name is not a route segment.
        :raises DuplicatePlugin: When two plugins share a name.
        """
        plugins = [entry_point.load()() for entry_point in self.entry_points]
        names: List[str] = []
        for plugin in plugins:
            name = plugin.name()
            if re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) is None:
                raise InvalidPluginName(name)
            if name in names:
                raise DuplicatePlugin(name)
            names.append(name)
        return sorted(plugins, key=lambda plugin: plugin.name())
