"""Resolve telemetry buckets into a per-question report via the quiz API."""

from __future__ import annotations

import logging

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

    # question_id -> {category -> IssueReport}
    by_question: dict[int, QuestionReport] = {}
    unresolved: set[int] = set()

    for row in rows:
        qid = row.question_id
        resolved = index.get(qid)
        if resolved is None:
            unresolved.add(qid)

        qr = by_question.get(qid)
        if qr is None:
            qr = QuestionReport(
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
            by_question[qid] = qr

        # find or create the IssueReport for this category
        issue = next((i for i in qr.issues if i.category == row.category), None)
        if issue is None:
            issue = IssueReport(category=row.category)
            qr.issues.append(issue)

        lang_label = languages.get(row.language_id, f"#{row.language_id}")
        if row.is_reset:
            issue.reset_count += row.count
        else:
            issue.count += row.count
            issue.by_language[lang_label] = (
                issue.by_language.get(lang_label, 0) + row.count
            )
            qr.languages[lang_label] = qr.languages.get(lang_label, 0) + row.count

    questions = list(by_question.values())
    for qr in questions:
        qr.issues.sort(key=lambda i: i.count + i.reset_count, reverse=True)
    # sort by number of (non-reset) reports, then resets, then id for stability
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
