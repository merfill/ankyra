"""Single-task runner: one problem text through every stage, reported as a summary.

Usage (from the repo root, real LLM calls):
    uv run python -m ankyra.cli.solve "All dogs are mammals. Rex is a dog. Is Rex a mammal?"
    cat problem.txt | uv run python -m ankyra.cli.solve --verbose --lang ru
    uv run python -m ankyra.cli.solve --track csp "Six people sit in a row. ..."

The console shows the run live: each stage streams its compact Prolog result
(extracted facts/rules, the built theory, the question, the query, the mechanical
proof), and the guided cycle prints one deterministic block per wave (what the model
proposed, how the classifier judged it, what entered the theory, what the solver then
derived). At the
end a compact report follows in three sections: ``ТЕОРИЯ`` renders the built theory
and the question in plain Prolog form with origin tags, ``ВЫВОД`` lists the solver's
steps (routing, the verdict, the answer) one per line, and ``ЗАКЛЮЧЕНИЕ`` is the short
text written by the LLM from the run state. ``--verbose`` (``--log``) additionally
prints the raw model answers and intermediate JSON dumps. If the conclusion call is
unavailable or fails, a deterministic text built from the run state replaces it and
the error stays in the stage log.

The runner decides nothing itself: it calls the existing Phase 0 assemblers
(``ankyra.build``), the fragment routing and the procedure entry points of
``ankyra.engine``, and the answer/explanation assemblers, printing what each stage
received and produced. The procedure comes from ``engine.inference``; an
``out_of_fragment:*`` refusal is reported as the result, never replaced by a
fallback.

The theory track routes a ``Theory``/``Query`` (horn or clausal). The L3 and L4
engines do not consume a ``Theory``: they have their own extraction, IR builders and
routers, so they are selected with ``--track csp`` / ``--track numeric`` and decided
through ``engine/csp/decide.py`` / ``engine/numeric/decide.py``.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, TextIO, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage

from ankyra.build.extract import extract_problem_structure, extract_question_structure
from ankyra.build.pipeline import build_query, build_theory, default_world_assumption
from ankyra.config.settings import get_setting
from ankyra.core.models import (
    Answer,
    Constraint,
    Explanation,
    FactKey,
    Hypothesis,
    Morphism,
    Query,
    Revision,
    Rule,
    Theory,
    Verdict,
    WaveRecord,
)
from ankyra.core.schemas import Slot, StructAtom, StructRule
from ankyra.engine.answer import build_answer, render_answer
from ankyra.engine.cycle import CycleEvent, run_cycle
from ankyra.engine.explain import build_explanation
from ankyra.engine.inference import analyze_routing
from ankyra.engine.ledger import HypothesisLedger
from ankyra.engine.narrate import narrate_explanation
from ankyra.engine.proposal import effective_action, propose as propose_default
from ankyra.engine.verify import verify
from ankyra.llm import trace as llm_trace

T = TypeVar("T")

TRACKS = ("theory", "csp", "numeric")


@dataclass
class StageLog:
    """Structured stage log; ``live`` streams each line, ``flush`` drains the rest.

    In live mode a line reaches ``out`` the moment it is written, so the run is
    observable while it lasts; ``flush`` then prints only what was never streamed
    (nothing, unless the log was buffered). A buffered log (``live=False``) keeps
    everything for ``flush``, which is what the library tests use.
    """

    out: TextIO = sys.stdout
    verbose: bool = False
    live: bool = False
    _index: int = 0
    _lines: list[str] = field(default_factory=list)
    _emitted: int = 0
    stages: list[str] = field(default_factory=list)

    def stage(self, title: str) -> None:
        self._index += 1
        self.stages.append(title)
        if self._index > 1:
            self.write()
        self.write(f"=== ЭТАП {self._index}: {title} ===")

    def write(self, line: str = "") -> None:
        self._lines.append(line)
        if self.live:
            print(line, file=self.out, flush=True)
            self._emitted = len(self._lines)

    def lines(self) -> list[str]:
        """A copy of everything buffered so far."""
        return list(self._lines)

    def flush(self) -> None:
        """Print the lines not streamed live yet and drop the buffer."""
        for line in self._lines[self._emitted:]:
            print(line, file=self.out)
        self._lines.clear()
        self._emitted = 0

    def field(self, name: str, value: Any) -> None:
        self.write(f"  {name}: {value}")

    def block(self, title: str, body: str) -> None:
        self.write(f"  {title}:")
        text = body.rstrip("\n")
        if not text:
            self.write("    (empty)")
            return
        for line in text.splitlines():
            self.write(f"    {line}")

    def detail(self, title: str, body: str) -> None:
        """A large dump (raw model answer, built IR); silent in quiet mode."""
        if self.verbose:
            self.block(title, body)


@dataclass
class SolveResult:
    """What the run produced: the chosen track, the answer, the refusal, if any."""

    track: str
    status: str
    answer: Answer | None = None
    explanation: Explanation | None = None
    theory: Theory | None = None
    query: Query | None = None
    verdict: Verdict | None = None
    refusal: str | None = None
    procedure: str = ""
    final_text: str = ""
    summary: str = ""
    summary_source: str = ""
    steps: list[str] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    waves: list[WaveRecord] = field(default_factory=list)
    revisions: list[Revision] = field(default_factory=list)
    calls: list[llm_trace.LLMCall] = field(default_factory=list)


def _render_steps(explanation: Explanation) -> str:
    """Deterministic rendering of a proof trace; no interpretation of the text."""
    lines: list[str] = []
    if explanation.goal:
        lines.append(f"goal: {explanation.goal}")
    if explanation.hypotheses_used:
        lines.append(f"depends on hypotheses: {', '.join(explanation.hypotheses_used)}")
    for step in explanation.steps:
        detail = f"{step.index}. [{step.kind}] {step.statement}"
        if step.premises:
            detail += f"  <- steps {step.premises}"
        if step.source:
            detail += f"  [{step.source}]"
        if step.quote:
            detail += f'  quote="{step.quote}"'
        lines.append(detail)
        if step.rule:
            lines.append(f"      rule {step.rule_index}: {step.rule}")
    conflict = explanation.conflict
    if conflict is not None:
        detail = f"conflict: {conflict.kind}, {conflict.status}, defeated={conflict.defeated}"
        if conflict.reason:
            detail += f" — {conflict.reason}"
        lines.append(detail)
        for label, branch in (("supporting", conflict.supporting), ("attacking", conflict.attacking)):
            lines.append(f"  {label}:")
            for step in branch:
                lines.append(f"    {step.index}. [{step.kind}] {step.statement}")
    return "\n".join(lines)


def _prolog_atom(morphism: Morphism) -> str:
    """One literal in plain Prolog form: ``raining``, ``wet(ground)``, ``\\+ wet(ground)``."""
    args = ", ".join(arg for arg in (morphism.subject, morphism.object) if arg)
    atom = f"{morphism.predicate}({args})" if args else morphism.predicate
    if morphism.modality != "neutral":
        atom = f"{morphism.modality}:{atom}"
    return f"\\+ {atom}" if morphism.negated else atom


def _prolog_rule(rule: Rule) -> str:
    """One clause: ``wet(ground) :- raining.``; a disjunctive head joins with ``;``."""
    head = " ; ".join(_prolog_atom(literal) for literal in rule.head)
    body = ", ".join(_prolog_atom(condition) for condition in rule.conditions)
    return f"{head} :- {body}." if body else f"{head}."


def _prolog_constraint(constraint: Constraint) -> str:
    """An integrity constraint: no individual is a member of both disjoint classes."""
    return f":- is_a(X, {constraint.left}), is_a(X, {constraint.right})."


def _prolog_query(query: Query) -> str:
    """The question as Prolog goals: the target, or the decomposed goals."""
    if query.target is not None:
        body = _prolog_atom(query.target)
    elif query.goals:
        body = ", ".join(_prolog_atom(goal) for goal in query.goals)
    elif query.goal_clauses:
        body = ", ".join(
            "(" + "; ".join(_prolog_atom(literal) for literal in clause) + ")"
            for clause in query.goal_clauses
        )
    else:
        body = "(no goal)"
    return f"{body}."


def _slot_text(slot: Slot) -> str:
    """Compact rendering of an extraction slot (id, AND-set, OR-variants, exclusions)."""
    parts: list[str] = []
    if slot.id:
        parts.append(slot.id)
    if slot.set:
        parts.append("+".join(slot.set))
    if slot.variants:
        parts.append("|".join(slot.variants))
    if slot.exclude:
        parts.append("without " + ", ".join(slot.exclude))
    return " ".join(parts)


def _struct_atom_text(atom: StructAtom) -> str:
    """One extracted atom as ``predicate(args)``, before the deterministic build."""
    subject, obj = _slot_text(atom.subject), _slot_text(atom.object)
    args = f"{subject}, {obj}" if subject and obj else (subject or obj)
    body = f"{atom.predicate}({args})" if args else atom.predicate
    neg = "NOT " if atom.negated else ""
    modality = "" if atom.modality == "neutral" else f"{atom.modality}:"
    return f"{neg}{modality}{body}"


def _struct_rule_text(rule: StructRule) -> str:
    """One extracted rule as ``IF body => head`` (disjunctions kept as OR)."""
    if rule.disjunctive_antecedent:
        body = " OR ".join(_struct_atom_text(atom) for atom in rule.disjunctive_antecedent)
    else:
        body = " AND ".join(_struct_atom_text(atom) for atom in rule.antecedent)
    heads = rule.consequents or ([rule.consequent] if rule.consequent.predicate else [])
    head = " OR ".join(_struct_atom_text(atom) for atom in heads) or "(none)"
    kind = "" if rule.kind == "implication" else f" [{rule.kind}]"
    return f"IF {body or 'TRUE'} => {head}{kind}"


def _question_structure_text(question: Any) -> str:
    """The extracted question in compact form: givens, rules, and the goal forms."""
    lines: list[str] = []
    if question.presuppositions:
        given = " AND ".join(_struct_atom_text(atom) for atom in question.presuppositions)
        lines.append(f"given: {given}")
    for rule in question.rules:
        lines.append(f"rule: {_struct_rule_text(rule)}")
    if question.ask is not None and question.ask.predicate:
        lines.append(f"ask: {_struct_atom_text(question.ask)}")
    if question.ask_all:
        lines.append("ask all: " + " AND ".join(_struct_atom_text(a) for a in question.ask_all))
    if question.ask_any:
        lines.append("ask any: " + " OR ".join(_struct_atom_text(a) for a in question.ask_any))
    if question.ask_universal:
        lines.append(
            "ask universal: "
            + " OR ".join(_struct_atom_text(a) for a in question.ask_universal)
        )
    if question.ask_clauses:
        clauses = " AND ".join(
            "(" + " OR ".join(_struct_atom_text(a) for a in clause) + ")"
            for clause in question.ask_clauses
        )
        lines.append(f"ask clauses: {clauses}")
    if question.variables:
        variables = ", ".join(f"?{key}={value}" for key, value in question.variables.items())
        lines.append(f"variables: {variables}")
    return "\n".join(lines) or "(no goal)"


def _fact_tag(hypotheses: list[Hypothesis], morphism: Morphism) -> str:
    """Origin of a theory fact: a hypothesis id or an explicit quote marker."""
    for hypothesis in hypotheses:
        if hypothesis.kind == "fact" and hypothesis.payload == morphism:
            return f" [{hypothesis.id}]"
    return " [quote]" if morphism.quote else ""


def _rule_tag(rule: Rule) -> str:
    """Origin of a rule: its hypothesis tag when tagged, else the quote marker."""
    if rule.source_hypothesis_id:
        return f" [{rule.source_hypothesis_id}]"
    return " [quote]" if rule.quote else ""


def _theory_rows(
    theory: Theory | None, hypotheses: list[Hypothesis] | None = None
) -> list[tuple[str, str]]:
    """``(label, clause)`` rows of a theory, one clause each, with origin tags."""
    rows: list[tuple[str, str]] = []
    if theory is None:
        return rows
    tagged = hypotheses or []
    rows += [
        ("факт", _prolog_atom(morphism) + "." + _fact_tag(tagged, morphism))
        for morphism in theory.morphisms
    ]
    rows += [("правило", _prolog_rule(rule) + _rule_tag(rule)) for rule in theory.rules]
    rows += [
        ("ограничение", _prolog_constraint(constraint) + (" [quote]" if constraint.quote else ""))
        for constraint in theory.constraints
    ]
    return rows


def _rows_text(rows: list[tuple[str, str]]) -> str:
    """One clause per line, ``label: clause``; ``(empty)`` when there are none."""
    return "\n".join(f"{label}: {clause}" for label, clause in rows) or "(empty)"


def _prolog_theory(result: SolveResult) -> list[tuple[str, str]]:
    """``(label, clause)`` rows of the theory and the question, one clause each."""
    rows = _theory_rows(result.theory, result.hypotheses)
    if result.query is not None:
        rows.append(("вопрос", _prolog_query(result.query)))
    return rows


def _report_lines(result: SolveResult) -> list[str]:
    """The default report: theory, the solver's steps, the conclusion."""
    lines = ["ТЕОРИЯ"]
    rows = _prolog_theory(result)
    if rows:
        width = max(len(f"{label}:") for label, _ in rows) + 1
        lines += [f"  {f'{label}:':<{width}}{clause}" for label, clause in rows]
    else:
        lines.append("  (this track builds no theory)")
    lines += ["", "ВЫВОД"]
    if result.steps:
        lines += [f"  шаг {index}: {step}" for index, step in enumerate(result.steps, 1)]
    else:
        lines.append("  (the solver did not run)")
    lines += ["", "ЗАКЛЮЧЕНИЕ"]
    conclusion = result.summary.strip()
    if conclusion:
        lines += [f"  {line}" for line in conclusion.splitlines()]
    else:
        lines.append("  (no conclusion)")
    return lines


