"""
The local robot preview boundary and the live routes visible through the viewer.
"""

import json
import threading
from http.client import RemoteDisconnected
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.error import URLError

import pytest

from cramera_laboratory.exceptions import RobotDemoUnavailable, UnknownLiveRead
from cramera_laboratory.robot_view import RobotLaboratoryView
from cramera_protocol.live_messages import SavedScene


@pytest.fixture
def live_publisher():
    paths = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            paths.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"sequenceNumber": 3, "joints": {"elbow": 1.2}}).encode()
            )

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/", paths
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def test_live_observations_are_read_from_the_owned_publishers_root(
    shelf, live_publisher
):
    address, paths = live_publisher
    view = RobotLaboratoryView(SimpleNamespace(live_address=lambda: address), shelf)
    response = view.live_read("state")
    assert json.loads(response.body)["joints"] == {"elbow": 1.2}
    assert paths == ["/state"]


@pytest.mark.parametrize(
    "path", ["../state", "http://example.org", "recording/save", "", "state?url=x"]
)
def test_the_live_proxy_does_not_forward_other_paths(shelf, live_publisher, path):
    address, paths = live_publisher
    view = RobotLaboratoryView(SimpleNamespace(live_address=lambda: address), shelf)
    with pytest.raises(UnknownLiveRead):
        view.live_read(path)
    assert paths == []


def test_no_live_request_is_made_without_an_owned_running_publisher(shelf):
    view = RobotLaboratoryView(SimpleNamespace(live_address=lambda: None), shelf)
    with pytest.raises(RobotDemoUnavailable):
        view.live_read("info")


@pytest.mark.parametrize(
    "problem",
    [
        URLError("Connection refused"),
        RemoteDisconnected("Publisher stopped"),
        ConnectionResetError("Publisher reset"),
    ],
)
def test_a_stopped_publisher_is_reported_as_unavailable(shelf, monkeypatch, problem):
    def unavailable(*args, **kwargs):
        raise problem

    monkeypatch.setattr("cramera_laboratory.robot_view.urlopen", unavailable)
    view = RobotLaboratoryView(
        SimpleNamespace(live_address=lambda: "http://127.0.0.1:1234/"), shelf
    )
    with pytest.raises(RobotDemoUnavailable, match="unavailable"):
        view.live_read("info")


def test_preview_crosses_the_bridge_as_paths_and_a_protocol_result(
    shelf, locations, monkeypatch
):
    from cramera_bridge.laboratory import command

    arguments = []

    def prepare(bundle, scenes):
        arguments.append((bundle, scenes))
        return SavedScene(scene="aicor_medical_lab_pr2")

    monkeypatch.setattr(command, "prepare_preview", prepare)
    task = SimpleNamespace(available=lambda: True, locations=locations)
    view = RobotLaboratoryView(task, shelf)
    assert view.preview().scene == "aicor_medical_lab_pr2"
    assert arguments == [
        (str(shelf.laboratories()[0].directory), str(locations.local_scenes))
    ]


def test_an_older_bridge_explains_how_to_add_the_preview(shelf, locations, monkeypatch):
    from cramera_bridge.laboratory import command

    monkeypatch.delattr(command, "prepare_preview")
    task = SimpleNamespace(available=lambda: True, locations=locations)
    with pytest.raises(RobotDemoUnavailable, match="CRAM"):
        RobotLaboratoryView(task, shelf).preview()


@pytest.mark.parametrize(
    "problem", [ImportError("Missing ROS module"), OSError("Missing robot assets")]
)
def test_incomplete_native_setup_explains_the_preview_failure(
    shelf, locations, monkeypatch, problem
):
    from cramera_bridge.laboratory import command

    def unavailable(*args):
        raise problem

    monkeypatch.setattr(command, "prepare_preview", unavailable)
    task = SimpleNamespace(available=lambda: True, locations=locations)
    with pytest.raises(RobotDemoUnavailable, match="source ROS") as failure:
        RobotLaboratoryView(task, shelf).preview()
    assert failure.value.status() == 503
    assert str(problem) in failure.value.message()


def test_an_unexpected_preview_bug_is_not_relabelled_as_missing_setup(
    shelf, locations, monkeypatch
):
    from cramera_bridge.laboratory import command

    def broken(*args):
        raise ValueError("Unexpected model data")

    monkeypatch.setattr(command, "prepare_preview", broken)
    task = SimpleNamespace(available=lambda: True, locations=locations)
    with pytest.raises(ValueError, match="Unexpected model data"):
        RobotLaboratoryView(task, shelf).preview()
