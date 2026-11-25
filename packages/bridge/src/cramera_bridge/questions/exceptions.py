"""
Errors the question engine raises.

Errors a request can cause derive from :class:`~cramera.exceptions.ViewerError`, so the
HTTP boundary answers them with their own status.
"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus

from typing_extensions import List, Optional

from cramera.exceptions import ViewerError

# %% base


@dataclass
class QuestionError(ViewerError):
    """
    A question that cannot be asked or answered.
    """


# %% queries


@dataclass
class EmptyQuery(QuestionError):
    """
    A query whose source holds no statement.
    """

    def message(self) -> str:
        return "The query is empty."


@dataclass
class UnknownScope(QuestionError):
    """
    A body of knowledge that is not on offer.
    """

    scope: str
    """
    The scope that was asked.
    """

    offered: List[str]
    """
    The scopes on offer.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return f"No knowledge of the scope {self.scope!r} is offered; ask one of {self.offered}."


@dataclass
class UnknownVocabularyName(QuestionError):
    """
    A name whose members were asked for although no type of that name is in reach.
    """

    name: str
    """
    The name that was asked for.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return f"No type named {self.name!r} is in reach of a query."


# %% graph views


@dataclass
class UnknownGraphView(QuestionError):
    """
    A graph view no builder knows.
    """

    view: str
    """
    The view that was asked for.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return f"There is no graph view named {self.view!r}."


# %% graphs


@dataclass
class DuplicateGraphNode(QuestionError):
    """
    A graph view that would hold two nodes of the same identity.
    """

    identifier: str
    """
    The identity both nodes carry.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.INTERNAL_SERVER_ERROR

    def message(self) -> str:
        return f"The graph already holds a node {self.identifier!r}."


@dataclass
class DomainNeverHoldsClass(QuestionError):
    """
    A query asking for a class among a domain whose type it never is, which answers
    nothing however the world stands.
    """

    asked: str
    """
    The class the query asks for.
    """

    held: str
    """
    The type the domain holds.
    """

    hint: Optional[str] = None
    """
    Where the class can be asked instead, or None when the scope names nowhere.
    """

    def message(self) -> str:
        message = (
            f"A {self.asked} is never a {self.held}, and the domain it is asked "
            f"among holds only objects of type {self.held}, so the query cannot answer."
        )
        return message if self.hint is None else f"{message} {self.hint}"