def _print_report(result: SolveResult, out: TextIO) -> None:
    """Write the compact three-section report to ``out``."""
    for line in _report_lines(result):
        print(line, file=out)


def _log_calls(log: StageLog, calls: list[llm_trace.LLMCall], result: SolveResult) -> None:
    """Print every raw model answer recorded for one stage."""
    for call in calls:
        result.calls.append(call)
        log.detail(
            f"LLM {call.label} ({call.schema or 'no schema'}, {call.duration_ms} ms)",
            call.raw or "",
        )
        if call.error:
            log.field("LLM error", call.error)


def _traced(log: StageLog, fn: Callable[[], T], result: SolveResult) -> T:
    """Run one stage with LLM tracing on, so its raw answers land in the log."""
    with llm_trace.tracing() as trace:
        try:
            value = fn()
        finally:
            _log_calls(log, trace.calls, result)
    return value


def _route(log: StageLog, routing: Any) -> None:
    log.field("fragment", ", ".join(sorted(routing.fragment)) or "(none)")
    log.field("procedure", routing.procedure)
    log.field("capabilities", ", ".join(sorted(routing.capabilities)))
    log.field("world assumption", routing.world_assumption)
    log.field("defeasible", routing.defeasible)
    log.field("reasons", ", ".join(routing.reasons) or "(none)")
    log.field("refusal", routing.refusal or "(none)")


