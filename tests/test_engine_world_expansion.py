"""World expansion over waves: each wave adds a statement with a distinct origin.

Deterministic illustration of ``docs/statement_sources.md`` — the base only grows,
and every added statement carries where it came from (a text quote / a tagged
hypothesis), which the explanation reports. Proposals are scripted, so no LLM.
"""

from __future__ import annotations

from ankyra.core.models import Morphism, Object, Query, Rule, Theory
from ankyra.engine.cycle import run_cycle
from ankyra.engine.proposal import ProposalDraft


def test_a_wave_adds_a_cited_fact_from_the_text():
    theory = Theory(
        objects=[Object(id="ground")],
        rules=[
            Rule(
                conditions=[Morphism(predicate="raining")],
                consequence=Morphism(predicate="is_wet", object="ground"),
            )
        ],
        source_text="The ground is wet. It is raining.",
    )
    query = Query(target=Morphism(predicate="is_wet", object="ground"))

    def cite(_ctx):
        return ProposalDraft(
            action="assert_cited_fact",
            fact=Morphism(predicate="raining", quote="It is raining"),
        )

    result = run_cycle(cite, theory, query, max_waves=2)

    assert result.status == "supported"
    assert result.answer.strength == "proven"
    assert result.answer.hypotheses_used == []

    # The world grew: the wave-0 fact is now an axiom of the theory, not invented.
    assert any(m.predicate == "raining" for m in result.theory.morphisms)
    assert result.hypotheses == []
    assert [record.category for record in result.history] == ["cited"]

    # Provenance: the step is grounded in the text, not assumed.
    fact_step = next(s for s in result.explanation.steps if s.statement == "raining()")
    assert fact_step.kind == "axiom"
    assert fact_step.source == "quote"
    assert fact_step.quote == "It is raining"


def test_a_wave_adds_a_hypothesis_fact_and_it_is_tagged():
    theory = Theory(
        objects=[Object(id="gary")],
        morphisms=[Morphism(predicate="is_a", subject="gary", object="smart")],
        rules=[
            Rule(
                conditions=[
                    Morphism(predicate="is_a", subject="?x", object="rough"),
                    Morphism(predicate="is_a", subject="?x", object="smart"),
                ],
                consequence=Morphism(predicate="is_a", subject="?x", object="furry"),
            )
        ],
    )
    query = Query(target=Morphism(predicate="is_a", subject="gary", object="furry"))

    def hypothesize(_ctx):
        return ProposalDraft(
            action="assert_cited_fact",
            fact=Morphism(predicate="is_a", subject="gary", object="rough"),
        )

    result = run_cycle(hypothesize, theory, query, max_waves=2)

    assert result.status == "supported"
    assert result.answer.strength == "proven_under"
    assert result.answer.hypotheses_used == ["H1"]

    # The invented fact is ledgered and attributed to the wave that added it.
    assert [hypothesis.id for hypothesis in result.hypotheses] == ["H1"]
    assert result.hypotheses[0].wave == 0
    assert [record.category for record in result.history] == ["hypothesis"]

    fact_step = next(
        s for s in result.explanation.steps if s.statement == "is_a(gary,rough)"
    )
    assert fact_step.kind == "hypothesis"
    assert fact_step.source == "hypothesis:H1"


def test_two_waves_expand_the_world_with_distinct_origins():
    theory = Theory(
        objects=[Object(id="a")],
        rules=[
            Rule(
                conditions=[
                    Morphism(predicate="p", subject="?x"),
                    Morphism(predicate="q", subject="?x"),
                ],
                consequence=Morphism(predicate="r", subject="?x"),
            )
        ],
        source_text="a is p.",
    )
    query = Query(target=Morphism(predicate="r", subject="a"))

    proposals = iter(
        [
            # Wave 0: a fact grounded in the text.
            ProposalDraft(
                action="assert_cited_fact",
                fact=Morphism(predicate="p", subject="a", quote="a is p"),
            ),
            # Wave 1: a fact with no quote — the engine must tag it.
            ProposalDraft(
                action="assert_cited_fact",
                fact=Morphism(predicate="q", subject="a"),
            ),
        ]
    )
    result = run_cycle(lambda _ctx: next(proposals), theory, query, max_waves=5)

    assert result.status == "supported"
    assert result.answer.strength == "proven_under"
    assert result.answer.hypotheses_used == ["H1"]
    assert [record.category for record in result.history] == ["cited", "hypothesis"]

    # Each wave's contribution is identifiable in the history payload.
    assert result.history[0].proposal.payload["fact"]["predicate"] == "p"
    assert result.history[1].proposal.payload["fact"]["predicate"] == "q"

    # The base grew monotonically: a cited axiom plus one ledgered hypothesis.
    assert any(m.predicate == "p" for m in result.theory.morphisms)
    assert [hypothesis.id for hypothesis in result.hypotheses] == ["H1"]

    # One trace, two origins: the answer rests on the hypothesis, not the text alone.
    by_statement = {step.statement: step for step in result.explanation.steps}
    assert by_statement["p(a)"].source == "quote"
    assert by_statement["q(a)"].source == "hypothesis:H1"

    # The answer moved once, triggered by the hypothesis.
    assert len(result.revisions) == 1
    assert result.revisions[0].trigger == "new_hypothesis"
    assert result.revisions[0].current.strength == "proven_under"
