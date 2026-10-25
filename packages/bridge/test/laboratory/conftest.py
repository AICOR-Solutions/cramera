"""
The laboratory asset bundle used by the bridge's native integration tests.
"""

from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def laboratory_bundle() -> Path:
    """
    :return: The small laboratory bundle, independent of installing its plugin.
    """
    return (
        Path(__file__).resolve().parents[3]
        / "plugins/laboratory/src/cramera_laboratory/resources/aicor_medical_lab"
    )
