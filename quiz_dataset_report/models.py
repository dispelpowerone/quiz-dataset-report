"""Plain data structures shared across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TelemetryRow:
    """One aggregated telemetry bucket from ClickHouse."""

    event_name: str
    question_id: int
    language_id: int
    count: int

    @property
    def category(self) -> str:
        """Issue type, e.g. ``answer``/``question``/``image`` (prefix stripped)."""
        name = self.event_name
        for prefix in ("custom_report_reset_", "custom_report_"):
            if name.startswith(prefix):
                return name[len(prefix) :]
        return name

    @property
    def is_reset(self) -> bool:
        return self.event_name.startswith("custom_report_reset_")


@dataclass(frozen=True)
class AnswerInfo:
    text: str
    is_right: bool


@dataclass(frozen=True)
class ResolvedQuestion:
    question_id: int
    test_id: int
    test_title: str
    text: str
    image: str | None
    answers: tuple[AnswerInfo, ...]


@dataclass
class IssueReport:
    """Aggregated reports of one issue type for one question."""

    category: str
    count: int = 0  # non-reset reports
    reset_count: int = 0  # corresponding reset events
    by_language: dict[str, int] = field(default_factory=dict)


@dataclass
class QuestionReport:
    """All reported issues for a single question, with language breakdown."""

    question_id: int
    resolved: bool
    test_title: str
    question_text: str
    image: str | None
    image_url: str | None
    answers: list[AnswerInfo] = field(default_factory=list)
    issues: list[IssueReport] = field(default_factory=list)
    languages: dict[str, int] = field(default_factory=dict)

    @property
    def report_count(self) -> int:
        """Number of (non-reset) user reports; questions are sorted by this."""
        return sum(i.count for i in self.issues)

    @property
    def reset_count(self) -> int:
        return sum(i.reset_count for i in self.issues)


@dataclass
class AppReport:
    app_name: str
    domain: str
    days: int
    date_from: str
    date_to: str
    generated_at: str
    questions: list[QuestionReport] = field(default_factory=list)
    unresolved_question_ids: list[int] = field(default_factory=list)

    @property
    def report_count(self) -> int:
        return sum(q.report_count for q in self.questions)

    @property
    def reset_count(self) -> int:
        return sum(q.reset_count for q in self.questions)

    @property
    def total_events(self) -> int:
        return self.report_count + self.reset_count

    @property
    def is_empty(self) -> bool:
        return self.total_events == 0
