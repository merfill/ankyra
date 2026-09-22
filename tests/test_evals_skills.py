"""Per-collection skills: loader, composition, and harness wiring (offline)."""

from __future__ import annotations

import hashlib
import inspect

from evals import ar_lsat, folio
from evals.skills import Skill, compose, load_skill, skill_block

# Checksums of the injected guide text, locking it against accidental edits. Changing a
# guide's wording is a deliberate, budgeted decision (docs/task.md §0.6); update the
# checksum in the same commit that changes the text.
_COMMITTED = {
    "ar_lsat": "536265b3cab3eb30e066a389d652d20fb3d983bcd16ad030c0e340c4afd98bf2",
    "folio": "a49eb1ed5d57868d219331b429b8d508f42e91da8a1d9fd00ebb0651fafe7703",
}


def test_compose_joins_non_empty_sections_with_one_blank_line():
    assert compose("a", "", "b") == "a\n\nb"
    assert compose("", "") == ""


def test_compose_strips_outer_newlines_but_keeps_internal_blank_lines():
    assert compose("\na\n\nb\n") == "a\n\nb"


def test_unknown_collection_is_empty():
    assert skill_block("not_a_collection") == ""
    assert skill_block("") == ""
    assert load_skill("not_a_collection") == Skill("not_a_collection", "", "")


def test_loader_takes_only_a_collection_name():
    # The no-per-id-tuning guarantee is structural: no record/example can be passed in.
    params = list(inspect.signature(load_skill).parameters)
    assert params == ["collection"]


def test_committed_skills_compose_language_then_task():
    for collection in _COMMITTED:
        skill = load_skill(collection)
        assert skill.language and skill.task
        assert skill.block == compose(skill.language, skill.task)


def test_committed_guide_text_is_locked():
    for collection, digest in _COMMITTED.items():
        actual = hashlib.sha256(skill_block(collection).encode("utf-8")).hexdigest()
        assert actual == digest, collection


def test_harnesses_auto_load_their_own_collection():
    assert ar_lsat.COLLECTION == "ar_lsat"
    assert folio.COLLECTION == "folio"
    assert skill_block(ar_lsat.COLLECTION)
    assert skill_block(folio.COLLECTION)


def test_run_problem_dict_carries_the_composed_skill():
    record = folio.load_sample()[0]
    problem = folio._to_problem(record, allow_hypotheses=False)
    assert problem["language_spec"] == skill_block(folio.COLLECTION)


def test_skill_block_is_injectable_as_language_spec():
    from ankyra.config.settings import setting_overrides
    from ankyra.build.extract import language_spec_block

    with setting_overrides(LANGUAGE_SPEC=skill_block("ar_lsat")):
        block = language_spec_block()
    assert "ADDITIONAL LANGUAGE SPECIFICATION" in block
    assert "Reading the game" in block
    assert "Reading the options" in block
