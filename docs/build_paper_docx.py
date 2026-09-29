#!/usr/bin/env python3
"""Build a journal-formatted DOCX (AIDM style) from the Ankyra working papers.

The two LaTeX sources (``ankyra_paper.tex`` and ``ankyra_paper_ru.tex``) are
parsed with pandoc (LaTeX -> JSON AST) and reassembled into a single Word
document that follows the journal layout: Russian version first, English version
second.  Everything that is journal-specific (fonts, spacing, margins, numbered
sections, numbered tables with captions, in-text table references, a short
100-120 word abstract, affiliation placeholders, "About author(s)") is produced
here, so the working-paper sources stay untouched.

Run with::

    uv run --with python-docx python docs/build_paper_docx.py

Requires the ``pandoc`` binary on PATH.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

DOCS = Path(__file__).resolve().parent
EN_SRC = DOCS / "ankyra_paper.tex"
RU_SRC = DOCS / "ankyra_paper_ru.tex"
OUT = DOCS / "ankyra_paper_journal.docx"

FONT = "Times New Roman"
MONO = "Courier New"
BODY_PT = 11
TITLE_PT = 12
SMALL_PT = 10

# --------------------------------------------------------------------------
# Journal metadata (author data are explicit placeholders).
# --------------------------------------------------------------------------

META = {
    "ru": {
        "title": "Ankyra: корректное нейросимволическое рассуждение "
                 "с проверяемым выводом",
        "authors": "В.А. Лапшин",
        "affiliation": "Индивидуальный исследователь, Москва, Россия",
        "correspondence": "Ответственный за переписку: Лапшин Владимир "
                          "Анатольевич. E-mail: merfill@yandex.ru",
        "abstract_label": "Аннотация.",
        "abstract": (
            "Представлена Ankyra — нейросимволическая система рассуждений, не "
            "зависящая от предметной области. Языковая модель предлагает "
            "формализацию задачи, а детерминированный символический решатель "
            "принимает решение. Система охватывает семейство разрешимых "
            "формализмов: от определённых хорновских клауз и стратифицированного "
            "отрицания до позитивной логики первого порядка с дизъюнкцией и "
            "кванторами, конечно-доменных ограничений, точной арифметики и "
            "умолчаний со специфичностью. Каждый ответ сопровождается "
            "проверяемой историей вывода, и ни одно утверждение не входит в "
            "теорию без дословной цитаты или явной пометки гипотезы. Приведена "
            "демонстрационная оценка на стандартных коллекциях: на охваченных "
            "срезах система точна и не допускает уверенно неверных выводов, "
            "честно воздерживаясь там, где реализованная логика не выражает "
            "задачу. Сравнение с Logic-LM и LINC на одинаковых входах "
            "показывает, что при малой модели узким местом становится "
            "интерфейс перевода, а не рассуждение."
        ),
        "keywords_label": "Ключевые слова:",
        "keywords": "нейросимволические рассуждения, автоматическое "
                    "доказательство, проверяемый вывод, языковые модели, "
                    "формализация, хорновские клаузы, логика первого порядка, "
                    "конечно-доменные ограничения, точная арифметика, умолчания",
        "bibliography_heading": "Литература",
        "about_heading": "Об авторе(ах)",
        "about": [
            "Лапшин Владимир Анатольевич. Кандидат физико-математических "
            "наук. Индивидуальный исследователь, Москва, Россия. Области "
            "исследований: нейросимволические рассуждения, автоматическое "
            "доказательство, проверяемый вывод, языковые модели. E-mail: "
            "merfill@yandex.ru. (ответственный за переписку)"
        ],
        "appendix_label": "Приложение",
    },
    "en": {
        "title": "Ankyra: Sound Neuro-Symbolic Reasoning with Verifiable Proofs",
        "authors": "V.A. Lapshin",
        "affiliation": "Independent Researcher, Moscow, Russia",
        "correspondence": None,
        "abstract_label": "Abstract.",
        "abstract": (
            "We present Ankyra, a domain-general neuro-symbolic reasoning system "
            "in which the language model proposes a formalization and a "
            "deterministic symbolic engine decides it. The system spans a family "
            "of decidable formalisms, from definite Horn clauses and stratified "
            "negation to first-order logic with disjunction and quantifiers, "
            "finite-domain constraints, exact arithmetic, and defeasible "
            "defaults. Every answer carries a machine-checkable proof trace, and "
            "no statement enters the theory without a verbatim quotation or an "
            "explicit hypothesis tag. A demonstration-scale evaluation shows "
            "high accuracy on covered slices, no "
            "confidently wrong conclusions, and honest abstention where the "
            "logic cannot express the problem. A common-input comparison with "
            "Logic-LM and LINC shows the binding constraint under a small model "
            "to be the translation interface, not the reasoning."
        ),
        "keywords_label": "Keywords:",
        "keywords": "neuro-symbolic reasoning, automated proof, verifiable "
                    "reasoning, large language models, formalization, Horn "
                    "clauses, first-order logic, finite-domain constraints, "
                    "exact arithmetic, defaults",
        "bibliography_heading": "References",
        "about_heading": "About author(s)",
        "about": [
            "Lapshin Vladimir A. Candidate of Physical and Mathematical "
            "Sciences (Ph.D.). Independent Researcher, Moscow, Russia. "
            "Research areas: neuro-symbolic reasoning, automated proof, "
            "verifiable reasoning, large language models. E-mail: "
            "merfill@yandex.ru. (corresponding author)"
        ],
        "appendix_label": "Appendix",
    },
}

# Table captions, in document order (13 tables in both languages).
TABLE_CAPTIONS = {
    "ru": [
        "Категории утверждений в протоколе предложений",
        "Чистая дедукция: факт, правило и цель",
        "Стадии, формализмы и решающие процедуры",
        "Синтетические проверки без участия языковой модели",
        "Результаты на зафиксированных подвыборках",
        "Протоколы декодирования сравниваемых систем",
        "Сравнение на общем входе: точность решателя по всем строкам",
        "Охват символических решателей на общем входе",
        "Проверка символических решателей на эталонном входе (FOLIO)",
        "Причины отказов сохранённых программ Logic-LM",
        "Чувствительность к модели на наборе ProofWriter",
        "Признаки фрагмента и условия их возникновения",
        "Переключатели запуска и их действие",
    ],
    "en": [
        "Statement categories of the proposal protocol",
        "Pure deduction: fact, rule, and goal",
        "Stages, formalisms, and decision procedures",
        "Synthetic checks without a language model",
        "Results on fixed subsamples",
        "Decoding protocols of the compared systems",
        "Common-input comparison: solver accuracy over all rows",
        "Coverage of the symbolic back-ends under common input",
        "Gold-fed check of the symbolic back-ends (FOLIO)",
        "Failure modes of Logic-LM's saved programs",
        "Model sensitivity on the ProofWriter set",
        "Fragment features and when they arise",
        "Switches available to a run",
    ],
}

# Bibliography, formatted after GOST R 7.0.5-2008 (the sample's style).  The
# Russian list gives Russian-language works in Cyrillic; the English list gives
# the same sources, transliterating Russian ones.  Numbering follows the
# \bibitem order of the LaTeX sources, so in-text citation numbers are stable.
ACCESS = "29.09.2026"
GOST_COMMON = {
    "logiclm": "Pan L. et al. Logic-LM: Empowering Large Language Models with "
               "Symbolic Solvers for Faithful Logical Reasoning // Findings of "
               "the Association for Computational Linguistics: EMNLP 2023. "
               "2023.",
    "linc": "Olausson T.X. et al. LINC: A Neurosymbolic Approach for Logical "
            "Reasoning by Combining Language Models with First-Order Logic "
            "Provers // Proceedings of the 2023 Conference on Empirical "
            "Methods in Natural Language Processing. 2023.",
    "survey2026": "Bin Hakim S., Adil M., Velasquez A., Song H.H. "
                  "Neuro-symbolic agentic AI: Architectures, integration "
                  "patterns, applications, open challenges and future "
                  "research directions // Computer Science Review. 2026. "
                  "Vol. 60. Art. 100902. DOI: 10.1016/j.cosrev.2026.100902.",
    "ata": "Peer D., Stabinger S. ATA: Autonomous Trustworthy Agents // "
           "arXiv. 2025. arXiv:2510.16381.",
    "nsc": "Hsia Y.-S., Yu F., Jiang J.-H.R. Neuro-Symbolic Compliance: "
           "LLM-driven SMT Verification of Regulatory Documents // arXiv. "
           "2026. arXiv:2601.06181.",
    "cot": "Wei J. et al. Chain-of-Thought Prompting Elicits Reasoning in "
           "Large Language Models // Advances in Neural Information "
           "Processing Systems. 2022. arXiv:2201.11903.",
    "selfconsistency": "Wang X. et al. Self-Consistency Improves Chain of "
                       "Thought Reasoning in Language Models // "
                       "International Conference on Learning "
                       "Representations. 2023. arXiv:2203.11171.",
    "proofwriter": "Tafjord O., Mishra B.D., Clark P. ProofWriter: "
                   "Generating Implications, Proofs, and Abductive "
                   "Statements over Natural Language // arXiv. 2020. "
                   "arXiv:2012.13048.",
    "prontoqa": "Saparov A., He H. Language Models Are Greedy Reasoners: A "
                "Systematic Formal Analysis of Chain-of-Thought // "
                "International Conference on Learning Representations. 2023. "
                "arXiv:2210.01240.",
    "prontoqaood": "Saparov A., He H. Testing the General Deductive Reasoning "
                   "Capacity of Large Language Models Using OOD Examples // "
                   "Advances in Neural Information Processing Systems. 2023. "
                   "arXiv:2305.15269.",
    "folio": "Han S. et al. FOLIO: Natural Language Reasoning with "
             "First-Order Logic // arXiv. 2024. arXiv:2209.00840.",
    "arlsat": "Zhong W. et al. AR-LSAT: Investigating Analytical Reasoning of "
              "Text // arXiv. 2021. arXiv:2104.06598.",
    "gsm8k": "Cobbe K. et al. Training Verifiers to Solve Math Word "
             "Problems // arXiv. 2021. arXiv:2110.14168.",
    "reiter": "Reiter R. A Logic for Default Reasoning // Artificial "
              "Intelligence. 1980. Vol. 13, No. 1\u20132. P. 81\u2013132.",
    "mccarthy": "McCarthy J. Circumscription \u2014 A Form of Non-Monotonic "
                "Reasoning // Artificial Intelligence. 1980. Vol. 13, "
                "No. 1\u20132. P. 27\u201339.",
}
GOST_OVERRIDES = {
    "ankyra": {
        "ru": "Ankyra: A domain-agnostic neuro-symbolic reasoning engine // "
              "Электронный ресурс. URL: https://github.com/merfill/ankyra "
              f"(дата обращения: {ACCESS}).",
        "en": "Ankyra: A domain-agnostic neuro-symbolic reasoning engine // "
              "Electronic resource. URL: https://github.com/merfill/ankyra "
              f"(accessed {ACCESS}).",
    },
    "doxa": {
        "ru": "Лапшин В.А. Докса и логос: операторная модель "
              "взаимодействия языковой модели и формальной системы. "
              "(В подготовке).",
        "en": "Lapshin V.A. Doksa i logos: operatornaya model\u2019 "
              "vzaimodeystviya yazykovoy modeli i formal\u2019noy sistemy "
              "[Doxa and Logos: An Operator Model of the Interaction between "
              "a Language Model and a Formal System]. (In preparation).",
    },
}
GOST_BIB = {key: {"ru": txt, "en": txt} for key, txt in GOST_COMMON.items()}
GOST_BIB.update(GOST_OVERRIDES)

TABLE_REF = {"ru": "Табл.", "en": "Table"}
# Tables already referenced in the running text (by their 1-based number).
PREREFERENCED = {5, 7, 8}

UNNUMBERED_TITLES = {
    "introduction", "введение",
    "conclusion", "заключение",
}

# --------------------------------------------------------------------------
# LaTeX helpers.
# --------------------------------------------------------------------------

MATH_CMD = {
    "Rightarrow": "⇒", "rightarrow": "→", "to": "→", "longrightarrow": "→",
    "Leftarrow": "⇐", "leftarrow": "←", "leftrightarrow": "↔",
    "neg": "¬", "lnot": "¬", "lor": "∨", "vee": "∨", "land": "∧", "wedge": "∧",
    "phi": "ϕ", "varphi": "φ", "Gamma": "Γ", "Delta": "Δ",
    "exists": "∃", "forall": "∀", "neq": "≠", "ne": "≠",
    "approx": "≈", "sim": "∼", "equiv": "≡", "times": "×", "cdot": "·",
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥",
    "dots": "…", "ldots": "…", "cdots": "⋯",
    "ast": "*", "star": "*", "pm": "±", "in": "∈", "subset": "⊂",
    "cup": "∪", "cap": "∩", "emptyset": "∅", "alpha": "α", "beta": "β",
    "lambda": "λ", "mu": "μ", "pi": "π", "sigma": "σ", "tau": "τ", "omega": "ω",
    "quad": " ", "qquad": "  ", ", ": " ", " ": " ", ";": " ",
}

SUBSCRIPT = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₋₊₌₍₎")
SUPERSCRIPT = str.maketrans("0123456789+-=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾")


def _map_chars(text: str, table) -> str:
    return "".join(chr(table.get(ord(ch), ord(ch))) for ch in text)


def math_to_text(expr: str) -> str:
    """Render the simple inline maths used in the papers as Unicode text.

    The result is later re-parsed by pandoc's LaTeX reader, so characters that
    are special in LaTeX (%, &, #, _, {, }) are kept escaped.
    """
    protected = (("\\%", "\x00PCT\x00"), ("\\&", "\x00AMP\x00"),
                 ("\\#", "\x00HASH\x00"), ("\\_", "\x00UND\x00"),
                 ("\\{", "\x00LB\x00"), ("\\}", "\x00RB\x00"))
    for lit, token in protected:
        expr = expr.replace(lit, token)
    # Command replacement (longest first so ``\to`` does not eat ``\top``).
    for name in sorted(MATH_CMD, key=len, reverse=True):
        expr = re.sub(r"\\" + re.escape(name) + r"(?![A-Za-z])",
                      lambda _m, r=MATH_CMD[name]: r, expr)
    expr = expr.replace("{,}", ",")
    expr = re.sub(r"_\{([^{}]*)\}", lambda m: _map_chars(m.group(1), SUBSCRIPT), expr)
    expr = re.sub(r"_([0-9A-Za-z])", lambda m: _map_chars(m.group(1), SUBSCRIPT), expr)
    expr = re.sub(r"\^\{([^{}]*)\}",
                  lambda m: _map_chars(math_to_text(m.group(1)), SUPERSCRIPT), expr)
    expr = re.sub(r"\^([0-9A-Za-z])", lambda m: _map_chars(m.group(1), SUPERSCRIPT), expr)
    expr = expr.replace("{", "").replace("}", "")
    for lit, token in protected:
        expr = expr.replace(token, lit)
    return expr


def clean_bib_text(entry: str) -> str:
    entry = " ".join(entry.split())
    entry = re.sub(r"\\url\{([^}]*)\}", r"\1", entry)
    entry = re.sub(r"\\(?:textit|emph|texttt)\{([^{}]*)\}", r"\1", entry)
    entry = entry.replace("---", "—").replace("--", "–")
    entry = entry.replace("~", " ").replace("\\%", "%")
    entry = entry.replace("\\&", "&").replace("\\_", "_")
    entry = entry.replace("{", "").replace("}", "")
    return " ".join(entry.split())


def extract_bibliography(src: str):
    """Return (list of (key, entry), key -> 1-based number)."""
    body = re.search(r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}",
                     src, flags=re.S)
    if not body:
        raise RuntimeError("no thebibliography environment")
    content = body.group(0)
    content = content[:content.rindex(r"\end{thebibliography}")]
    parts = re.split(r"\\bibitem\{([^}]+)\}", content)
    order = []
    for i in range(1, len(parts), 2):
        order.append((parts[i].strip(), clean_bib_text(parts[i + 1])))
    index = {key: n for n, (key, _txt) in enumerate(order, 1)}
    if len(index) != len(order):
        raise RuntimeError("duplicate bibliography keys")
    return order, index


def strip_comments(text: str) -> str:
    out = []
    for line in text.splitlines():
        result, i = [], 0
        while i < len(line):
            if line[i] == "\\" and i + 1 < len(line):
                result.append(line[i:i + 2])
                i += 2
                continue
            if line[i] == "%":
                break
            result.append(line[i])
            i += 1
        out.append("".join(result))
    return "\n".join(out)


def split_document(src: str) -> str:
    start = src.index(r"\begin{document}") + len(r"\begin{document}")
    end = src.index(r"\end{document}")
    body = src[start:end]
    body = re.sub(r"\\maketitle", "", body)
    body = re.sub(r"\\begin\{abstract\}.*?\\end\{abstract\}", "", body,
                  flags=re.S)
    body = re.sub(r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", "",
                  body, flags=re.S)
    return body


def scan_sections(body: str):
    """Return (label -> number, ordered [(level, title, number)])."""
    main, sep, app = body.partition(r"\appendix")
    labelmap: dict[str, str] = {}
    ordered: list[tuple[str, str, str | None]] = []
    pattern = re.compile(
        r"\\(section|subsection)\*?\{([^{}]*)\}(\s*\\label\{([^}]*)\})?")

    def process(text: str, appendix: bool):
        sec = 0
        sub = 0
        apx = 0
        for match in pattern.finditer(text):
            level, title, label = match.group(1), match.group(2), match.group(4)
            title_clean = " ".join(title.split())
            if level == "section":
                sub = 0
                if appendix:
                    apx += 1
                    number = chr(ord("A") + apx - 1)
                elif title_clean.lower() in UNNUMBERED_TITLES:
                    number = None
                else:
                    sec += 1
                    number = str(sec)
            else:
                sub += 1
                if appendix:
                    number = f"{chr(ord('A') + apx - 1)}.{sub}"
                elif sec == 0:
                    number = None
                else:
                    number = f"{sec}.{sub}"
            ordered.append((level, title_clean, number))
            if label:
                labelmap[label] = number if number is not None else ""
        return

    process(main, appendix=False)
    if sep:
        process(app, appendix=True)
    return labelmap, ordered


def scan_tables(body: str):
    """Return (label -> table number, total table count)."""
    starts = [m.start() for m in re.finditer(r"\\begin\{tabular\}", body)]
    labelmap: dict[str, int] = {}
    for m in re.finditer(r"\\label\{(tab:[^}]*)\}", body):
        number = sum(1 for pos in starts if pos < m.start())
        labelmap[m.group(1)] = number
    return labelmap, len(starts)


def _convert_math_segments(text: str) -> str:
    chunks = re.split(r"(\\begin\{verbatim\}.*?\\end\{verbatim\})", text,
                      flags=re.S)
    for i in range(0, len(chunks), 2):
        chunks[i] = re.sub(r"(?<!\\)\$([^$]*?)(?<!\\)\$",
                           lambda m: math_to_text(m.group(1)), chunks[i])
    return "".join(chunks)


def preprocess_text(text: str, bib_index, labelmap, tabmap) -> str:
    text = re.sub(r"\\label\{[^}]*\}", "", text)
    text = re.sub(r"\\paragraph\{([^{}]*)\}", r"\\textbf{\1}", text)

    def cite(match):
        keys = [k.strip() for k in match.group(1).split(",") if k.strip()]
        nums = sorted(bib_index[k] for k in keys)
        parts, i = [], 0
        while i < len(nums):
            j = i
            while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
                j += 1
            if j - i >= 2:
                parts.append(f"{nums[i]}-{nums[j]}")
            else:
                parts.extend(str(nums[k]) for k in range(i, j + 1))
            i = j + 1
        return "[" + ", ".join(parts) + "]"

    text = re.sub(r"\\cite\{([^}]*)\}", cite, text)

    def ref(match):
        key = match.group(1)
        if key in labelmap:
            return labelmap[key]
        if key in tabmap:
            return str(tabmap[key])
        return "?"

    text = re.sub(r"\\ref\{([^}]*)\}", ref, text)
    text = _convert_math_segments(text)
    return text


def run_pandoc(fragment: str):
    wrapped = ("\\documentclass{article}\n\\begin{document}\n"
               + fragment + "\n\\end{document}\n")
    proc = subprocess.run(
        ["pandoc", "-f", "latex", "-t", "json", "--wrap=none"],
        input=wrapped, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        Path("/tmp/opencode/failed_fragment.tex").write_text(wrapped,
                                                             encoding="utf-8")
        raise RuntimeError(f"pandoc failed ({proc.returncode}); fragment saved")
    return json.loads(proc.stdout)["blocks"]


# --------------------------------------------------------------------------
# DOCX rendering.
# --------------------------------------------------------------------------

def set_run(run, *, bold=False, italic=False, mono=False):
    run.font.bold = bold or None
    run.font.italic = italic or None
    if mono:
        run.font.name = MONO
        run.font.size = Pt(SMALL_PT)
        rpr = run._element.get_or_add_rPr()
        rfonts = rpr.get_or_add_rFonts()
        for attr in ("w:ascii", "w:hAnsi", "w:cs"):
            rfonts.set(qn(attr), MONO)


class Builder:
    def __init__(self, doc, lang: str, sections):
        self.doc = doc
        self.lang = lang
        self.sections = sections
        self.sec_i = 0
        self.table_i = 0
        self.last_para = None
        self.prev_was_table = False
        self.previous_block = None

    # -- paragraph helpers -------------------------------------------------
    def new_para(self, *, align=WD_ALIGN_PARAGRAPH.JUSTIFY, indent=0.5,
                 line=1.5, before=0, after=0):
        p = self.doc.add_paragraph()
        pf = p.paragraph_format
        pf.alignment = align
        pf.first_line_indent = Cm(indent)
        pf.left_indent = Cm(0)
        pf.line_spacing = line
        pf.space_before = Pt(before)
        pf.space_after = Pt(after)
        self.last_para = p
        return p

    def add_run(self, p, text, *, bold=False, italic=False, mono=False):
        run = p.add_run(text)
        set_run(run, bold=bold, italic=italic, mono=mono)
        return run

    def render_inlines(self, p, nodes, *, bold=False, italic=False):
        for node in nodes:
            t = node.get("t")
            if t == "Str":
                self.add_run(p, node["c"], bold=bold, italic=italic)
            elif t in ("Space", "SoftBreak"):
                self.add_run(p, " ", bold=bold, italic=italic)
            elif t == "LineBreak":
                self.add_run(p, "").add_break()
            elif t == "Emph":
                self.render_inlines(p, node["c"], bold=bold, italic=True)
            elif t == "Strong":
                self.render_inlines(p, node["c"], bold=True, italic=italic)
            elif t == "Code":
                self.add_run(p, node["c"][1], mono=True)
            elif t == "Math":
                self.add_run(p, math_to_text(node["c"][1]))
            elif t == "Span":
                self.render_inlines(p, node["c"][1], bold=bold, italic=italic)
            elif t == "Quoted":
                open_q, close_q = ("«", "»") if self.lang == "ru" else ("“", "”")
                self.add_run(p, open_q)
                self.render_inlines(p, node["c"][1], bold=bold, italic=italic)
                self.add_run(p, close_q)
            elif t == "Cite":
                self.render_inlines(p, node["c"][1], bold=bold, italic=italic)
            elif t == "Link":
                self.render_inlines(p, node["c"][1], bold=bold, italic=italic)
            elif t == "Note":
                pass
            elif t == "RawInline":
                pass
            elif isinstance(node.get("c"), list):
                self.render_inlines(p, node["c"], bold=bold, italic=italic)

    # -- block helpers -----------------------------------------------------
    def add_blocks(self, blocks, *, in_table=False):
        for block in blocks:
            self.add_block(block)

    def add_block(self, block):
        t = block.get("t")
        if t in ("Para", "Plain"):
            p = self.new_para()
            self.render_inlines(p, block["c"])
        elif t == "Header":
            self.add_header(block)
        elif t == "BulletList":
            self.add_list(block["c"], ordered=False, start=1)
        elif t == "OrderedList":
            attrs, items = block["c"]
            self.add_list(items, ordered=True, start=attrs[0])
        elif t == "CodeBlock":
            self.add_code(block["c"][1])
        elif t == "Table":
            self.add_table(block)
        elif t == "Div":
            self.add_blocks(block["c"][1])
        elif t == "BlockQuote":
            self.add_blocks(block["c"])
        elif t == "HorizontalRule":
            pass
        else:
            if isinstance(block.get("c"), list):
                self.add_blocks(block["c"])
        self.previous_block = t
        if t != "Div":
            self.prev_was_table = (t == "Table")

    def add_header(self, block):
        level = block["c"][0]
        inlines = block["c"][2]
        _, title, number = self.sections[self.sec_i]
        self.sec_i += 1
        p = self.new_para(align=WD_ALIGN_PARAGRAPH.LEFT, indent=0,
                          line=1.5, before=8, after=4)
        label = None
        if number is None:
            label = None
        elif level == 1 and number in ("A", "B", "C", "D", "E"):
            label = f"{META[self.lang]['appendix_label']} {number}."
        elif level == 1:
            label = f"{number}."
        else:
            label = f"{number}."
        if label:
            self.add_run(p, label + " ", bold=True)
        for node in inlines:
            if node.get("t") == "Str":
                self.add_run(p, node["c"], bold=True)
            elif node.get("t") == "Space":
                self.add_run(p, " ", bold=True)
            elif node.get("t") == "Strong":
                self.add_run(p, "".join(x.get("c", "") for x in node["c"]),
                             bold=True)
            elif isinstance(node.get("c"), list):
                self.render_inlines(p, node["c"], bold=True)
            else:
                self.add_run(p, str(node.get("c", "")), bold=True)
        self.last_para = p

    def add_list(self, items, *, ordered, start):
        for n, item in enumerate(items, start):
            first = True
            for block in item:
                if block.get("t") not in ("Para", "Plain"):
                    self.add_block(block)
                    continue
                p = self.new_para(indent=0)
                pf = p.paragraph_format
                pf.left_indent = Cm(0.75)
                pf.first_line_indent = Cm(-0.5)
                if ordered:
                    self.add_run(p, f"{n}.\t")
                else:
                    self.add_run(p, "•\t")
                self.render_inlines(p, block["c"])
                first = False

    def add_code(self, text):
        lines = text.splitlines() or [""]
        for line in lines:
            line = re.sub(r"^ +", "\t", line)
            p = self.new_para(align=WD_ALIGN_PARAGRAPH.LEFT, indent=0,
                              line=1.0, after=0)
            self.add_run(p, line if line else " ", mono=True)

    def add_table_ref(self):
        n = self.table_i
        text = f" ({TABLE_REF[self.lang]} {n})"
        p = self.last_para
        if p is None:
            return
        body = p.text.rstrip()
        if body.endswith((":", "：")):
            for run in reversed(p.runs):
                if run.text.rstrip().endswith((":", "：")):
                    run.text = run.text.rstrip()[:-1] + text + body[-1]
                    break
        else:
            suffix = "" if body.endswith((".", "!", "?", "…")) else "."
            self.add_run(p, text + suffix)

    def add_table(self, block):
        self.table_i += 1
        n = self.table_i
        if n not in PREREFERENCED:
            if self.prev_was_table:
                lead = (f"См. Табл. {n}." if self.lang == "ru"
                        else f"See Table {n}.")
                self.add_run(self.new_para(), lead)
            else:
                self.add_table_ref()
        caption = TABLE_CAPTIONS[self.lang][n - 1]
        cp = self.new_para(align=WD_ALIGN_PARAGRAPH.CENTER, indent=0,
                           line=1.0, before=6, after=2)
        run = self.add_run(cp, f"{TABLE_REF[self.lang]} {n}. {caption}")
        run.font.size = Pt(SMALL_PT)

        c = block["c"]
        colspecs = c[2]
        head_rows = c[3][1]
        body_rows = []
        for body in c[4]:
            body_rows.extend(body[3])
        all_rows = list(head_rows) + body_rows

        columns = len(colspecs)
        table = self.doc.add_table(rows=0, cols=columns)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        self.set_borders(table)
        for r_index, row in enumerate(all_rows):
            cells = row[1]
            cells_out = table.add_row().cells
            for col, cell in enumerate(cells):
                if col >= len(cells_out):
                    break
                self.fill_cell(cells_out[col], cell[4])
        self.last_para = None
        self.prev_was_table = True

    @staticmethod
    def set_borders(table):
        tbl_pr = table._tbl.tblPr
        borders = OxmlElement("w:tblBorders")
        for edge in ("top", "bottom", "insideH"):
            e = OxmlElement(f"w:{edge}")
            e.set(qn("w:val"), "single")
            e.set(qn("w:sz"), "6")
            e.set(qn("w:space"), "0")
            e.set(qn("w:color"), "000000")
            borders.append(e)
        for edge in ("left", "right", "insideV"):
            e = OxmlElement(f"w:{edge}")
            e.set(qn("w:val"), "none")
            e.set(qn("w:sz"), "0")
            e.set(qn("w:space"), "0")
            e.set(qn("w:color"), "auto")
            borders.append(e)
        tbl_pr.append(borders)

    def fill_cell(self, cell, blocks):
        cell.paragraphs[0].text = ""
        first = True
        for block in blocks:
            if block.get("t") not in ("Plain", "Para"):
                continue
            p = cell.paragraphs[0] if first else cell.add_paragraph()
            first = False
            pf = p.paragraph_format
            pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
            pf.first_line_indent = Cm(0)
            pf.line_spacing = 1.0
            pf.space_before = Pt(0)
            pf.space_after = Pt(0)
            for run in list(p.runs):
                run.text = ""
            start = len(p.runs)
            self.render_inlines(p, block["c"])
            for run in p.runs[start:]:
                run.font.size = Pt(SMALL_PT)
                if run.font.name is None:
                    run.font.name = FONT

    # -- document-level pieces --------------------------------------------
    def page_break(self):
        self.doc.add_page_break()
        self.last_para = None
        self.prev_was_table = False


def configure_document(doc):
    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(BODY_PT)
    rpr = normal.element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(attr), FONT)
    pf = normal.paragraph_format
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    pf.line_spacing = 1.5
    pf.first_line_indent = Cm(0.5)
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(3.5)
    section.bottom_margin = Cm(3.5)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)


def add_front_matter(doc, lang, builder: Builder):
    meta = META[lang]
    p = builder.new_para(align=WD_ALIGN_PARAGRAPH.LEFT, indent=0, line=1.5,
                         after=2)
    builder.add_run(p, meta["title"], bold=True)
    p.runs[0].font.size = Pt(TITLE_PT)

    p = builder.new_para(align=WD_ALIGN_PARAGRAPH.LEFT, indent=0, line=1.5)
    builder.add_run(p, meta["authors"])
    p = builder.new_para(align=WD_ALIGN_PARAGRAPH.LEFT, indent=0, line=1.5)
    builder.add_run(p, meta["affiliation"])
    if meta["correspondence"]:
        p = builder.new_para(align=WD_ALIGN_PARAGRAPH.LEFT, indent=0, line=1.5)
        builder.add_run(p, meta["correspondence"])

    p = builder.new_para(indent=0, line=1.0, before=8)
    builder.add_run(p, meta["abstract_label"] + " ", bold=True)
    builder.add_run(p, meta["abstract"])

    p = builder.new_para(indent=0, line=1.0, before=4, after=6)
    builder.add_run(p, meta["keywords_label"] + " ", bold=True)
    builder.add_run(p, meta["keywords"])


def add_back_matter(doc, lang, builder: Builder, bib_order):
    meta = META[lang]
    p = builder.new_para(align=WD_ALIGN_PARAGRAPH.LEFT, indent=0, line=1.5,
                         before=10, after=2)
    builder.add_run(p, meta["bibliography_heading"], bold=True)
    for n, (_key, entry) in enumerate(bib_order, 1):
        p = builder.new_para(align=WD_ALIGN_PARAGRAPH.JUSTIFY, indent=0,
                             line=1.0, after=2)
        builder.add_run(p, f"{n}. {entry}")
        for run in p.runs:
            run.font.size = Pt(SMALL_PT)

    p = builder.new_para(align=WD_ALIGN_PARAGRAPH.LEFT, indent=0, line=1.5,
                         before=10, after=2)
    builder.add_run(p, meta["about_heading"], bold=True)
    for paragraph in meta["about"]:
        p = builder.new_para(align=WD_ALIGN_PARAGRAPH.JUSTIFY, indent=0,
                             line=1.0, after=2)
        split = paragraph.find(". ")
        if split != -1:
            builder.add_run(p, paragraph[:split + 1], bold=True)
            builder.add_run(p, paragraph[split + 1:])
        else:
            builder.add_run(p, paragraph, bold=True)
        for run in p.runs:
            run.font.size = Pt(SMALL_PT)


def prepare_language(path: Path, lang: str):
    src = path.read_text(encoding="utf-8")
    order, bib_index = extract_bibliography(src)
    bib_order = [(key, GOST_BIB[key][lang]) for key, _txt in order]
    body = split_document(src)
    body = strip_comments(body)
    labelmap, sections = scan_sections(body)
    tabmap, n_tables = scan_tables(body)
    main, sep, app = body.partition(r"\appendix")
    parts = [preprocess_text(main, bib_index, labelmap, tabmap)]
    if sep:
        parts.append(preprocess_text(app, bib_index, labelmap, tabmap))
    blocks = []
    for fragment in parts:
        blocks.extend(run_pandoc(fragment))
    return {
        "bib_order": bib_order,
        "sections": sections,
        "n_tables": n_tables,
        "blocks": blocks,
        "n_headers": sum(1 for b in blocks if b.get("t") == "Header"),
    }


def build():
    ru = prepare_language(RU_SRC, "ru")
    en = prepare_language(EN_SRC, "en")
    for name, payload in (("ru", ru), ("en", en)):
        if payload["n_tables"] != 13:
            print(f"warning: {name} has {payload['n_tables']} tables")
        if payload["n_headers"] != len(payload["sections"]):
            print(f"warning: {name} headers {payload['n_headers']} != "
                  f"sections {len(payload['sections'])}")

    doc = Document()
    configure_document(doc)

    for i, (lang, payload) in enumerate((("ru", ru), ("en", en))):
        builder = Builder(doc, lang, payload["sections"])
        if i:
            builder.page_break()
        add_front_matter(doc, lang, builder)
        builder.add_blocks(payload["blocks"])
        add_back_matter(doc, lang, builder, payload["bib_order"])

    doc.save(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    sys.exit(build())
