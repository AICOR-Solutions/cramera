"""
Routing, the origin policy and the server.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from http import HTTPStatus

import pytest

from cramera.exceptions import UnknownScene
from cramera.http.messages import (
    Header,
    HttpMethod,
    MediaType,
    Request,
    Response,
)
from cramera.http.origin import OriginPolicy
from cramera.http.routing import ExactRoute, PrefixRoute, Router
from cramera.http.server import HttpServer, RequestAnswerer
from cramera_protocol.exceptions import MissingDocumentField
from cramera_protocol.viewer import ErrorKey, ViewerRoute

LOCAL_HOST = {Header.HOST: "127.0.0.1:8711"}
"""
The headers of a request addressed to this machine.
"""


def request(method=HttpMethod.GET, path="/", **headers) -> Request:
    return Request(method=method, path=path, headers={**LOCAL_HOST, **headers})


# %% router


def test_the_router_answers_with_the_first_matching_route():
    router = Router()
    router.add(ExactRoute(HttpMethod.GET, "/a", lambda _: Response.of_text("exact")))
    router.add(PrefixRoute(HttpMethod.GET, "/", lambda _, rest: Response.of_text(rest)))
    assert router.answer(request(path="/a")).body == b"exact"
    assert router.answer(request(path="/b/c")).body == b"b/c"


def test_a_head_request_is_answered_by_the_get_route():
    router = Router([ExactRoute(HttpMethod.GET, "/a", lambda _: Response.of_text("x"))])
    assert router.answer(request(HttpMethod.HEAD, "/a")).status is HTTPStatus.OK


def test_an_unknown_path_is_not_found_and_a_wrong_method_not_allowed():
    router = Router([ExactRoute(HttpMethod.GET, "/a", lambda _: Response.of_text("x"))])
    assert router.answer(request(path="/b")).status is HTTPStatus.NOT_FOUND
    assert (
        router.answer(request(HttpMethod.POST, "/a")).status
        is HTTPStatus.METHOD_NOT_ALLOWED
    )


# %% messages


def test_a_request_reads_headers_without_regard_to_case_and_parses_its_query():
    incoming = Request(
        method=HttpMethod.GET,
        path="/",
        query="scene=cell&scene=two",
        headers={"oRiGiN": "x"},
    )
    assert incoming.header(Header.ORIGIN) == "x"
    assert incoming.header(Header.HOST) is None
    assert incoming.parameters() == {"scene": ["cell", "two"]}


def test_a_json_response_serializes_protocol_values():
    response = Response.of_json({"a": 1})
    assert json.loads(response.body) == {"a": 1}
    assert response.media_type is MediaType.JSON


def test_media_types_follow_file_suffixes(tmp_path):
    assert MediaType.of_path(tmp_path / "m.GLB") is MediaType.GLB
    assert MediaType.of_path(tmp_path / "robot.urdf") is MediaType.XML
    assert MediaType.of_path(tmp_path / "data.unknown") is MediaType.BINARY


# %% origin policy


@pytest.mark.parametrize(
    "origin", ["http://localhost:8711", "https://127.0.0.1", "http://[::1]:9"]
)
def test_local_origins_are_answered_and_named_in_the_answer(origin):
    policy = OriginPolicy()
    incoming = request(**{Header.ORIGIN: origin})
    assert policy.refusal(incoming) is None
    answered = policy.addressed(incoming, Response())
    assert answered.headers[Header.ALLOW_ORIGIN] == origin


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example",
        "http://localhost.evil.example",
        "file://",
        "null",
        "ftp://localhost",
    ],
)
def test_other_origins_are_refused(origin):
    refusal = OriginPolicy().refusal(request(**{Header.ORIGIN: origin}))
    assert refusal.status is HTTPStatus.FORBIDDEN


@pytest.mark.parametrize("headers", [{Header.HOST: "evil.example:8711"}, {}])
def test_requests_addressed_to_other_hosts_are_refused(headers):
    incoming = Request(method=HttpMethod.GET, path="/", headers=headers)
    assert OriginPolicy().refusal(incoming).status is HTTPStatus.FORBIDDEN


def test_a_preflight_allows_the_viewer_methods():
    answer = OriginPolicy().preflight(
        request(HttpMethod.OPTIONS, **{Header.ORIGIN: "http://localhost"})
    )
    assert answer.status is HTTPStatus.NO_CONTENT
    assert HttpMethod.POST.value in answer.headers[Header.ALLOW_METHODS]


# %% answerer


def test_viewer_and_protocol_errors_become_error_answers():
    def unknown(_):
        raise UnknownScene("x")

    def malformed(_):
        raise MissingDocumentField("Scene", "name")

    router = Router(
        [
            ExactRoute(HttpMethod.GET, "/u", unknown),
            ExactRoute(HttpMethod.GET, "/m", malformed),
        ]
    )
    answerer = RequestAnswerer(router=router, policy=OriginPolicy())
    unknown_answer = answerer.answer(request(path="/u"))
    assert unknown_answer.status is HTTPStatus.NOT_FOUND
    assert (
        json.loads(unknown_answer.body)[ErrorKey.ERROR] == UnknownScene("x").message()
    )
    assert answerer.answer(request(path="/m")).status is HTTPStatus.BAD_REQUEST


def test_the_answerer_refuses_before_routing():
    answerer = RequestAnswerer(router=Router(), policy=OriginPolicy())
    assert (
        answerer.answer(request(**{Header.ORIGIN: "https://evil.example"})).status
        is HTTPStatus.FORBIDDEN
    )
    preflight = request(HttpMethod.OPTIONS, **{Header.ORIGIN: "http://localhost"})
    assert answerer.answer(preflight).status is HTTPStatus.NO_CONTENT


# %% server


def test_the_server_answers_over_a_socket_and_stops(answerer):
    with HttpServer(answerer=answerer) as server:
        with urllib.request.urlopen(server.url() + ViewerRoute.INFO) as answer:
            assert answer.status == HTTPStatus.OK
        head = urllib.request.Request(
            server.url() + ViewerRoute.INFO, method=HttpMethod.HEAD
        )
        with urllib.request.urlopen(head) as answer:
            assert answer.read() == b""
        posted = urllib.request.Request(
            server.url() + ViewerRoute.SCENES, method=HttpMethod.POST, data=b"{}"
        )
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(posted)
        assert refused.value.code == HTTPStatus.METHOD_NOT_ALLOWED
    assert server.server is None
    server.stop()


def test_the_server_decodes_percent_encoded_paths(answerer):
    with HttpServer(answerer=answerer) as server:
        url = server.url() + ViewerRoute.SCENE_FILES + "cell/meshes/arm%20base.stl"
        with urllib.request.urlopen(url) as answer:
            assert answer.read().startswith(b"solid")
        escaping = (
            server.url()
            + ViewerRoute.SCENE_FILES
            + "cell/..%2F..%2Fshared_scenes%2Fcell%2Fscene.json"
        )
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(escaping)
        assert refused.value.code == HTTPStatus.FORBIDDEN


def test_the_url_brackets_an_ipv6_host(answerer):
    server = HttpServer(answerer=answerer, host="::1")
    with server:
        assert server.url().startswith("http://[::1]:")
