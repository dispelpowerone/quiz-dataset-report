"""Render an AppReport into HTML."""

from __future__ import annotations

from jinja2 import Environment, PackageLoader, select_autoescape

from .models import AppReport

_env = Environment(
    loader=PackageLoader("quiz_dataset_report", "templates"),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_html(report: AppReport) -> str:
    template = _env.get_template("report.html.j2")
    return template.render(report=report)


def subject_line(report: AppReport) -> str:
    return (
        f"[quiz-report] {report.app_name} ({report.domain}): "
        f"{report.report_count} reports / {len(report.questions)} questions "
        f"(last {report.days}d)"
    )