def _closure_labels(theory: Theory) -> dict[FactKey, str]:
    """Labels of the facts the solver derives (asserted axioms excluded)."""
    from ankyra.engine.horn import derive_store

    try:
        store = derive_store(theory)
    except Exception:
        return {}
    return {fact.key: fact.label() for fact in store.facts if not fact.axiom}


def _theory_delta(
    before: Theory,
    after: Theory,
    hypothesis: Hypothesis | None = None,
) -> list[tuple[str, str]]:
    """Rows appended by one classification wave; the theory only ever grows."""

    def tag(item: Morphism | Rule | Constraint) -> str:
        if hypothesis is not None and (
            (hypothesis.kind == "fact" and isinstance(item, Morphism))
            or (hypothesis.kind == "rule" and isinstance(item, Rule))
        ):
            return f" [{hypothesis.id}]"
        return " [quote]" if getattr(item, "quote", None) else ""

    rows: list[tuple[str, str]] = []
    rows += [
        ("факт", _prolog_atom(morphism) + "." + tag(morphism))
        for morphism in after.morphisms[len(before.morphisms):]
    ]
    rows += [
        ("правило", _prolog_rule(rule) + tag(rule))
        for rule in after.rules[len(before.rules):]
    ]
    rows += [
        ("ограничение", _prolog_constraint(constraint) + tag(constraint))
        for constraint in after.constraints[len(before.constraints):]
    ]
    return rows


