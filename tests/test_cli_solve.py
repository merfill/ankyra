"""Offline tests for the single-task CLI runner (canned model responses, no network)."""

from __future__ import annotations

import io
import json

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from ankyra.cli import solve
from ankyra.config.settings import setting_overrides

RAIN = "It is raining. If it is raining, the ground is wet. Is the ground wet?"

RAIN_PROBLEM = {
    "objects": [{"id": "ground"}],
    "facts": [{"predicate": "raining", "quote": "it is raining"}],
    "rules": [
        {
            "antecedent": [{"predicate": "raining", "quote": "if it is raining"}],
            "consequent": {"predicate": "is_wet", "object": "ground", "quote": "the ground is wet"},
            "quote": "if it is raining, the ground is wet",
        }
    ],
    "question": "Is the ground wet?",
}

RAIN_QUESTION = {"ask": {"predicate": "is_wet", "object": "ground", "quote": "ground wet"}}

COMPOUND_QUESTION = {
    "ask_all": [
        {"predicate": "is_wet", "object": "ground", "quote": "ground wet"},
        {"predicate": "raining", "quote": "it is raining"},
    ]
}

VEHICLE = "The truck has an engine. Is the truck a vehicle?"

VEHICLE_PROBLEM = {
    "objects": [{"id": "truck"}, {"id": "vehicle"}],
    "facts": [
        {"predicate": "has_engine", "subject": "truck", "quote": "truck has an engine"}
    ],
    "rules": [],
    "question": "Is the truck a vehicle?",
}

VEHICLE_QUESTION = {
    "ask": {
        "predicate": "is_a",
        "subject": "truck",
        "object": "vehicle",
        "quote": "truck a vehicle",
    }
}

VEHICLE_PROPOSAL = {
    "action": "propose_rule",
    "narration": "A thing with an engine is a vehicle.",
    "rule": {
        "conditions": [{"predicate": "has_engine", "subject": "?x"}],
        "consequence": {"predicate": "is_a", "subject": "?x", "object": "vehicle"},
        "kind": "implication",
    },
}

SEAT_GAME = {
    "domains": [{"id": "seat", "values": ["0", "1", "2"], "topology": "linear"}],
    "variables": [{"id": "A", "domain": "seat"}, {"id": "B", "domain": "seat"}],
    "constraints": [
        {"kind": "all_different", "variables": ["A", "B"], "quote": "A and B sit apart"},
        {"kind": "eq", "variables": ["A"], "values": ["0"], "quote": "A sits first"},
    ],
}

SEAT_QUESTION = {
    "kind": "not_violate",
    "options": [
        {
            "constraints": [
                {"kind": "eq", "variables": ["A"], "values": ["0"]},
                {"kind": "eq", "variables": ["B"], "values": ["1"]},
            ]
        },
        {
            "constraints": [
                {"kind": "eq", "variables": ["A"], "values": ["1"]},
                {"kind": "eq", "variables": ["B"], "values": ["2"]},
            ]
        },
    ],
}

PERCENT = "A shirt costs $80. It is on sale for 25% off. What is the sale price?"

PERCENT_GAME = {
    "quantities": [
        {"id": "list", "quote": "costs $80"},
        {"id": "discount", "quote": "25% off"},
        {"id": "sale", "quote": "sale for 25% off"},
    ],
    "equations": [
        {
            "lhs": {"op": "quantity", "quantity": "list"},
            "rhs": {"op": "const", "value": "80"},
            "quote": "costs $80",
        },
        {
            "lhs": {"op": "quantity", "quantity": "discount"},
            "rhs": {
                "op": "mul",
                "args": [
                    {"op": "quantity", "quantity": "list"},
                    {
                        "op": "div",
                        "args": [
                            {"op": "const", "value": "25"},
                            {"op": "const", "value": "100"},
                        ],
                    },
                ],
            },
            "quote": "25% off",
        },
        {
            "lhs": {"op": "quantity", "quantity": "sale"},
            "rhs": {
                "op": "sub",
                "args": [
                    {"op": "quantity", "quantity": "list"},
                    {"op": "quantity", "quantity": "discount"},
                ],
            },
            "quote": "sale for 25% off",
        },
    ],
}

