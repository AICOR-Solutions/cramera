"""
Shared fixtures of the protocol tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typing_extensions import Any, Callable

DATASET = Path(__file__).parent / "dataset"
"""
The directory holding the test documents.
"""


@pytest.fixture
def dataset() -> Path:
    """
    :return: The directory holding the test documents.
    """
    return DATASET


@pytest.fixture
def read_json(dataset: Path) -> Callable[[str], Any]:
    """
    :return: A function decoding a JSON file of the dataset by its relative path.
    """

    def read(relative_path: str) -> Any:
        return json.loads((dataset / relative_path).read_text(encoding="utf-8"))

    return read