def _render_draft(draft: Any) -> list[str]:
    """One proposal in Prolog form plus the model's narration, verbatim."""
    action = effective_action(draft) or draft.action
    lines = [f"предложено: {action}"]
    if draft.rule is not None:
        lines.append(_prolog_rule(draft.rule))
    if draft.fact is not None:
        lines.append(_prolog_atom(draft.fact) + ".")
    if draft.query is not None:
        lines.append(_prolog_query(draft.query))
    if draft.subgoal:
        lines.append(f"subgoal: {draft.subgoal}")
    narration = (draft.narration or "").strip()
    if narration:
        lines.append(f"доводы: {narration}")
    return lines


def _revision_line(revision: Revision) -> str:
    previous = revision.previous
    before = f"{previous.kind}/{previous.strength}" if previous is not None else "(none)"
    current = f"{revision.current.kind}/{revision.current.strength}"
    # The engine records waves 0-based; the console speaks human wave numbers.
    return f"волна {revision.wave + 1}: {before} -> {current} ({revision.trigger})"


def _log_proposed(log: StageLog, event: CycleEvent) -> None:
    """The model's one action for this wave, before the classifier judges it."""
    log.write()
    log.write(f"── волна {event.wave} ──")
    if event.draft is None:
        log.write(f"  предложено: (нет — {event.status})")
        return
    for line in _render_draft(event.draft):
        log.write(f"  {line}")


def _log_classified(
    log: StageLog,
    event: CycleEvent,
    previous_theory: Theory,
    previous_query: Query,
) -> None:
    """What the classifier did with the proposal, and what entered the theory."""
    pending = event.pending
    if pending is None:
        return
    log.write(f"  классификация: {pending.category} ({pending.reason})")
    rows = _theory_delta(previous_theory, event.theory, pending.hypothesis)
    if not rows and event.query == previous_query:
        log.write("    теория не изменилась")
    for label, clause in rows:
        log.write(f"    + {label}: {clause}")
    if event.query != previous_query:
        log.write(f"    + вопрос: {_prolog_query(event.query)}")


def _log_verified(
    log: StageLog,
    result: SolveResult,
    event: CycleEvent,
    previous_closure: dict[FactKey, str],
) -> None:
    """The solver's verdict after a wave, plus the facts this wave added."""
    verdict = event.verdict
    if verdict is not None:
        log.field("status", event.status)
        if event.wave == 0:
            log.field("shelf", verdict.shelf)
            log.field(
                "bindings",
                ", ".join(f"{k}={v}" for k, v in verdict.bindings.items()) or "(none)",
            )
            log.field("gaps", ", ".join(verdict.gaps) or "(none)")
            log.field("matched quotes", len(verdict.matched))
            log.field(
                "unused premises",
                ", ".join(map(str, verdict.unused_premises)) or "(none)",
            )
        elif verdict.gaps:
            log.field("gaps", ", ".join(verdict.gaps))
        result.verdict = verdict
    answer = event.answer
    if answer is not None:
        value = f" = {answer.value}" if answer.value else ""
        log.field("answer", f"{answer.kind} / {answer.strength}{value}")
        prefix = "решатель" if event.wave == 0 else f"волна {event.wave}"
        result.steps.append(f"{prefix}: {event.status}, ответ {answer.kind} / {answer.strength}")
    current = _closure_labels(event.theory)
    added = sorted(current[key] for key in current if key not in previous_closure)
    removed = sorted(previous_closure[key] for key in previous_closure if key not in current)
    if added:
        log.write("  ⊢ выведено: " + ", ".join(added))
    if removed:
        log.write("  ⊣ снято: " + ", ".join(removed))
    if not added and not removed:
        log.write("  ⊢ выведено: (нет новых фактов)")


def _run_horn_cycle(
    log: StageLog,
    result: SolveResult,
    theory: Theory,
    query: Query,
    proposer: Any,
    *,
    max_waves: int | None = None,
) -> Any:
    """Run the guided cycle, streaming one deterministic block per wave."""
    previous_theory, previous_query = theory, query
    previous_closure: dict[FactKey, str] = {}

    def on_event(event: CycleEvent) -> None:
        nonlocal previous_theory, previous_query, previous_closure
        if event.node == "proposed":
            _log_proposed(log, event)
        elif event.node == "classified":
            _log_classified(log, event, previous_theory, previous_query)
        elif event.node == "verified":
            _log_verified(log, result, event, previous_closure)
            previous_theory, previous_query = event.theory, event.query
            previous_closure = _closure_labels(event.theory)

    cycle = run_cycle(
        lambda ctx: propose_default(proposer, ctx),
        theory,
        query,
        max_waves=max_waves,
        on_event=on_event,
    )
    result.theory, result.query, result.verdict = cycle.theory, cycle.query, cycle.verdict
    result.answer, result.explanation = cycle.answer, cycle.explanation
    result.hypotheses = list(cycle.hypotheses)
    result.waves = list(cycle.history)
    result.revisions = list(cycle.revisions)
    for revision in cycle.revisions:
        log.field("ревизия", _revision_line(revision))
        result.steps.append(_revision_line(revision))
    log.field("waves", len(cycle.history))
    log.field("cycle status", cycle.status)
    result.steps.append(f"цикл: статус {cycle.status}, волн {len(cycle.history)}")
    return cycle


def _solve(
    procedure: str,
    log: StageLog,
    *,
    theory: Theory | None = None,
    query: Query | None = None,
    game: Any = None,
    question: Any = None,
    numeric_query: Any = None,
) -> Any:
    """Call the entry point the routing decision names; the choice is not ours."""
    if procedure == "csp":
        from ankyra.engine.csp.decide import decide as csp_decide

        log.field("entry point", "ankyra.engine.csp.decide.decide")
        return csp_decide(game, question)
    if procedure == "numeric":
        from ankyra.engine.numeric.decide import decide as numeric_decide

        log.field("entry point", "ankyra.engine.numeric.decide.decide")
        return numeric_decide(game, numeric_query)
    log.field("entry point", "ankyra.engine.verify.verify")
    return verify(theory, query)