PERCENT_QUERY = {"target": "sale"}


class FakeModel(BaseChatModel):
    """Canned responses keyed by the extraction schema title in the prompt."""

    responses: dict[str, dict] = {}
    summary: str = ""

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        prompt = "\n".join(str(getattr(message, "content", "")) for message in messages)
        if self.summary and "closing report" in prompt:
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content=self.summary))]
            )
        for title, payload in self.responses.items():
            if f'"title": "{title}"' in prompt:
                return ChatResult(
                    generations=[
                        ChatGeneration(message=AIMessage(content=json.dumps(payload)))
                    ]
                )
        raise AssertionError(f"no canned response for prompt tail: {prompt[-300:]}")


def _run(text: str, responses: dict[str, dict], **kwargs):
    """Run the pipeline and return the result plus what ``--verbose`` would print."""
    out = io.StringIO()
    summary = kwargs.pop("summary", "")
    log = solve.StageLog(out=out, verbose=kwargs.pop("verbose", True))
    result = solve.run_task(
        text, llm=FakeModel(responses=responses, summary=summary), log=log, **kwargs
    )
    log.flush()
    return result, out.getvalue()


@pytest.fixture(autouse=True)
def _single_sample():
    with setting_overrides(EXTRACT_SAMPLES=1, EXTRACT_REPAIRS=0):
        yield


def test_theory_track_logs_every_stage_and_answers_yes():
    result, output = _run(RAIN, {"ProblemStructure": RAIN_PROBLEM, "QuestionStructure": RAIN_QUESTION})

    assert result.status == "supported"
    assert result.answer is not None and result.answer.kind == "yes"
    assert "Answer: Yes" in result.final_text

    for marker in (
        "=== ЭТАП 1: Input ===",
        "=== ЭТАП 2: Extract the problem structure (Phase 0) ===",
        "=== ЭТАП 3: Build the theory ===",
        "=== ЭТАП 4: Extract the question structure (Phase 0) ===",
        "=== ЭТАП 5: Build the query ===",
        "=== ЭТАП 6: Route the problem (analyze_routing) ===",
        "=== ЭТАП 7: Solve (procedure: horn) ===",
        "=== ЭТАП 8: Assemble the answer and the proof ===",
        "=== ЭТАП 9: Final answer ===",
        "=== ЭТАП 10: Summary ===",
    ):
        assert marker in output
    assert "entry point: ankyra.engine.verify.verify" in output
    assert '"predicate": "is_wet"' in output  # the built theory is dumped
    assert "LLM extract_problem" in output  # the raw model answer is logged
    assert "status: supported" in output
    assert result.summary  # the run ends with a report, never a bare dump
    assert "summary source: fallback" in output  # the fake model has no report


def test_verbose_mode_can_hide_model_dumps_but_keeps_stage_headers():
    result, output = _run(
        RAIN,
        {"ProblemStructure": RAIN_PROBLEM, "QuestionStructure": RAIN_QUESTION},
        verbose=False,
    )

    assert result.status == "supported"
    assert "=== ЭТАП 7: Solve (procedure: horn) ===" in output
    assert '"predicate": "is_wet"' not in output


def test_compact_stage_results_are_visible_without_verbose():
    result, output = _run(
        RAIN,
        {"ProblemStructure": RAIN_PROBLEM, "QuestionStructure": RAIN_QUESTION},
        verbose=False,
    )

    assert "facts (1):" in output
    assert "  raining" in output
    assert "theory (Prolog):" in output
    assert "факт: raining. [quote]" in output
    assert "правило: is_wet(ground) :- raining. [quote]" in output
    assert "question (Prolog):" in output
    assert "ask: is_wet(ground)" in output
    assert "query (Prolog):" in output
    assert "⊢ выведено: is_wet(ground)" in output
    assert "proof (mechanical):" in output
    assert '"predicate": "is_wet"' not in output  # the raw JSON dump stays verbose-only


