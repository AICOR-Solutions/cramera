"""
The plugin API, version 1 (:func:`api_version`): everything a viewer plugin built on the
plan builder needs, in one module, so a plugin imports this facade and the protocol
(:mod:`cramera_protocol`) and nothing else of cramera.

It holds the viewer's plugin interface (a plugin subclasses :class:`ViewerPlugin`,
declares routes and raises subclasses of :class:`ViewerError`, which a route answers
with the error's message and status), the plan builder's services
(:class:`PlanBuilderServices`: its saved plans, the configured robot profile, the object
catalogue, the page that opens a plan) and the identifier registry. Names leave it only
with a new major version; a new minor version only adds names. The browser side is the
JavaScript SDK the viewer serves at ``/sdk/v1/index.js``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from typing_extensions import Mapping, Optional, Self

from cramera.exceptions import ViewerError
from cramera.http.messages import HttpMethod, Request, Response
from cramera.plugins import (
    PLUGIN_API_VERSION,
    NavigationEntry,
    PageEntry,
    PanelEntry,
    PluginContext,
    PluginPrefixRoute,
    PluginRoute,
    RouteDeclaration,
    ViewerPlugin,
)
from cramera_plan_builder.plans import PlanStore
from cramera_plan_builder.plugin import PlanBuilderStorage
from cramera_plan_builder.profiles import ConfiguredProfile
from cramera_protocol.object_library import ObjectCatalog
from cramera_protocol.plan_builder import (
    PlanBuilderFile,
    PlanBuilderName,
    PlanBuilderPageParameter,
)
from cramera_protocol.registry import IdKind, IdStatus, Registry
from cramera_protocol.robot_profile import RobotProfileVariable
from cramera_protocol.version import ProtocolVersion
from cramera_protocol.viewer import NavigationGroup, ViewerRoute

__all__ = [
    "ConfiguredProfile",
    "HttpMethod",
    "IdKind",
    "IdStatus",
    "NavigationEntry",
    "NavigationGroup",
    "ObjectCatalog",
    "PageEntry",
    "PanelEntry",
    "PlanBuilderServices",
    "PlanStore",
    "PluginContext",
    "PluginPrefixRoute",
    "PluginRoute",
    "Registry",
    "Request",
    "Response",
    "RouteDeclaration",
    "ViewerError",
    "ViewerPlugin",
    "api_version",
]

# %% version


def api_version() -> ProtocolVersion:
    """
    :return: The version of the plugin API this installation offers; the viewer refuses
        a plugin whose :meth:`ViewerPlugin.api_version` has another major version.
    """
    return PLUGIN_API_VERSION


# %% services


@dataclass(frozen=True)
class PlanBuilderServices:
    """
    What the plan builder offers a plugin.
    """

    plans: PlanStore
    """
    The plan builder's saved plans.
    """

    profile: ConfiguredProfile
    """
    The configured robot profile, which may be none.
    """

    profile_path: Optional[Path]
    """
    The robot profile's file, which its templates and simulated scene are read relative
    to, or None.
    """

    objects: ObjectCatalog
    """
    What the object libraries say about the object models.
    """

    registry: Registry
    """
    The robots and actions the installed packages declare.
    """

    @classmethod
    def of(cls, context: PluginContext, environment: Mapping[str, str]) -> Self:
        """
        :param context: What the viewer gives the plugin.
        :param environment: The process environment, which names the robot profile and
            the object libraries.
        :return: The services the plan builder of this viewer uses.
        """
        configured = environment.get(RobotProfileVariable.PROFILE)
        return cls(
            plans=PlanStore(PlanBuilderStorage.of(context.locations, environment).plans),
            profile=ConfiguredProfile.of_environment(environment),
            profile_path=None if configured is None else Path(configured).expanduser(),
            objects=ObjectCatalog.from_environment(environment),
            registry=Registry.installed(),
        )

    @staticmethod
    def plan_builder_page(plan: str) -> str:
        """
        :param plan: A saved plan's identity.
        :return: The address of the plan builder's page opening it.
        """
        return (
            f"{ViewerRoute.PLUGIN_FILES}{PlanBuilderName.PLUGIN}/{PlanBuilderFile.PAGE}"
            f"?{PlanBuilderPageParameter.PLAN}={plan}"
        )