def _refused(result: SolveResult, log: StageLog, routing: Any) -> bool:
    """Report an ``out_of_fragment:*`` refusal as the result; never fall back."""
    if not routing.refusal:
        return False
    log.field("status", "out_of_fragment")
    result.status = "out_of_fragment"
    result.refusal = routing.refusal
    result.steps.append(f"отказ вне фрагмента: {routing.refusal}")
    return True


def run_theory(
    text: str,
    llm: Any,
    log: StageLog,
    result: SolveResult,
    *,
    proposer: Any = None,
    world_assumption: str | None = None,
    max_waves: int | None = None,
) -> SolveResult:
    """Theory/Query track: Phase 0 → routing → verify/cycle → answer and proof."""
    proposer = proposer or llm
    log.stage("Extract the problem structure (Phase 0)")
    log.field("input chars", len(text))
    structure = _traced(log, lambda: extract_problem_structure(llm, text=text), result)
    log.block(
        f"objects ({len(structure.objects)})",
        ", ".join(obj.id for obj in structure.objects) or "(none)",
    )
    log.block(
        f"facts ({len(structure.facts)})",
        "\n".join(_struct_atom_text(atom) for atom in structure.facts) or "(none)",
    )
    log.block(
        f"rules ({len(structure.rules)})",
        "\n".join(_struct_rule_text(rule) for rule in structure.rules) or "(none)",
    )
    log.field("question (verbatim)", structure.question or "(none)")
    log.detail("structure", structure.model_dump_json(indent=2))
    result.steps.append(
        f"разобрана задача: объектов {len(structure.objects)}, "
        f"фактов {len(structure.facts)}, правил {len(structure.rules)}"
    )

    log.stage("Build the theory")
    theory = build_theory(structure)
    result.theory = theory
    log.field("objects", len(theory.objects))
    log.field("axioms (morphisms)", len(theory.morphisms))
    log.field("rules", len(theory.rules))
    log.field("constraints", len(theory.constraints))
    log.field("existentials", len(theory.existentials))
    log.field("domain", ", ".join(theory.domain) or "(none)")
    log.block("theory (Prolog)", _rows_text(_theory_rows(theory)))
    log.detail("theory", theory.model_dump_json(indent=2))
    result.steps.append(
        f"построена теория: фактов {len(theory.morphisms)}, правил {len(theory.rules)}, "
        f"ограничений {len(theory.constraints)}, экзистенциалов {len(theory.existentials)}"
    )

    log.stage("Extract the question structure (Phase 0)")
    question_structure = _traced(
        log,
        lambda: extract_question_structure(
            llm, question=structure.question, theory=theory, source_text=text
        ),
        result,
    )
    log.block("question (Prolog)", _question_structure_text(question_structure))
    log.detail("question structure", question_structure.model_dump_json(indent=2))

    log.stage("Build the query")
    query = build_query(
        question_structure,
        domain=theory.domain,
        world_assumption=world_assumption or default_world_assumption(),
    )
    result.query = query
    log.field("answer type", query.answer_type)
    log.field("goal mode", query.goal_mode)
    log.field("target", query.target.predicate if query.target else "(none)")
    log.field("conditions", len(query.conditions))
    if query.conditions:
        log.block("conditions (Prolog)", ", ".join(_prolog_atom(c) for c in query.conditions))
    log.block("query (Prolog)", _prolog_query(query))
    log.detail("query", query.model_dump_json(indent=2))

    log.stage("Route the problem (analyze_routing)")
    routing = analyze_routing(theory, query)
    result.procedure = routing.procedure
    _route(log, routing)
    result.steps.append(
        f"маршрут: фрагмент {', '.join(sorted(routing.fragment)) or '(нет)'}, "
        f"процедура {routing.procedure}, допущение {routing.world_assumption}"
    )
    if _refused(result, log, routing):
        return result

    log.stage(f"Solve (procedure: {routing.procedure})")
    ledger = HypothesisLedger()
    cycle = None
    if routing.procedure == "horn":
        # The Horn path runs the guided cycle: its first verify is the initial
        # solve; every later wave is one proposal plus one re-check.
        log.field("entry point", "ankyra.engine.verify.verify")
        cycle = _run_horn_cycle(
            log, result, theory, query, proposer, max_waves=max_waves
        )
        theory, query, verdict = cycle.theory, cycle.query, cycle.verdict
        result.theory, result.query, result.verdict = theory, query, verdict
    else:
        verdict = _solve(routing.procedure, log, theory=theory, query=query)
        result.verdict = verdict
        log.field("status", verdict.status)
        log.field("shelf", verdict.shelf)
        log.field("bindings", ", ".join(f"{k}={v}" for k, v in verdict.bindings.items()) or "(none)")
        log.field("gaps", ", ".join(verdict.gaps) or "(none)")
        log.field("matched quotes", len(verdict.matched))
        log.field("unused premises", ", ".join(map(str, verdict.unused_premises)) or "(none)")
        log.detail("verdict", verdict.model_dump_json(indent=2))
        result.steps.append(f"решатель {routing.procedure}: статус {verdict.status}")
        if verdict.bindings:
            result.steps.append(
                "привязки: " + ", ".join(f"{key}={value}" for key, value in verdict.bindings.items())
            )
        if verdict.gaps:
            result.steps.append("пробелы вывода: " + ", ".join(verdict.gaps))

    log.stage("Assemble the answer and the proof")
    if cycle is not None:
        answer, explanation = cycle.answer, cycle.explanation
        result.status = cycle.status
    else:
        answer = build_answer(theory, query, verdict, ledger, verdict.status)
        explanation = build_explanation(theory, query, verdict, ledger)
        result.status = verdict.status
    result.answer, result.explanation = answer, explanation
    log.field("answer kind", answer.kind)
    log.field("strength", answer.strength)
    log.field("value", answer.value or "(none)")
    log.field("hypotheses used", ", ".join(answer.hypotheses_used) or "(none)")
    log.field("defeasible", answer.defeasible)
    log.block("proof (mechanical)", _render_steps(explanation))
    result.steps.append(f"ответ: {answer.kind}, сила {answer.strength}")
    if answer.hypotheses_used:
        result.steps.append("пополнение базы: гипотезы " + ", ".join(answer.hypotheses_used))
    return result