def test_horn_track_streams_the_guided_cycle_wave():
    result, output = _run(
        VEHICLE,
        {
            "ProblemStructure": VEHICLE_PROBLEM,
            "QuestionStructure": VEHICLE_QUESTION,
            "ProposalDraft": VEHICLE_PROPOSAL,
        },
    )

    assert result.status == "supported"
    assert result.answer is not None
    assert result.answer.strength == "proven_under"
    assert result.answer.hypotheses_used == ["H1"]

    assert "── волна 1 ──" in output
    assert "предложено: propose_rule" in output
    assert "классификация: hypothesis (hypothesis:H1)" in output
    assert "+ правило: is_a(?x, vehicle) :- has_engine(?x). [H1]" in output
    assert "⊢ выведено: is_a(truck,vehicle)" in output
    assert "ревизия: волна 1:" in output
    assert len(result.waves) == 1

    report = "\n".join(solve._report_lines(result))
    assert "факт:    has_engine(truck). [quote]" in report
    assert "правило: is_a(?x, vehicle) :- has_engine(?x). [H1]" in report


def test_live_log_streams_before_flush():
    out = io.StringIO()
    log = solve.StageLog(out=out, live=True)

    log.stage("One")
    log.write("streamed")
    assert "=== ЭТАП 1: One ===" in out.getvalue()
    assert "streamed" in out.getvalue()

    log.flush()
    assert out.getvalue().count("streamed") == 1


