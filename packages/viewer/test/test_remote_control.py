"""
Control from other devices: the policy of a viewer behind a password-checking proxy and
the route flags that say what other devices may do.
"""

from __future__ import annotations

import json
from http import HTTPStatus

import pytest

from cramera.http.messages import Header, HttpMethod, Request, Response
from cramera.http.origin import KEY_COOKIE, OriginPolicy
from cramera.http.routing import ExactRoute, PrefixRoute, Router
from cramera.http.server import RequestAnswerer
from cramera.plugins import PluginPrefixRoute, PluginRoute
from cramera_protocol.viewer import ErrorKey

PUBLIC_HOST = "cramera.example.org"
"""
The host name the proxy serves the viewer at in the tests.
"""

PROXY_POLICY = OriginPolicy(
    allowed_hosts=frozenset({"localhost", "127.0.0.1", "::1", PUBLIC_HOST}),
    proxied=True,
)
"""
The policy of a viewer behind a password-checking proxy on this machine.
"""

KEY = "s3cret-Key_1"
"""
The key of a viewer that other devices of the network may watch.
"""


def ok(request: Request) -> Response:
    return Response.of_text("ok")


ROUTER = Router(
    [
        ExactRoute(HttpMethod.GET, "/read", ok),
        ExactRoute(HttpMethod.GET, "/private", ok, local_only=True),
        ExactRoute(HttpMethod.POST, "/change", ok),
        ExactRoute(HttpMethod.POST, "/control", ok, remote_changes=True),
    ]
)
"""
A router with a plain read, a read for this machine only, a change for this machine only
and a change other devices may make.
"""


def proxied(method=HttpMethod.GET, path="/read", **headers) -> Request:
    """
    :return: A request the proxy forwards from a phone on the internet: it arrives from
        and at this machine's loopback address.
    """
    return Request(
        method=method,
        path=path,
        headers={
            Header.HOST: PUBLIC_HOST,
            Header.ORIGIN: f"https://{PUBLIC_HOST}",
            **headers,
        },
    )


def from_phone(method=HttpMethod.GET, path="/read") -> Request:
    """
    :return: A request a phone of the network sends with the key in its cookie.
    """
    return Request(
        method=method,
        path=path,
        headers={Header.HOST: "192.0.2.7:8711", Header.COOKIE: f"{KEY_COOKIE}={KEY}"},
        server_address="192.0.2.7",
        client_address="192.0.2.50",
    )


def answer(policy: OriginPolicy, request: Request) -> Response:
    return RequestAnswerer(router=ROUTER, policy=policy).answer(request)


# %% route flags


def test_routes_are_for_everyone_and_change_nothing_remotely_by_default():
    route = ExactRoute(HttpMethod.GET, "/a", ok)
    assert not route.local_only and not route.remote_changes


def test_plugin_routes_carry_their_flags_to_the_router():
    exact = PluginRoute(
        HttpMethod.POST, path="start", handler=ok, remote_changes=True
    ).route("/api/plugins/runs/")
    prefix = PluginPrefixRoute(
        HttpMethod.GET, prefix="files/", handler=lambda r, p: ok(r), local_only=True
    ).route("/api/plugins/runs/")
    assert exact.remote_changes and not exact.local_only
    assert isinstance(prefix, PrefixRoute) and prefix.local_only


# %% behind a proxy


def test_every_request_through_the_proxy_counts_as_another_device_s():
    assert not PROXY_POLICY.is_from_this_machine(proxied())
    assert PROXY_POLICY.is_admitted(proxied())


def test_the_proxy_s_pages_read_without_a_key():
    response = answer(PROXY_POLICY, proxied())
    assert response.status is HTTPStatus.OK
    assert response.headers[Header.ALLOW_ORIGIN] == f"https://{PUBLIC_HOST}"
    assert Header.SET_COOKIE not in response.headers


def test_the_proxy_s_pages_make_the_changes_other_devices_may_make():
    assert answer(PROXY_POLICY, proxied(HttpMethod.POST, "/control")).body == b"ok"


@pytest.mark.parametrize(
    "method, path",
    [(HttpMethod.POST, "/change"), (HttpMethod.POST, "/unknown")],
)
def test_the_proxy_s_pages_make_no_other_change(method, path):
    response = answer(PROXY_POLICY, proxied(method, path))
    assert response.status is HTTPStatus.FORBIDDEN
    assert "Over the network" in json.loads(response.body)[ErrorKey.ERROR]


def test_the_proxy_s_pages_do_not_read_what_is_for_this_machine_only():
    response = answer(PROXY_POLICY, proxied(path="/private"))
    assert response.status is HTTPStatus.FORBIDDEN


@pytest.mark.parametrize(
    "headers",
    [
        {Header.HOST: "evil.example"},
        {Header.ORIGIN: "https://evil.example"},
    ],
)
def test_other_host_names_stay_refused_behind_the_proxy(headers):
    response = answer(PROXY_POLICY, proxied(**headers))
    assert response.status is HTTPStatus.FORBIDDEN


# %% on the network


def test_a_phone_of_the_network_only_watches_even_where_other_devices_may_change():
    response = answer(OriginPolicy(key=KEY), from_phone(HttpMethod.POST, "/control"))
    assert response.status is HTTPStatus.FORBIDDEN
    assert "only watch" in json.loads(response.body)[ErrorKey.ERROR]


def test_a_phone_of_the_network_does_not_read_what_is_for_this_machine_only():
    response = answer(OriginPolicy(key=KEY), from_phone(path="/private"))
    assert response.status is HTTPStatus.FORBIDDEN


def test_this_machine_reads_and_changes_everything():
    local = {Header.HOST: "127.0.0.1:8711"}
    for method, path in [(HttpMethod.GET, "/private"), (HttpMethod.POST, "/change")]:
        request = Request(method=method, path=path, headers=local)
        assert answer(OriginPolicy(), request).body == b"ok"
