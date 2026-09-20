"""Mechanical explanation: walk the provenance of the winning proof.

The trace is built only from real derivation edges (``premises`` / ``rule_index``)
and identified hypotheses; the LLM never authors it. Steps are ordered from
premises to the goal by a post-order DFS, so every premise index is smaller than
the step that uses it.
"""

from __future__ import annotations

from ankyra.core.models import (
    Conflict,
    Explanation,
    ExplanationKind,
    ExplanationStep,
    Fact,
    FactKey,
    Query,
    Theory,
    Verdict,
)
from ankyra.engine.clause import label_of
from ankyra.engine.horn import build_context
from ankyra.engine.ledger import HypothesisLedger, morphism_key
from ankyra.engine.verify import (
    _key_matches,
    l2_outcomes,
    logic_enabled,
    winning_store_hit,
)


def render_atom(morphism) -> str:
    """Readable atom, including modality and negation: ``obligation:pay(alice)``."""
    neg = "NOT " if morphism.negated else ""
    modality = "" if morphism.modality == "neutral" else f"{morphism.modality}:"
    args = ",".join(arg for arg in (morphism.subject, morphism.object) if arg)
    return f"{neg}{modality}{morphism.predicate}({args})"


def render_rule(rule) -> str:
    """Readable clause: ``IF is_a(?x,dog) => is_a(?x,mammal) [implication]``.

    A disjunctive head renders its literals with ``OR`` (L2).
    """
    conditions = " AND ".join(render_atom(condition) for condition in rule.conditions) or "TRUE"
    head = " OR ".join(render_atom(literal) for literal in rule.head)
    label = rule.kind if rule.strength == "strict" else f"{rule.kind}, defeasible"
    return f"IF {conditions} => {head} [{label}]"


def _constraint_quote(theory: Theory, witness: str) -> str | None:
    """The quote of the disjointness axiom behind a ``disjoint:left|right`` witness."""
    _, _, pair = witness.partition(":")
    left, _, right = pair.partition("|")
    for constraint in theory.constraints:
        if {constraint.left, constraint.right} == {left, right}:
            return constraint.quote
    return None


def _classify_fact(
    fact: Fact,
    theory: Theory,
    ledger: HypothesisLedger,
    axiom_quotes: dict[FactKey, str | None],
) -> tuple[ExplanationKind, str | None, str | None, str | None, int | None]:
    if fact.key in ledger.fact_keys:
        hypothesis_id = ledger.fact_keys[fact.key]
        return "hypothesis", f"hypothesis:{hypothesis_id}", None, hypothesis_id, fact.rule_index
    quote = axiom_quotes.get(fact.key)
    if fact.axiom:
        return "axiom", "quote" if quote else None, quote, None, None
    if fact.rule_index is not None:
        rule = theory.rules[fact.rule_index - 1]
        return "rule", rule.source, rule.quote, rule.source_hypothesis_id, fact.rule_index
    if fact.witness.startswith("disjoint:"):
        constraint_quote = _constraint_quote(theory, fact.witness)
        return "constraint", "quote" if constraint_quote else None, constraint_quote, None, None
    if fact.witness.startswith("naf:"):
        return "naf", "naf", None, None, None
    if fact.witness.startswith("is_a:"):
        return "is_a", None, None, None, None
    # A non-axiom, non-derived, non-hypothesis fact is a question condition (Gamma);
    # its origin is the question itself, tagged for audit only (see
    # docs/statement_sources.md). The logical role stays "assumption".
    return "assumption", "presupposition", None, None, None


