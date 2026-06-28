"""Resolve telemetry buckets into a per-question report via the quiz API."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from .config import Config
from .models import (
    AnswerInfo,
    AppReport,
    IssueReport,
    QuestionReport,
    ResolvedQuestion,
    TelemetryRow,
)
from .quiz_api import QuizApiClient

logger = logging.getLogger(__name__)

# Preference order when picking a single display string from localizations.
_TEXT_PREFERENCE = ("EN", "FR", "ES", "PT", "ZH", "RU", "FA", "PA")


def _pick_text(localized: dict | None) -> str:
    """Pick English text (falling back to any available) from a PrebuildText."""
    if not localized:
        return ""
    loc = localized.get("localizations") or {}
    for code in _TEXT_PREFERENCE:
        entry = loc.get(code)
        if entry and entry.get("content"):
            return entry["content"]
    for entry in loc.values():
        if entry and entry.get("content"):
            return entry["content"]
    return ""


def _parse_answers(raw_answers: list[dict]) -> tuple[AnswerInfo, ...]:
    answers = []
    for a in raw_answers or []:
        answers.append(
            AnswerInfo(
                text=_pick_text(a.get("text")),
                is_right=bool(a.get("is_right_answer")),
            )
        )
    return tuple(answers)


def build_question_index(
    api: QuizApiClient, domain: str
) -> dict[int, ResolvedQuestion]:
    """Build question_id -> ResolvedQuestion for an entire domain."""
    index: dict[int, ResolvedQuestion] = {}
    tests = api.get_tests(domain)
    for test in tests:
        test_id = test["test_id"]
        test_title = _pick_text(test.get("title"))
        for q in api.get_questions(domain, test_id):
            qid = q["question_id"]
            index[qid] = ResolvedQuestion(
                question_id=qid,
                test_id=test_id,
                test_title=test_title,
                text=_pick_text(q.get("text")),
                image=q.get("image"),
                answers=_parse_answers(q.get("answers", [])),
            )
    logger.info("Domain %s: indexed %d questions", domain, len(index))
    return index


def _image_url(image: str | None, domain: str, template: str) -> str | None:
    if not image or not template:
        return None
    return template.format(domain=domain, image=image)


@dataclass
class _Report:
    """One distinct report (user+session): the issue types and languages it spans."""

    categories: set[str] = field(default_factory=set)
    languages: set[str] = field(default_factory=set)


def _summarize(
    reports: dict[tuple[str, int], _Report],
    resets: dict[tuple[str, int], _Report],
) -> tuple[int, int, dict[str, int], list[IssueReport]]:
    """Turn deduped reports into counts, language totals, and per-issue rows."""
    # languages: number of distinct reports using each language
    languages: dict[str, int] = {}
    for r in reports.values():
        for lang in r.languages:
            languages[lang] = languages.get(lang, 0) + 1

    categories = {c for r in reports.values() for c in r.categories}
    categories |= {c for r in resets.values() for c in r.categories}

    issues: list[IssueReport] = []
    for cat in categories:
        by_language: dict[str, int] = {}
        count = 0
        for r in reports.values():
            if cat in r.categories:
                count += 1
                for lang in r.languages:
                    by_language[lang] = by_language.get(lang, 0) + 1
        reset_count = sum(1 for r in resets.values() if cat in r.categories)
        issues.append(
            IssueReport(
                category=cat,
                count=count,
                reset_count=reset_count,
                by_language=by_language,
            )
        )
    issues.sort(key=lambda i: (i.count + i.reset_count), reverse=True)
    return len(reports), len(resets), languages, issues


def build_app_report(
    *,
    app_name: str,
    domain: str,
    days: int,
    date_from: str,
    date_to: str,
    generated_at: str,
    rows: list[TelemetryRow],
    index: dict[int, ResolvedQuestion],
    config: Config,
) -> AppReport:
    """Aggregate telemetry rows into a per-question report, sorted by reports."""
    languages = config.languages
    image_template = config.api.image_url_template

    by_question: dict[int, QuestionReport] = {}
    unresolved: set[int] = set()

    # Per question, group events into distinct reports keyed by (user, session).
    # Each report tracks the issue types and languages it spans. A report that
    # flags question + image is one report covering two issue types.
    # qid -> report_key -> {"cats": set, "langs": set}
    reports: dict[int, dict[tuple[str, int], _Report]] = defaultdict(dict)
    resets: dict[int, dict[tuple[str, int], _Report]] = defaultdict(dict)

    for row in rows:
        qid = row.question_id
        if qid not in by_question:
            resolved = index.get(qid)
            if resolved is None:
                unresolved.add(qid)
            by_question[qid] = QuestionReport(
                question_id=qid,
                resolved=resolved is not None,
                test_title=resolved.test_title if resolved else "",
                question_text=(
                    resolved.text if resolved else f"(unresolved question #{qid})"
                ),
                image=resolved.image if resolved else None,
                image_url=(
                    _image_url(resolved.image, domain, image_template)
                    if resolved
                    else None
                ),
                answers=list(resolved.answers) if resolved else [],
            )

        bucket = resets[qid] if row.is_reset else reports[qid]
        entry = bucket.get(row.report_key)
        if entry is None:
            entry = _Report()
            bucket[row.report_key] = entry
        entry.categories.add(row.category)
        if not row.is_reset:
            entry.languages.add(languages.get(row.language_id, f"#{row.language_id}"))

    questions: list[QuestionReport] = []
    for qid, qr in by_question.items():
        qr.report_count, qr.reset_count, qr.languages, qr.issues = _summarize(
            reports.get(qid, {}), resets.get(qid, {})
        )
        questions.append(qr)

    # sort by number of (deduped) reports, then resets, then id for stability
    questions.sort(
        key=lambda q: (q.report_count, q.reset_count, -q.question_id), reverse=True
    )

    return AppReport(
        app_name=app_name,
        domain=domain,
        days=days,
        date_from=date_from,
        date_to=date_to,
        generated_at=generated_at,
        questions=questions,
        unresolved_question_ids=sorted(unresolved),
    )
