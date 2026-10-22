"""
Protocol versions and which documents a reader accepts.
"""

from __future__ import annotations

import pytest

from cramera_protocol.exceptions import (
    MalformedProtocolVersion,
    UnsupportedProtocolVersion,
)
from cramera_protocol.version import CURRENT_VERSION, UNVERSIONED, ProtocolVersion


def test_a_version_round_trips():
    version = ProtocolVersion.from_json("1.12")
    assert version == ProtocolVersion(major=1, minor=12)
    assert version.to_json() == "1.12"


@pytest.mark.parametrize("text", ["1", "1.0.0", "one", "", "-1.0"])
def test_text_that_is_not_a_version_is_refused(text):
    with pytest.raises(MalformedProtocolVersion):
        ProtocolVersion.from_json(text)


def test_a_version_that_is_not_text_is_refused():
    with pytest.raises(MalformedProtocolVersion):
        ProtocolVersion.from_json(1.0)


def test_a_reader_accepts_its_own_major_version_and_unversioned_documents():
    later_minor = ProtocolVersion(
        major=CURRENT_VERSION.major, minor=CURRENT_VERSION.minor + 1
    )
    later_minor.require_readable_by(CURRENT_VERSION)
    UNVERSIONED.require_readable_by(CURRENT_VERSION)


def test_a_reader_refuses_another_major_version():
    next_major = ProtocolVersion(major=CURRENT_VERSION.major + 1, minor=0)
    with pytest.raises(UnsupportedProtocolVersion) as raised:
        next_major.require_readable_by(CURRENT_VERSION)
    assert raised.value.found == next_major.to_json()
    assert raised.value.supported == CURRENT_VERSION.to_json()