def _trace(
    theory: Theory,
    store,
    hit,
    ledger: HypothesisLedger,
    axiom_quotes: dict[FactKey, str | None],
) -> tuple[list[ExplanationStep], list[str]]:
    """Ordered steps of one proof and the hypotheses it actually uses."""
    steps: list[ExplanationStep] = []
    index_of: dict[FactKey, int] = {}

    def visit(key: FactKey) -> int | None:
        if key in index_of:
            return index_of[key]
        fact = store.by_key.get(key)
        if fact is None:
            return None
        premise_ids = []
        for premise in sorted(fact.premises):
            premise_id = visit(premise)
            if premise_id is not None:
                premise_ids.append(premise_id)
        kind, source, quote, hypothesis, rule_index = _classify_fact(
            fact, theory, ledger, axiom_quotes
        )
        rule_text = (
            render_rule(theory.rules[rule_index - 1])
            if kind == "rule" and rule_index is not None
            else None
        )
        index = len(steps)
        steps.append(
            ExplanationStep(
                index=index,
                kind=kind,
                statement=fact.label(),
                premises=premise_ids,
                rule_index=rule_index,
                rule=rule_text,
                source=source,
                quote=quote,
                hypothesis=hypothesis,
            )
        )
        index_of[key] = index
        return index

    visit(hit.fact.key)
    proof_keys = frozenset(hit.fact.used) | {hit.fact.key}
    return steps, ledger.used(store, proof_keys)


def _single(
    theory: Theory,
    query: Query,
    verdict: Verdict,
    ledger: HypothesisLedger,
    goal,
) -> Explanation:
    """One trace for ``goal`` (default: the target), or empty when unmatched."""
    result = winning_store_hit(theory, query, goal=goal)
    if result is None:
        return Explanation()
    store, hit = result
    axiom_quotes = {morphism_key(m): m.quote for m in theory.morphisms}
    steps, hypotheses = _trace(theory, store, hit, ledger, axiom_quotes)
    return Explanation(
        goal=hit.fact.label(),
        binding=dict(verdict.bindings),
        hypotheses_used=hypotheses,
        steps=steps,
    )


def _conflict(
    theory: Theory,
    query: Query,
    verdict: Verdict,
    ledger: HypothesisLedger,
) -> Explanation:
    """Both branches for a contradicted target: supporting vs attacking."""
    goal = query.target
    negated = goal.model_copy(update={"negated": not goal.negated})
    axiom_quotes = {morphism_key(m): m.quote for m in theory.morphisms}
    supporting: list[ExplanationStep] = []
    attacking: list[ExplanationStep] = []
    hypotheses: list[str] = []
    for branch_goal, sink in ((goal, "supporting"), (negated, "attacking")):
        result = winning_store_hit(theory, query, goal=branch_goal)
        if result is None:
            continue
        steps, used = _trace(theory, result[0], result[1], ledger, axiom_quotes)
        for hypothesis_id in used:
            if hypothesis_id not in hypotheses:
                hypotheses.append(hypothesis_id)
        if sink == "supporting":
            supporting = steps
        else:
            attacking = steps
    note = "; ".join(verdict.gaps) or "both polarities are derivable"
    return Explanation(
        goal=render_atom(goal),
        binding=dict(verdict.bindings),
        hypotheses_used=hypotheses,
        conflict=Conflict(
            kind="strict",
            status="undecided",
            supporting=supporting,
            attacking=attacking,
            defeated="none",
            note=note,
        ),
    )


def _rule_steps(theory: Theory, candidates) -> list[ExplanationStep]:
    steps: list[ExplanationStep] = []
    for candidate in candidates:
        rule = theory.rules[candidate.rule_index - 1]
        steps.append(
            ExplanationStep(
                index=len(steps),
                kind="rule",
                statement=candidate.head.label(),
                rule_index=candidate.rule_index,
                rule=render_rule(rule),
                source=rule.source,
                quote=rule.quote,
                hypothesis=rule.source_hypothesis_id,
            )
        )
    return steps


def _defeasible_enabled() -> bool:
    from ankyra.config.settings import get_setting

    return bool(get_setting("DEFEASIBLE", False))


def _candidate_keys(candidates) -> frozenset[FactKey]:
    """Every provenance key a set of rule applications rests on."""
    keys: set[FactKey] = set()
    for candidate in candidates:
        keys.add(candidate.head.key)
        keys.update(candidate.head.used)
        for fact in candidate.body_facts:
            keys.add(fact.key)
            keys.update(fact.used)
    return frozenset(keys)


def _attach_resolved_conflict(
    theory: Theory, query: Query, explanation: Explanation, goal, ledger: HypothesisLedger
) -> Explanation:
    """Record which more specific rule won, when the defeasible layer decided it."""
    if not explanation.steps or not _defeasible_enabled():
        return explanation
    conflict = _resolved_conflict(theory, query, goal, ledger)
    if conflict is None:
        return explanation
    return explanation.model_copy(update={"conflict": conflict})


