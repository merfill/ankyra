"""Phase 0 public API: structure -> Theory / Query."""

from __future__ import annotations

from ankyra.build.enrich import enrich_theory
from ankyra.build.query import settle_query
from ankyra.build.unroll import unroll_problem_structure, unroll_query_structure
from ankyra.core.models import Query, Theory
from ankyra.core.schemas import ProblemStructure, QuestionStructure


def build_theory(structure: ProblemStructure, *, deontic_prefixes: bool = False) -> Theory:
    """Unroll then enrich a problem structure into a well-formed theory."""
    return enrich_theory(
        unroll_problem_structure(structure, deontic_prefixes=deontic_prefixes)
    )


def build_query(
    structure: QuestionStructure,
    *,
    deontic_prefixes: bool = False,
) -> Query:
    """Unroll then settle a question structure."""
    return settle_query(
        unroll_query_structure(structure, deontic_prefixes=deontic_prefixes)
    )
