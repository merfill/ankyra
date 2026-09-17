"""Tests for the Phase 0 LLM extraction (live tests are opt-in)."""

from __future__ import annotations

import os

import pytest

from ankyra.build.extract import (
    extract_problem_structure,
    extract_question_structure,
    format_theory_for_llm,
)
from ankyra.core.models import Morphism, Object, Rule, Theory

live = pytest.mark.skipif(
    not os.getenv("ANKYRA_LIVE"),
    reason="set ANKYRA_LIVE=1 to call the LLM",
)


def test_format_theory_for_llm_lists_vocabulary_and_rules():
    theory = Theory(
        objects=[Object(id="ground")],
        morphisms=[Morphism(predicate="raining", quote="raining")],
        rules=[
            Rule(
                conditions=[Morphism(predicate="raining")],
                consequence=Morphism(predicate="is_wet", object="ground"),
            )
        ],
    )
    text = format_theory_for_llm(theory)
    assert "raining" in text
    assert "is_wet" in text
    assert "R1: IF raining" in text


@pytest.mark.live
@live
def test_live_problem_and_question_extraction():
    from ankyra.build.pipeline import build_query, build_theory
    from ankyra.engine.verify import verify
    from ankyra.llm.client import create_chat_llm

    problem = "It is raining. If it is raining, the ground is wet. Is the ground wet?"
    llm = create_chat_llm(role="extract")
    structure = extract_problem_structure(llm, text=problem)
    assert structure.question.strip()

    theory = build_theory(structure)
    question = extract_question_structure(
        llm, question=structure.question, theory=theory, source_text=problem
    )
    query = build_query(theory, question)
    verdict = verify(theory, query)
    assert verdict.status in {"supported", "insufficient", "unsupported", "refuted"}