def _undecided_conflict(
    theory: Theory, query: Query, ledger: HypothesisLedger
) -> Explanation | None:
    """Both competing rule applications for an undecided defeasible conflict."""
    from ankyra.engine.defeasible import effective_closure

    ctx = build_context(theory)
    negated_target = query.target.model_copy(update={"negated": not query.target.negated})
    store, unresolved, _ = effective_closure(theory, query.conditions)
    supporting = []
    attacking = []
    reason = ""
    for key, entry in unresolved.items():
        if not (
            _key_matches(query.target, key, ctx)
            or _key_matches(negated_target, key, ctx)
        ):
            continue
        reason = reason or entry.reason
        for candidate in entry.candidates:
            if candidate.head.negated == query.target.negated:
                supporting.append(candidate)
            else:
                attacking.append(candidate)
    if not supporting and not attacking:
        return None
    return Explanation(
        goal=render_atom(query.target),
        binding={},
        conflict=Conflict(
            kind="defeasible",
            status="undecided",
            supporting=_rule_steps(theory, supporting),
            attacking=_rule_steps(theory, attacking),
            defeated="none",
            reason=reason or "specificity does not decide between the competing defaults",
            note="undecided: neither default is more specific",
            source_ids=ledger.used(store, _candidate_keys([*supporting, *attacking])),
        ),
    )


def _resolved_conflict(
    theory: Theory, query: Query, goal, ledger: HypothesisLedger
) -> Conflict | None:
    """The defeat that decided ``goal``, with the ``is_a`` witness as the reason."""
    if goal is None:
        return None
    from ankyra.engine.defeasible import effective_closure

    ctx = build_context(theory)
    negated_goal = goal.model_copy(update={"negated": not goal.negated})
    store, _, defeats = effective_closure(theory, query.conditions)
    for defeat in defeats:
        winner, loser = defeat.winner.head, defeat.loser.head
        if not _key_matches(goal, winner.key, ctx):
            continue
        if not _key_matches(negated_goal, loser.key, ctx):
            continue
        return Conflict(
            kind="defeasible",
            status="resolved",
            supporting=_rule_steps(theory, [defeat.winner]),
            attacking=_rule_steps(theory, [defeat.loser]),
            defeated="attacking",
            reason=defeat.reason,
            note="the more specific default wins",
            source_ids=ledger.used(
                store, _candidate_keys([defeat.winner, defeat.loser])
            ),
        )
    return None


def _clause_text(key) -> str:
    if not key:
        return "contradiction"
    return " OR ".join(label_of(literal) for literal in key)


def _classify_clause(origins, theory: Theory):
    """Map a clause's origin label to an explanation kind, rule, source and quote."""
    for origin in origins:
        if origin.startswith("axiom:"):
            return "axiom", None, "quote", None
        if origin.startswith("rule:"):
            index = int(origin.split(":", 1)[1])
            rule = theory.rules[index - 1]
            return "rule", index, rule.source, rule.quote
        if origin == "transitivity":
            return "is_a", None, None, None
        if origin.startswith("constraint:"):
            left, _, right = origin.split(":", 1)[1].partition("|")
            for constraint in theory.constraints:
                if {constraint.left, constraint.right} == {left, right}:
                    return "constraint", None, "quote", constraint.quote
            return "constraint", None, None, None
        if origin.startswith("presupposition:"):
            return "assumption", None, "presupposition", None
        if origin == "goal":
            return "assumption", None, "goal_negation", None
    return "resolution", None, None, None


def _l2_steps(proof, theory: Theory) -> list[ExplanationStep]:
    """Render a resolution refutation as premises-first explanation steps."""
    steps: list[ExplanationStep] = []
    index: dict = {}
    for key in proof.derivation():
        node = proof.nodes.get(key)
        premise_ids: list[int] = []
        if node is not None:
            for parent in node[:2]:
                if parent is not None and parent in index:
                    premise_ids.append(index[parent])
        kind, rule_index, source, quote = _classify_clause(
            proof.origins.get(key, []), theory
        )
        rule = theory.rules[rule_index - 1] if rule_index else None
        steps.append(
            ExplanationStep(
                index=len(steps),
                kind=kind,
                statement=_clause_text(key),
                premises=premise_ids,
                rule_index=rule_index,
                rule=render_rule(rule) if rule else None,
                source=source,
                quote=quote,
            )
        )
        index[key] = steps[-1].index
    return steps


