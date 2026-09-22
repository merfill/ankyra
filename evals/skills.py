"""Per-collection skills: declarative language and task guidance for Phase 0.

A *skill* packages, for one benchmark collection, two text blocks:

* ``language`` — how to read the collection's source notation (grammar, idioms);
* ``task`` — the collection's task specifics (question shapes, option formats, and
  what the harness declares).

Both are **declarative guidance**, never answer keys or per-example content
(``docs/task.md`` §3.8). ``load_skill`` takes only a collection name, never a record,
so per-id tuning is structurally impossible. The composed block flows through the
existing ``ANKYRA_LANGUAGE_SPEC`` seam
(``ankyra.build.extract.language_spec_block``); the engine stays collection-agnostic.

Layout::

    evals/skills/<collection>/language.md
    evals/skills/<collection>/task.md

A missing file or collection yields an empty section, so an unknown collection
composes to ``""`` and the prompts stay byte-identical. See ``docs/task.md`` §0.6.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parent / "skills"

LANGUAGE_FILE = "language.md"
TASK_FILE = "task.md"


@dataclass(frozen=True)
class Skill:
    """The sections of one collection's skill, in injection order."""

    collection: str
    language: str
    task: str

    @property
    def block(self) -> str:
        """The composed guide, joining non-empty sections with one blank line."""
        return compose(self.language, self.task)


def compose(*sections: str) -> str:
    """Join non-empty sections with one blank line, preserving order.

    Leading and trailing newlines are stripped from each section (the surrounding
    ``LANGUAGE_SPEC`` wrapper adds its own spacing), while internal blank lines are
    kept, so a recomposed skill is byte-identical to the single guide it replaced.
    """
    return "\n\n".join(
        section for section in (s.strip("\n") for s in sections) if section
    )


def _read(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip("\n")


def load_skill(collection: str) -> Skill:
    """Load a collection's skill; unknown collections and missing files are empty."""
    root = SKILLS_ROOT / collection
    return Skill(
        collection=collection,
        language=_read(root / LANGUAGE_FILE),
        task=_read(root / TASK_FILE),
    )


def skill_block(collection: str) -> str:
    """The composed skill text for ``collection``; ``""`` when the skill is absent."""
    return load_skill(collection).block
