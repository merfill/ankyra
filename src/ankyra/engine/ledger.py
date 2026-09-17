"""Hypothesis ledger and proof-based accounting of the hypotheses actually used."""

from __future__ import annotations

from dataclasses import dataclass, field

from ankyra.core.models import FactKey, Hypothesis, Morphism, Rule
from ankyra.engine.horn import AtomStore


def morphism_key(morphism: Morphism) -> FactKey:
    return (
        morphism.predicate,
        morphism.subject or "",
        morphism.object or "",
        morphism.negated,
        morphism.modality,
    )


@dataclass
class HypothesisLedger:
    """Every tagged assumption, plus the provenance needed to attribute proofs."""

    hypotheses: list[Hypothesis] = field(default_factory=list)
    rule_sources: dict[int, str] = field(default_factory=dict)
    fact_keys: dict[FactKey, str] = field(default_factory=dict)

    def next_id(self) -> str:
        return f"H{len(self.hypotheses) + 1}"

    def add_rule(
        self,
        hypothesis_id: str,
        rule: Rule,
        *,
        rule_index: int,
        rationale: str,
        wave: int,
    ) -> Hypothesis:
        hypothesis = Hypothesis(
            id=hypothesis_id, kind="rule", payload=rule, wave=wave, rationale=rationale
        )
        self.hypotheses.append(hypothesis)
        self.rule_sources[rule_index] = hypothesis_id
        return hypothesis

    def add_fact(
        self,
        hypothesis_id: str,
        morphism: Morphism,
        *,
        key: FactKey,
        rationale: str,
        wave: int,
    ) -> Hypothesis:
        hypothesis = Hypothesis(
            id=hypothesis_id, kind="fact", payload=morphism, wave=wave, rationale=rationale
        )
        self.hypotheses.append(hypothesis)
        self.fact_keys[key] = hypothesis_id
        return hypothesis

    def used(self, store: AtomStore, proof_keys: frozenset[FactKey]) -> list[str]:
        """Ids of hypotheses that appear in a proof, in ledger order."""
        attributed: set[str] = set()
        for key in proof_keys:
            hypothesis_id = self.fact_keys.get(key)
            if hypothesis_id is not None:
                attributed.add(hypothesis_id)
            fact = store.by_key.get(key)
            if fact is not None and fact.rule_index in self.rule_sources:
                attributed.add(self.rule_sources[fact.rule_index])
        return [hypothesis.id for hypothesis in self.hypotheses if hypothesis.id in attributed]
