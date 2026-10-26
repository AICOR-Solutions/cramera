"""
Evaluations standing in for where a query is answered.
"""

from __future__ import annotations

from dataclasses import dataclass

from krrood.entity_query_language.evaluable import Evaluable
from typing_extensions import Any

from cramera_bridge.questions.knowledge import TranslatedEvaluation
from cramera_protocol.questions import QueryTranslation

# %% translating evaluations


@dataclass(frozen=True)
class RecitedEvaluation(TranslatedEvaluation):
    """
    Answers a query in memory and recites a fixed statement as the one it was answered
    by, as an evaluation running its queries on a database does with its SQL.
    """

    translation: QueryTranslation
    """
    The statement every query is answered by.
    """

    def evaluate(self, expression: Evaluable) -> Any:
        return expression.evaluate()

    def translate(self, expression: Evaluable) -> QueryTranslation:
        return self.translation