def run_csp(text: str, llm: Any, log: StageLog, result: SolveResult) -> SolveResult:
    """L3 track: CSP extraction → IR → question → ``engine.csp.decide``."""
    from ankyra.build.csp import build_csp_game, build_csp_question
    from ankyra.build.extract_csp import extract_csp_game, extract_csp_question
    from ankyra.engine.csp.answer import build_csp_answer, build_csp_explanation
    from ankyra.engine.inference import analyze_csp_routing

    log.stage("Extract the CSP game (Phase 0, L3)")
    log.field("input chars", len(text))
    game_structure = _traced(log, lambda: extract_csp_game(llm, text=text), result)
    log.field("domains", len(game_structure.domains))
    log.field("variables", len(game_structure.variables))
    log.field("constraints", len(game_structure.constraints))
    log.detail("game structure", game_structure.model_dump_json(indent=2))

    log.stage("Build the CSP game")
    try:
        game = build_csp_game(game_structure, source_text=text)
    except ValueError as exc:
        log.field("build error", f"{type(exc).__name__}: {exc}")
        result.status = "build_error"
        return result
    log.field("domains", ", ".join(domain.id for domain in game.domains) or "(none)")
    log.field("variables", ", ".join(variable.id for variable in game.variables) or "(none)")
    log.field("constraints", len(game.constraints))
    log.detail("game", game.model_dump_json(indent=2))

    log.stage("Extract the CSP question (Phase 0, L3)")
    question_structure = _traced(
        log,
        lambda: extract_csp_question(llm, question=text, game=game, source_text=text),
        result,
    )
    log.detail("question structure", question_structure.model_dump_json(indent=2))

    log.stage("Build the CSP question")
    try:
        question = build_csp_question(question_structure, game=game)
    except ValueError as exc:
        log.field("build error", f"{type(exc).__name__}: {exc}")
        result.status = "build_error"
        return result
    log.field("kind", question.kind)
    log.field("options", len(question.options))
    log.field("assumptions", len(question.assumptions))
    log.detail("question", question.model_dump_json(indent=2))

    log.stage("Route the CSP question (analyze_csp_routing)")
    routing = analyze_csp_routing(question)
    _route(log, routing)
    result.steps.append(
        f"маршрут: фрагмент {', '.join(sorted(routing.fragment)) or '(нет)'}, "
        f"процедура {routing.procedure}, допущение {routing.world_assumption}"
    )
    if _refused(result, log, routing):
        return result

    log.stage(f"Solve (procedure: {routing.procedure})")
    decision = _solve(routing.procedure, log, game=game, question=question)
    log.field("status", decision.status)
    log.field("option index", decision.index)
    log.field("verified options", decision.verified)
    log.field("witness", decision.witness or "(none)")
    log.field("complete list", decision.complete_list or "(none)")
    log.field("detail", decision.detail or "(none)")
    result.steps.append(
        f"решатель {routing.procedure}: статус {decision.status}, "
        f"проверено вариантов {decision.verified}"
    )

    log.stage("Assemble the answer and the proof")
    answer = build_csp_answer(decision)
    explanation = build_csp_explanation(decision)
    result.answer, result.explanation = answer, explanation
    log.field("answer kind", answer.kind)
    log.field("strength", answer.strength)
    log.field("value", answer.value or "(none)")
    log.block("proof (mechanical)", _render_steps(explanation))
    result.status = decision.status
    return result