def _l2_explanation(theory: Theory, query: Query, verdict: Verdict) -> Explanation:
    """Build the explanation of an L2 verdict from the resolution proofs."""
    _, outcomes = l2_outcomes(theory, query)
    if not outcomes:
        return Explanation()
    binding = dict(verdict.bindings)
    if verdict.status == "contradiction":
        for goal, outcome, target, complement, _ in outcomes:
            if outcome == "contradiction":
                return Explanation(
                    goal=render_atom(goal),
                    binding=binding,
                    conflict=Conflict(
                        kind="strict",
                        status="undecided",
                        supporting=_l2_steps(target.proof, theory),
                        attacking=_l2_steps(complement.proof, theory),
                        defeated="none",
                        note="both polarities are derivable by resolution",
                    ),
                )
        return Explanation()
    if verdict.status == "supported":
        for goal, outcome, target, _, _ in outcomes:
            if outcome == "supported" and target is not None and target.proof is not None:
                return Explanation(
                    goal=render_atom(goal),
                    binding=binding,
                    steps=_l2_steps(target.proof, theory),
                )
        return Explanation()
    if verdict.status == "refuted":
        for goal, outcome, _, complement, _ in outcomes:
            if outcome in {"refuted", "contradiction"} and complement is not None and complement.proof is not None:
                negated_goal = goal.model_copy(update={"negated": not goal.negated})
                return Explanation(
                    goal=render_atom(negated_goal),
                    binding=binding,
                    steps=_l2_steps(complement.proof, theory),
                )
        return Explanation()
    return Explanation()


def build_explanation(
    theory: Theory,
    query: Query,
    verdict: Verdict,
    ledger: HypothesisLedger,
) -> Explanation:
    """The mechanical derivation of the target, its refutation, or both branches.

    ``supported`` yields the positive trace; ``target_refuted`` the negative one;
    ``contradiction`` both branches; everything else an empty trace.
    """
    if logic_enabled():
        explanation = _l2_explanation(theory, query, verdict)
        if explanation.steps or explanation.conflict:
            return explanation
    if query.target is None:
        return Explanation()
    if verdict.status == "supported":
        explanation = _single(theory, query, verdict, ledger, query.target)
        if not explanation.steps and query.world_assumption == "closed" and query.target.negated:
            # Supported by failure: the positive atom is unprovable (closed world).
            positive = query.target.model_copy(update={"negated": False})
            return Explanation(
                goal=render_atom(query.target),
                binding=dict(verdict.bindings),
                steps=[
                    ExplanationStep(
                        index=0,
                        kind="naf",
                        statement=render_atom(query.target),
                        premises=[],
                        source="naf",
                    )
                ],
            )
        return _attach_resolved_conflict(theory, query, explanation, query.target, ledger)
    if verdict.status == "refuted" and any(
        gap.startswith("target_refuted:") for gap in verdict.gaps
    ):
        negated = query.target.model_copy(update={"negated": not query.target.negated})
        explanation = _single(theory, query, verdict, ledger, negated)
        if explanation.steps:
            return _attach_resolved_conflict(theory, query, explanation, negated, ledger)
        if query.world_assumption == "closed" and any(
            gap.startswith("target_refuted:") for gap in verdict.gaps
        ):
            # The target was refuted by failure (closed world), not by a fact.
            return Explanation(
                goal=render_atom(negated),
                binding=dict(verdict.bindings),
                steps=[
                    ExplanationStep(
                        index=0,
                        kind="naf",
                        statement=render_atom(negated),
                        premises=[],
                        source="naf",
                    )
                ],
            )
        return explanation
    if verdict.status == "contradiction":
        return _conflict(theory, query, verdict, ledger)
    if any(gap.startswith("undecided_conflict:") for gap in verdict.gaps):
        conflict = _undecided_conflict(theory, query, ledger)
        if conflict is not None:
            return conflict
    return Explanation()
