"""
Requests as a page on this machine sends them.
"""

from __future__ import annotations

import json

from typing_extensions import Any

from cramera.http.messages import Header, HttpMethod, Request, Response

LOCAL_HOST = {Header.HOST.value: "127.0.0.1:8713"}
"""
The headers of a request addressed to this machine.
"""


def local_request(path: str, query: str = "") -> Request:
    """
    :param path: The requested path.
    :param query: The query, without ``?``.
    :return: A GET request addressed to this machine.
    """
    return Request(method=HttpMethod.GET, path=path, query=query, headers=LOCAL_HOST)


def answer_json(response: Response) -> Any:
    """
    :param response: A JSON response.
    :return: Its decoded body.
    """
    return json.loads(response.body)
