"""Phase 0 public API: structure -> Theory / Query."""

from __future__ import annotations

from ankyra.build.enrich import enrich_theory
from ankyra.build.query import settle_query, strip_domain_conditions
from ankyra.build.symbolic import enforce_grounded
from ankyra.build.unroll import unroll_problem_structure, unroll_query_structure
from ankyra.core.models import Query, Theory, WorldAssumption


def default_world_assumption() -> WorldAssumption:
    """The config-level default world assumption (``ANKYRA_NEGATION_MODE``)."""
    from ankyra.config.settings import settings

    value = str(settings.get("NEGATION_MODE", "open") or "open").strip().lower()
    return "closed" if value == "closed" else "open"
from ankyra.core.schemas import ProblemStructure, QuestionStructure


def build_theory(
    structure: ProblemStructure,
    *,
    deontic_prefixes: bool = False,
    enforce_grounding: bool = True,
) -> Theory:
    """Unroll then enrich a problem structure into a well-formed theory.

    ``enforce_grounding`` drops atoms/rules without a valid source quote; scoring
    an extraction candidate passes ``False`` so the gaps stay visible to the
    ranker and the repair loop.
    """
    theory = enrich_theory(unroll_problem_structure(structure, deontic_prefixes=deontic_prefixes))
    if enforce_grounding:
        theory = enforce_grounded(theory)
    return theory


def build_query(
    structure: QuestionStructure,
    *,
    deontic_prefixes: bool = False,
    domain: list[str] | None = None,
    world_assumption: WorldAssumption | None = None,
) -> Query:
    """Unroll, settle, and drop vacuous domain premises from a question structure.

    ``world_assumption`` defaults to the config value when omitted; it is never
    taken from the LLM-authored structure (``docs/l1_plan.md`` D-L1-4).
    """
    query = settle_query(
        unroll_query_structure(
            structure,
            deontic_prefixes=deontic_prefixes,
            world_assumption=world_assumption or default_world_assumption(),
        )
    )
    return strip_domain_conditions(query, domain)
