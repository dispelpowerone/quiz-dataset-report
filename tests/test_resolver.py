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


def row(event, qid, lang, user, session, count=1):
    return TelemetryRow(event, qid, lang, user, session, count)


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


def test_report_is_deduped_by_user_and_session():
    # One user in one session reports three issue types -> ONE report.
    rows = [
        row("custom_report_question", 101, 1, "u1", 5),
        row("custom_report_image", 101, 1, "u1", 5),
        row("custom_report_answer", 101, 1, "u1", 5),
    ]
    q = _build(rows).questions[0]
    assert q.report_count == 1
    # but every flagged issue type is still listed, each from that one report
    assert {i.category for i in q.issues} == {"question", "image", "answer"}
    assert all(i.count == 1 for i in q.issues)
    assert q.languages == {"EN": 1}


def test_repeated_same_issue_in_session_counts_once():
    rows = [
        row("custom_report_answer", 101, 1, "u1", 5, count=3),
        row("custom_report_answer", 101, 1, "u1", 5, count=2),
    ]
    q = _build(rows).questions[0]
    assert q.report_count == 1
    assert q.issues[0].count == 1


def test_distinct_users_and_sessions_counted_separately():
    rows = [
        row("custom_report_answer", 101, 1, "u1", 5),  # report A
        row("custom_report_image", 101, 1, "u1", 5),  # same report A (u1/s5)
        row("custom_report_answer", 101, 2, "u2", 7),  # report B
        row("custom_report_answer", 101, 1, "u1", 9),  # report C (u1, new session)
    ]
    q = _build(rows).questions[0]
    assert q.report_count == 3  # (u1,5), (u2,7), (u1,9)
    answer = next(i for i in q.issues if i.category == "answer")
    image = next(i for i in q.issues if i.category == "image")
    assert answer.count == 3  # all three reports flagged answer
    assert image.count == 1  # only report A flagged image
    assert answer.by_language == {"EN": 2, "FR": 1}
    assert q.languages == {"EN": 2, "FR": 1}


def test_questions_sorted_by_report_count_desc():
    rows = [
        row("custom_report_answer", 101, 1, "u1", 1),
        row("custom_report_question", 202, 1, "u1", 1),
        row("custom_report_question", 202, 1, "u2", 2),
    ]
    index = _index()
    index[202] = ResolvedQuestion(202, 2, "Test 2", "Q2", None, ())
    report = _build(rows, index)
    assert [q.question_id for q in report.questions] == [202, 101]


def test_reset_events_tracked_separately():
    rows = [
        row("custom_report_answer", 101, 1, "u1", 5),
        row("custom_report_reset_answer", 101, 1, "u9", 8),
    ]
    q = _build(rows).questions[0]
    assert q.report_count == 1  # resets excluded from report count
    assert q.reset_count == 1
    issue = q.issues[0]
    assert issue.count == 1 and issue.reset_count == 1
    assert q.languages == {"EN": 1}  # reset language not counted


def test_unresolved_question_id():
    rows = [row("custom_report_answer", 999, 1, "u1", 1)]
    report = _build(rows)
    q = report.questions[0]
    assert q.resolved is False
    assert report.unresolved_question_ids == [999]
    assert "999" in q.question_text


def test_unknown_language_id_labelled():
    rows = [row("custom_report_answer", 101, 7, "u1", 1)]
    report = _build(rows)
    assert report.questions[0].languages == {"#7": 1}
