from quiz_dataset_report.config import Config
from quiz_dataset_report.models import AnswerInfo, ResolvedQuestion, TelemetryRow
from quiz_dataset_report.resolver import build_app_report


def _config() -> Config:
    return Config.model_validate(
        {
            "languages": {1: "EN", 2: "FR"},
            "maintainers": ["m@example.com"],
            "apps": [],
        }
    )


def _index() -> dict[int, ResolvedQuestion]:
    return {
        101: ResolvedQuestion(
            question_id=101,
            test_id=1,
            test_title="Test 1",
            text="What does this sign mean?",
            image="101-1.png",
            answers=(
                AnswerInfo("Stop", True),
                AnswerInfo("Go", False),
            ),
        )
    }


def _build(rows, index=None):
    return build_app_report(
        app_name="Ontario",
        domain="on",
        days=30,
        date_from="2026-05-26",
        date_to="2026-06-25",
        generated_at="2026-06-25 00:00 UTC",
        rows=rows,
        index=index if index is not None else _index(),
        config=_config(),
    )


def test_groups_by_question_and_counts_languages():
    rows = [
        TelemetryRow("custom_report_answer", 101, 1, 3),
        TelemetryRow("custom_report_answer", 101, 2, 2),
        TelemetryRow("custom_report_image", 101, 1, 1),
    ]
    report = _build(rows)
    assert len(report.questions) == 1
    q = report.questions[0]
    assert q.question_id == 101
    assert q.report_count == 6
    assert q.resolved is True
    assert q.test_title == "Test 1"
    assert {i.category for i in q.issues} == {"answer", "image"}
    answer = next(i for i in q.issues if i.category == "answer")
    assert answer.by_language == {"EN": 3, "FR": 2}
    assert q.languages == {"EN": 4, "FR": 2}


def test_questions_sorted_by_report_count_desc():
    rows = [
        TelemetryRow("custom_report_answer", 101, 1, 2),
        TelemetryRow("custom_report_question", 202, 1, 9),
    ]
    index = _index()
    index[202] = ResolvedQuestion(202, 2, "Test 2", "Q2", None, ())
    report = _build(rows, index)
    assert [q.question_id for q in report.questions] == [202, 101]


def test_reset_events_tracked_separately():
    rows = [
        TelemetryRow("custom_report_answer", 101, 1, 5),
        TelemetryRow("custom_report_reset_answer", 101, 1, 2),
    ]
    report = _build(rows)
    q = report.questions[0]
    assert q.report_count == 5  # resets excluded from report count
    assert q.reset_count == 2
    issue = q.issues[0]
    assert issue.count == 5 and issue.reset_count == 2
    # reset language not counted toward language totals
    assert q.languages == {"EN": 5}


def test_unresolved_question_id():
    rows = [TelemetryRow("custom_report_answer", 999, 1, 1)]
    report = _build(rows)
    q = report.questions[0]
    assert q.resolved is False
    assert report.unresolved_question_ids == [999]
    assert "999" in q.question_text


def test_unknown_language_id_labelled():
    rows = [TelemetryRow("custom_report_answer", 101, 7, 1)]
    report = _build(rows)
    assert report.questions[0].languages == {"#7": 1}
