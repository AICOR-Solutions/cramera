"""
The logo the top bar shows: the AICOR logo, or one the viewer or the exported site was
given.
"""

from __future__ import annotations

import json
from http import HTTPStatus

import pytest

from cramera.application import ViewerApplication
from cramera.branding import DEFAULT_LOGO, Branding
from cramera.command_line import Option, ViewerConfiguration
from cramera.exceptions import LogoNotFound, UnsupportedLogo
from cramera.http.messages import Header, HttpMethod, MediaType, Request
from cramera.http.origin import OriginPolicy
from cramera.http.server import RequestAnswerer
from cramera_protocol.viewer import EnvironmentVariable, ViewerInfo, ViewerRoute

HEADERS = {Header.HOST: "localhost"}
"""
The headers of a request addressed to this machine.
"""

LOGO_BYTES = b"<svg xmlns='http://www.w3.org/2000/svg'/>"
"""
The content of the test logo.
"""


@pytest.fixture
def logo(tmp_path):
    """
    :return: A logo of another lab.
    """
    path = tmp_path / "lab-logo.svg"
    path.write_bytes(LOGO_BYTES)
    return path


def served(catalog, locations, branding, path):
    """
    :return: The viewer's answer to a request for a path.
    """
    application = ViewerApplication(
        catalog=catalog, locations=locations, branding=branding
    )
    answerer = RequestAnswerer(router=application.router(), policy=OriginPolicy())
    return answerer.answer(Request(method=HttpMethod.GET, path=path, headers=HEADERS))


# %% branding


def test_without_a_logo_the_aicor_logo_is_shown_and_its_text_left_to_the_page():
    branding = Branding()
    assert branding.file() == DEFAULT_LOGO and DEFAULT_LOGO.is_file()
    assert branding.text() is None


def test_a_given_logo_is_shown_with_its_text_or_its_name(logo):
    assert Branding(logo=logo).file() == logo
    assert Branding(logo=logo).text() == "lab-logo"
    assert Branding(logo=logo, logo_text="Our lab").text() == "Our lab"


def test_the_environment_names_a_logo_the_command_line_does_not(logo, tmp_path):
    other = tmp_path / "other.png"
    other.write_bytes(b"png")
    environment = {EnvironmentVariable.LOGO.value: str(logo)}
    assert Branding.of(None, None, environment).logo == logo
    assert Branding.of(other, None, environment).logo == other
    assert Branding.of(None, None, {}).logo is None


def test_a_logo_that_cannot_be_shown_is_refused(tmp_path):
    with pytest.raises(LogoNotFound):
        Branding.of(tmp_path / "missing.png", None, {})
    text = tmp_path / "logo.txt"
    text.write_text("not an image")
    with pytest.raises(UnsupportedLogo):
        Branding.of(text, None, {})


# %% viewer


def test_the_logo_route_serves_the_aicor_logo_by_default(catalog, locations):
    response = served(catalog, locations, Branding(), ViewerRoute.LOGO)
    assert response.status is HTTPStatus.OK
    assert response.body == DEFAULT_LOGO.read_bytes()


def test_the_logo_route_and_the_information_follow_a_given_logo(
    catalog, locations, logo
):
    branding = Branding(logo=logo, logo_text="Our lab")
    response = served(catalog, locations, branding, ViewerRoute.LOGO)
    assert response.body == LOGO_BYTES
    assert response.media_type is MediaType.SVG
    info = served(catalog, locations, branding, ViewerRoute.INFO)
    assert ViewerInfo.from_json(json.loads(info.body)).logo_text == "Our lab"


def test_the_command_takes_a_logo_and_its_text(locations, logo):
    configuration = ViewerConfiguration.from_arguments(
        [Option.LOGO, str(logo), Option.LOGO_TEXT, "Our lab"], locations
    )
    assert configuration.branding == Branding(logo=logo, logo_text="Our lab")


def test_the_command_refuses_a_missing_logo(locations, tmp_path, capsys):
    with pytest.raises(SystemExit):
        ViewerConfiguration.from_arguments(
            [Option.LOGO, str(tmp_path / "missing.png")], locations
        )
    assert "does not exist" in capsys.readouterr().err