def test_out_of_fragment_is_reported_without_a_fallback(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("verify must not run after a refusal")

    monkeypatch.setattr(solve, "verify", boom)
    result, output = _run(
        RAIN, {"ProblemStructure": RAIN_PROBLEM, "QuestionStructure": COMPOUND_QUESTION}
    )

    assert result.status == "out_of_fragment"
    assert result.refusal == "out_of_fragment:compound_goal"
    assert "out of fragment: out_of_fragment:compound_goal" in result.final_text.lower()
    assert "refusal: out_of_fragment:compound_goal" in output


def test_csp_track_decides_through_the_csp_entry_point():
    with setting_overrides(CSP=True):
        result, output = _run(
            "A and B sit in a row. A sits first.",
            {"CspGameStructure": SEAT_GAME, "CspQuestionStructure": SEAT_QUESTION},
            track="csp",
        )

    assert result.status == "decided"
    assert result.answer is not None and result.answer.value == "0"
    assert "entry point: ankyra.engine.csp.decide.decide" in output
    assert "=== ЭТАП 7: Solve (procedure: csp) ===" in output


def test_csp_track_refuses_when_the_capability_is_off():
    with setting_overrides(CSP=False):
        result, _ = _run(
            "A and B sit in a row.",
            {"CspGameStructure": SEAT_GAME, "CspQuestionStructure": SEAT_QUESTION},
            track="csp",
        )

    assert result.status == "out_of_fragment"
    assert result.refusal == "out_of_fragment:csp_off"


def test_numeric_track_decides_through_the_numeric_entry_point():
    with setting_overrides(ARITH=True):
        result, output = _run(
            PERCENT,
            {"NumericGameStructure": PERCENT_GAME, "NumericQueryStructure": PERCENT_QUERY},
            track="numeric",
        )

    assert result.status == "determined"
    assert result.answer is not None and result.answer.value == "60"
    assert "entry point: ankyra.engine.numeric.decide.decide" in output


def test_main_reads_stdin_and_prints_the_three_sections(monkeypatch, capsys):
    fake = FakeModel(
        responses={"ProblemStructure": RAIN_PROBLEM, "QuestionStructure": RAIN_QUESTION},
        summary="The run derived the answer.",
    )
    monkeypatch.setattr("ankyra.llm.client.create_chat_llm", lambda **kwargs: fake)
    monkeypatch.setattr("sys.stdin", io.StringIO(RAIN))

    code = solve.main(["--no-narrate"])

    output = capsys.readouterr().out
    assert code == 0
    assert "=== ЭТАП 1: Input ===" in output  # stages stream live by default
    assert '"predicate": "is_wet"' not in output  # raw dumps stay behind --verbose
    assert "ТЕОРИЯ" in output
    assert "ВЫВОД" in output
    assert "ЗАКЛЮЧЕНИЕ" in output
    assert "факт:    raining." in output
    assert "правило: is_wet(ground) :- raining." in output
    assert "вопрос:  is_wet(ground)." in output
    assert "  шаг 1:" in output
    assert fake.summary in output


def test_main_prints_the_full_dump_under_verbose(monkeypatch, capsys):
    fake = FakeModel(
        responses={"ProblemStructure": RAIN_PROBLEM, "QuestionStructure": RAIN_QUESTION},
        summary="The run derived the answer.",
    )
    monkeypatch.setattr("ankyra.llm.client.create_chat_llm", lambda **kwargs: fake)
    monkeypatch.setattr("sys.stdin", io.StringIO(RAIN))

    code = solve.main(["--verbose", "--no-narrate"])

    output = capsys.readouterr().out
    assert code == 0
    assert "=== ЭТАП 1: Input ===" in output
    assert '"predicate": "is_wet"' in output
    assert "ТЕОРИЯ" in output
    assert "правило: is_wet(ground) :- raining." in output
    assert "ЗАКЛЮЧЕНИЕ" in output
    assert fake.summary in output


def test_main_falls_back_to_a_deterministic_summary_without_the_llm(monkeypatch, capsys):
    fake = FakeModel(responses={"ProblemStructure": RAIN_PROBLEM, "QuestionStructure": RAIN_QUESTION})
    monkeypatch.setattr("ankyra.llm.client.create_chat_llm", lambda **kwargs: fake)
    monkeypatch.setattr("sys.stdin", io.StringIO(RAIN))

    code = solve.main(["--no-narrate", "--lang", "ru"])

    output = capsys.readouterr().out
    assert code == 0
    assert "ЗАКЛЮЧЕНИЕ" in output
    assert "Задача:" in output
    assert "процедура: horn" in output
    assert "Ответ: Да" in output


def test_summary_error_stays_in_the_verbose_log(monkeypatch):
    fake = FakeModel(responses={"ProblemStructure": RAIN_PROBLEM, "QuestionStructure": RAIN_QUESTION})
    monkeypatch.setattr("ankyra.llm.client.create_chat_llm", lambda **kwargs: fake)

    out = io.StringIO()
    log = solve.StageLog(out=out, verbose=True)
    result = solve.run_task(RAIN, narrate=False, log=log)
    log.flush()

    assert result.summary_source == "fallback"
    assert "summary error: AssertionError" in out.getvalue()


class FakeNarrator(BaseChatModel):
    """Answers the prose request with a fixed sentence in the problem's language."""

    summary: str = ""

    @property
    def _llm_type(self) -> str:
        return "fake-narrator"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        prompt = "\n".join(str(getattr(message, "content", "")) for message in messages)
        content = self.summary if self.summary and "closing report" in prompt else "Да: земля мокрая."
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])


def test_narration_replaces_the_final_answer_with_prose():
    out = io.StringIO()
    log = solve.StageLog(out=out, verbose=True)
    result = solve.run_task(
        RAIN,
        llm=FakeModel(responses={"ProblemStructure": RAIN_PROBLEM, "QuestionStructure": RAIN_QUESTION}),
        narration_llm=FakeNarrator(summary="Отчёт о прогоне."),
        lang="ru",
        log=log,
    )
    log.flush()

    assert result.status == "supported"
    assert result.final_text == "Да: земля мокрая."
    assert "direct answer: Ответ: Да" in out.getvalue()
    assert result.summary == "Отчёт о прогоне."
    assert result.summary_source == "llm"
