"""
The viewer's own routes, environment variables and plugin entry points.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import List, Optional

from cramera_protocol.document import JsonDocument, document_field
from cramera_protocol.live import Capability
from cramera_protocol.version import CURRENT_VERSION, ProtocolVersion

# %% routes


class ViewerRoute(StrEnum):
    """
    The routes the viewer itself serves; plugins add routes below :attr:`PLUGIN_API`.
    """

    INFO = "/api/info"
    """
    The viewer's version, its plugins and their capabilities.
    """

    SCENES = "/api/scenes"
    """
    The merged index of every scenes directory.
    """

    SCENE_FILES = "/scenes/"
    """
    The prefix of bundle files: ``/scenes/<bundle>/<file>``.
    """

    PROTOCOL_MODULE = "/protocol.js"
    """
    The protocol's names as an ES module for the browser.
    """

    PLUGIN_FILES = "/plugins/"
    """
    The prefix of plugin browser files: ``/plugins/<plugin>/<file>``.
    """

    PLUGIN_API = "/api/plugins/"
    """
    The prefix of plugin routes: ``/api/plugins/<plugin>/<route>``.
    """


# %% answers


class ErrorKey(StrEnum):
    """
    The keys of an error answer of the viewer or a live publisher.
    """

    ERROR = "error"
    """
    The reason the request failed.
    """


# %% environment


class EnvironmentVariable(StrEnum):
    """
    The environment variables cramera reads.
    """

    SCENES = "CRAMERA_SCENES"
    """
    The shared scenes directory.
    """

    DATA = "CRAMERA_DATA"
    """
    The directory of cramera's own data; local recordings go to its ``scenes``.
    """


# %% plugins


class PluginGroup(StrEnum):
    """
    The entry-point groups cramera discovers.
    """

    VIEWER = "cramera.plugins"
    """
    Plugins of the viewer; each entry point names a factory of a viewer plugin.
    """


class PluginKey(StrEnum):
    """
    The keys of one plugin in the viewer's information.
    """

    NAME = "name"
    """
    The plugin's name.
    """

    VERSION = "version"
    """
    The plugin's version.
    """

    MODULE = "module"
    """
    The URL of the plugin's browser module.
    """

    CAPABILITIES = "capabilities"
    """
    What the plugin adds.
    """


@dataclass(kw_only=True)
class PluginInfo(JsonDocument):
    """
    One loaded plugin as the browser learns about it.
    """

    name: str = document_field(PluginKey.NAME)
    """
    The plugin's name, which is also its route segment.
    """

    version: str = document_field(PluginKey.VERSION)
    """
    The plugin's version.
    """

    module: Optional[str] = document_field(PluginKey.MODULE, default=None)
    """
    The URL of the plugin's browser module, or None for a plugin without one.
    """

    capabilities: List[Capability] = document_field(
        PluginKey.CAPABILITIES, default_factory=list
    )
    """
    What the plugin adds.
    """


class BuildKey(StrEnum):
    """
    The keys of a build stamp.
    """

    COMMIT = "commit"
    """
    The commit the build was made from.
    """

    BUILT_AT = "builtAt"
    """
    When the build was made.
    """

    SOURCE = "source"
    """
    The repository the build was made from.
    """


@dataclass(kw_only=True)
class BuildStamp(JsonDocument):
    """
    Which commit a published build of the viewer shows, and when it was made.
    """

    commit: str = document_field(BuildKey.COMMIT)
    """
    The full hash of the commit the build was made from.
    """

    built_at: str = document_field(BuildKey.BUILT_AT)
    """
    When the build was made, as an ISO 8601 date and time in UTC.
    """

    source: Optional[str] = document_field(BuildKey.SOURCE, default=None)
    """
    The web address of the repository the build was made from.
    """


class ViewerInfoKey(StrEnum):
    """
    The keys of the answer to :attr:`ViewerRoute.INFO`.
    """

    PROTOCOL_VERSION = "protocolVersion"
    """
    The protocol version the viewer speaks.
    """

    VERSION = "version"
    """
    The viewer's version.
    """

    PLUGINS = "plugins"
    """
    The loaded plugins.
    """

    BUILD = "build"
    """
    The build stamp of a published build.
    """


@dataclass(kw_only=True)
class ViewerInfo(JsonDocument):
    """
    What the viewer says about itself.
    """

    version: str = document_field(ViewerInfoKey.VERSION)
    """
    The viewer's version.
    """

    protocol_version: ProtocolVersion = document_field(
        ViewerInfoKey.PROTOCOL_VERSION, default=CURRENT_VERSION
    )
    """
    The protocol version the viewer speaks.
    """

    plugins: List[PluginInfo] = document_field(
        ViewerInfoKey.PLUGINS, default_factory=list
    )
    """
    The loaded plugins.
    """

    build: Optional[BuildStamp] = document_field(ViewerInfoKey.BUILD, default=None)
    """
    The build stamp of a published build, or None for a viewer served from an
    installation.
    """
