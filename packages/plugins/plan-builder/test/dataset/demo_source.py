"""
Reading the demo document back out of a rendered demo, without running it.
"""

from __future__ import annotations

import ast
import json

from cramera_protocol.plan_builder import DemoDocument

DEMO_CONSTANT = "DEMO"
"""
The name of the template's constant holding the demo document.
"""


def demo_document(source: str) -> DemoDocument:
    """
    :param source: A rendered demo.
    :return: The document its constant holds.
    :raises AssertionError: When the demo assigns no such constant.
    """
    for statement in ast.parse(source).body:
        if (
            isinstance(statement, ast.Assign)
            and statement.targets[0].id == DEMO_CONSTANT
        ):
            return DemoDocument.from_json(json.loads(statement.value.value))
    raise AssertionError(f"The demo assigns no {DEMO_CONSTANT}.")