def run_numeric(text: str, llm: Any, log: StageLog, result: SolveResult) -> SolveResult:
    """L4 track: numeric extraction → IR → query → ``engine.numeric.decide``."""
    from ankyra.build.extract_numeric import extract_numeric_game, extract_numeric_query
    from ankyra.build.numeric import build_numeric_game, build_numeric_query
    from ankyra.engine.inference import analyze_numeric_routing

    log.stage("Extract the numeric game (Phase 0, L4)")
    log.field("input chars", len(text))
    game_structure = _traced(log, lambda: extract_numeric_game(llm, text=text), result)
    log.field("quantities", len(game_structure.quantities))
    log.field("equations", len(game_structure.equations))
    log.detail("game structure", game_structure.model_dump_json(indent=2))

    log.stage("Build the numeric game")
    try:
        game = build_numeric_game(game_structure, source_text=text)
    except ValueError as exc:
        log.field("build error", f"{type(exc).__name__}: {exc}")
        result.status = "build_error"
        return result
    log.field(
        "quantities",
        ", ".join(quantity.id for quantity in game.quantities) or "(none)",
    )
    log.field("equations", len(game.equations))
    log.detail("game", game.model_dump_json(indent=2))

    log.stage("Extract the numeric query (Phase 0, L4)")
    query_structure = _traced(
        log,
        lambda: extract_numeric_query(llm, question=text, game=game, source_text=text),
        result,
    )
    log.detail("query structure", query_structure.model_dump_json(indent=2))

    log.stage("Build the numeric query")
    try:
        numeric_query = build_numeric_query(query_structure, game=game)
    except ValueError as exc:
        log.field("build error", f"{type(exc).__name__}: {exc}")
        result.status = "build_error"
        return result
    log.field("target", numeric_query.target)
    log.field("tolerance", numeric_query.tolerance)
    log.detail("query", numeric_query.model_dump_json(indent=2))

    log.stage("Route the numeric query (analyze_numeric_routing)")
    routing = analyze_numeric_routing(numeric_query)
    _route(log, routing)
    result.steps.append(
        f"маршрут: фрагмент {', '.join(sorted(routing.fragment)) or '(нет)'}, "
        f"процедура {routing.procedure}, допущение {routing.world_assumption}"
    )
    if _refused(result, log, routing):
        return result

    log.stage(f"Solve (procedure: {routing.procedure})")
    decision = _solve(routing.procedure, log, game=game, numeric_query=numeric_query)
    log.field("status", decision.status)
    log.field("value", decision.value if decision.value is not None else "(none)")
    log.field("detail", decision.detail or "(none)")
    result.steps.append(
        f"решатель {routing.procedure}: статус {decision.status}, "
        f"значение {decision.value if decision.value is not None else '(нет)'}"
    )

    log.stage("Assemble the answer and the proof")
    from ankyra.engine.numeric.answer import build_numeric_answer, build_numeric_explanation

    answer = build_numeric_answer(decision)
    explanation = build_numeric_explanation(decision)
    result.answer, result.explanation = answer, explanation
    log.field("answer kind", answer.kind)
    log.field("strength", answer.strength)
    log.field("value", answer.value or "(none)")
    log.block("proof (mechanical)", _render_steps(explanation))
    result.status = decision.status
    return result


def _finish(
    result: SolveResult,
    log: StageLog,
    *,
    lang: str,
    narration_llm: Any = None,
) -> SolveResult:
    """Final answer in the language of the problem; prose when narration is on."""
    log.stage("Final answer")
    if result.refusal:
        log.field("refusal", result.refusal)
        log.field("answer", f"out of fragment: {result.refusal}")
        result.final_text = f"Out of fragment: {result.refusal}"
        result.steps.append(f"итог: вне фрагмента ({result.refusal})")
        return result
    if result.answer is None:
        log.field("answer", "(none)")
        result.final_text = f"No answer (status: {result.status})"
        result.steps.append(f"итог: ответа нет (статус {result.status})")
        return result

    direct = render_answer(result.answer, lang)
    log.field("status", result.status)
    log.field("direct answer", direct)
    result.final_text = direct
    result.steps.append(f"итог: {direct}")
    if narration_llm is not None and result.explanation is not None:
        try:
            prose = _traced(
                log,
                lambda: narrate_explanation(
                    narration_llm,
                    result.explanation,
                    answer=result.answer,
                    language=lang,
                ),
                result,
            )
        except Exception as exc:
            log.field("narration error", f"{type(exc).__name__}: {exc}")
            prose = ""
        if prose:
            log.detail("narration", prose)
            result.final_text = prose
    return result


SUMMARY_SYSTEM = """You write the conclusion section of the closing report of one
finished run of an automated reasoning pipeline. You are given the original problem
text, the built theory and the question in Prolog form, the steps the solver took, and
the final answer. Say in a few short sentences what was asked, how the answer was
obtained (or why it was not), judging from the routing fields and the solver steps,
and restate the final answer. Use ONLY the run state you are given: add no facts, do
not re-derive the answer, and never contradict it. Return plain text, no markdown, no
JSON."""


def _summary_prompt(text: str, result: SolveResult, stages: list[str], lang: str) -> str:
    """The run state for the conclusion: task, theory, steps, answer."""
    lines = [f"Original problem:\n{text}", "", f"Track: {result.track}"]
    lines.append(f"Procedure: {result.procedure or '(not routed)'}")
    lines.append(f"Run status: {result.status}")
    if result.refusal:
        lines.append(f"Refusal: {result.refusal}")
    lines.append(f"Final answer: {result.final_text or '(none)'}")
    lines.append("Theory (Prolog):")
    rows = _prolog_theory(result)
    lines.extend(f"  {label}: {clause}" for label, clause in rows)
    if not rows:
        lines.append("  (none)")
    lines.append("Solver steps:")
    lines.extend(f"  {index}. {step}" for index, step in enumerate(result.steps, 1))
    if not result.steps:
        lines.append("  (none)")
    lines.append("Stages:")
    lines.extend(f"  {index}. {title}" for index, title in enumerate(stages, 1))
    lines.append("")
    lines.append(f"Write the conclusion in this language: {lang}.")
    return "\n".join(lines)


def _call_summary(llm: Any, messages: list[Any]) -> str:
    started = time.perf_counter()
    try:
        response = llm.invoke(messages)
    except Exception as exc:
        llm_trace.record_direct(
            "summary",
            messages,
            None,
            duration_ms=(time.perf_counter() - started) * 1000,
            error=str(exc),
        )
        raise
    content = str(getattr(response, "content", None) or response).strip()
    llm_trace.record_direct(
        "summary", messages, content, duration_ms=(time.perf_counter() - started) * 1000
    )
    return content


