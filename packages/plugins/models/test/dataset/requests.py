"""
Requests as a page on this machine sends them to the models plugin.
"""

from __future__ import annotations

import json

from typing_extensions import Any

from cramera.http.messages import Header, HttpMethod, Request, Response
from cramera_protocol.models import ModelsRoute
from cramera_protocol.plugins import PluginName
from cramera_protocol.viewer import ViewerRoute

LOCAL_HOST = {Header.HOST.value: "127.0.0.1:8711"}
"""
The headers of a request addressed to this machine.
"""


def route_path(route: ModelsRoute) -> str:
    """
    :param route: A route of the models plugin.
    :return: The path the viewer serves it at.
    """
    return f"{ViewerRoute.PLUGIN_API}{PluginName.MODELS}/{route}"


def local_get(route: ModelsRoute) -> Request:
    """
    :param route: A route of the models plugin.
    :return: A GET request of it addressed to this machine.
    """
    return Request(method=HttpMethod.GET, path=route_path(route), headers=LOCAL_HOST)


def local_post(route: ModelsRoute, body: bytes) -> Request:
    """
    :param route: A route of the models plugin.
    :param body: The request body.
    :return: A POST request of it addressed to this machine.
    """
    return Request(
        method=HttpMethod.POST, path=route_path(route), headers=LOCAL_HOST, body=body
    )


def answer_json(response: Response) -> Any:
    """
    :param response: A JSON response.
    :return: Its decoded body.
    """
    return json.loads(response.body)