def _fallback_summary(text: str, result: SolveResult, stages: list[str], lang: str) -> str:
    """Deterministic report from the run state; used when the summary call fails."""
    task = " ".join(text.split())
    if len(task) > 200:
        task = task[:197].rstrip() + "..."
    procedure = result.procedure or "(not routed)"
    if str(lang).lower().startswith("ru"):
        route = f"Трек: {result.track}, процедура: {procedure}, стадий пройдено: {len(stages)}."
        if result.refusal:
            outcome = f"Итог: отказ вне фрагмента ({result.refusal})."
        elif result.answer is not None:
            outcome = f"Итог: {render_answer(result.answer, lang)} (статус {result.status})."
        else:
            outcome = f"Итог: ответа нет (статус {result.status})."
        return f"Задача: {task} {route} {outcome}"
    route = f"Track: {result.track}, procedure: {procedure}, stages run: {len(stages)}."
    if result.refusal:
        outcome = f"Outcome: out of fragment ({result.refusal})."
    elif result.answer is not None:
        outcome = f"Outcome: {render_answer(result.answer, lang)} (status {result.status})."
    else:
        outcome = f"Outcome: no answer (status {result.status})."
    return f"Task: {task} {route} {outcome}"


def summarize(
    text: str,
    result: SolveResult,
    log: StageLog,
    *,
    lang: str,
    llm: Any = None,
) -> str:
    """Closing report from one more LLM call, or a deterministic fallback on failure."""
    log.stage("Summary")
    summary = ""
    if llm is None:
        log.field("summary error", "no LLM available")
    else:
        messages = [
            SystemMessage(content=SUMMARY_SYSTEM),
            HumanMessage(content=_summary_prompt(text, result, log.stages, lang)),
        ]
        try:
            summary = _call_summary(llm, messages)
        except Exception as exc:
            log.field("summary error", f"{type(exc).__name__}: {exc}")
            summary = ""
    if summary:
        result.summary_source = "llm"
    else:
        summary = _fallback_summary(text, result, log.stages, lang)
        result.summary_source = "fallback"
    result.summary = summary
    log.field("summary source", result.summary_source)
    log.block("summary", summary)
    return summary


def run_task(
    text: str,
    *,
    track: str = "theory",
    lang: str | None = None,
    llm: Any = None,
    narration_llm: Any = None,
    propose_llm: Any = None,
    narrate: bool = True,
    world_assumption: str | None = None,
    max_waves: int | None = None,
    log: StageLog | None = None,
) -> SolveResult:
    """Run one problem text through the whole pipeline and log every stage."""
    if track not in TRACKS:
        raise ValueError(f"unknown track {track!r}; expected one of {', '.join(TRACKS)}")
    log = log or StageLog()
    language = lang or str(get_setting("LANG", "en"))
    result = SolveResult(track=track, status="")

    log.stage("Input")
    log.field("track", track)
    log.field("language", language)
    log.field("chars", len(text))
    log.block("text", text)

    created = llm is None
    if created:
        from ankyra.llm.client import create_chat_llm

        log.field("provider", get_setting("LLM_PROVIDER", "openai"))
        log.field("model", get_setting("MODEL"))
        llm = create_chat_llm(role="extract")
        if narrate and narration_llm is None:
            narration_llm = create_chat_llm(role="answer")
    if narration_llm is not None:
        summary_llm = narration_llm
    elif created:
        summary_llm = create_chat_llm(role="answer")
    else:
        summary_llm = llm
    if not narrate:
        narration_llm = None
    proposer = propose_llm or (llm if not created else create_chat_llm(role="answer"))

    if track == "csp":
        result = run_csp(text, llm, log, result)
    elif track == "numeric":
        result = run_numeric(text, llm, log, result)
    else:
        result = run_theory(
            text,
            llm,
            log,
            result,
            proposer=proposer,
            world_assumption=world_assumption,
            max_waves=max_waves,
        )
    result = _finish(result, log, lang=language, narration_llm=narration_llm)
    summarize(text, result, log, lang=language, llm=summary_llm)
    return result


def _read_text(args: argparse.Namespace) -> str:
    if args.file is not None:
        return args.file.read_text(encoding="utf-8").strip()
    if args.text:
        return " ".join(args.text).strip()
    return sys.stdin.read().strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ankyra.cli.solve",
        description="Run one problem through the pipeline and print a Prolog-style report.",
    )
    parser.add_argument("text", nargs="*", help="problem text; stdin is read when omitted")
    parser.add_argument("--file", type=argparse.FileType("r", encoding="utf-8"), default=None)
    parser.add_argument("--track", choices=TRACKS, default="theory")
    parser.add_argument("--lang", default=None, help="language of the problem (default ANKYRA_LANG)")
    parser.add_argument(
        "--world-assumption", choices=("open", "closed"), default=None, help="ANKYRA_NEGATION_MODE"
    )
    parser.add_argument("--no-narrate", action="store_true", help="skip the LLM paraphrase")
    parser.add_argument(
        "--max-waves",
        type=int,
        default=None,
        help="maximum guided-cycle waves (default ANKYRA_MAX_WAVES)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        "--log",
        dest="verbose",
        action="store_true",
        help="also print the raw model answers and intermediate JSON dumps",
    )
    parser.add_argument("--out", type=argparse.FileType("w", encoding="utf-8"), default=sys.stdout)
    args = parser.parse_args(argv)

    text = _read_text(args)
    if not text:
        parser.error("no problem text: pass it as an argument, --file, or on stdin")
    log = StageLog(out=args.out, verbose=args.verbose, live=True)
    result = run_task(
        text,
        track=args.track,
        lang=args.lang,
        narrate=not args.no_narrate,
        world_assumption=args.world_assumption,
        max_waves=args.max_waves,
        log=log,
    )
    log.flush()
    _print_report(result, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
