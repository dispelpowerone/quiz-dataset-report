"""Command-line entry point: query telemetry, build reports, email them."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .clickhouse import ClickHouseClient
from .config import AppConfig, Config, load_config
from .mailer import Mailer
from .models import AppReport
from .quiz_api import QuizApiClient
from .report import render_html, subject_line
from .resolver import build_app_report, build_question_index

logger = logging.getLogger("quiz_dataset_report")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="quiz-dataset-report",
        description="Build and email HTML reports of quiz issue telemetry.",
    )
    p.add_argument("-c", "--config", default="config.yaml", help="Path to config YAML.")
    p.add_argument(
        "-d",
        "--days",
        type=int,
        default=None,
        help="Reporting window in days (overrides config.report.days).",
    )
    p.add_argument(
        "-a",
        "--app",
        "--domain",
        action="append",
        dest="apps",
        metavar="NAME_OR_DOMAIN",
        help="Limit to this app by name or domain (repeatable). "
        "Default: all enabled apps.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Build reports but do not send email.",
    )
    p.add_argument(
        "-o",
        "--output-dir",
        default=None,
        help="Write each report's HTML to this directory.",
    )
    p.add_argument(
        "--include-empty",
        action="store_true",
        help="Also report/send apps with no events in the window.",
    )
    p.add_argument(
        "--list-apps", action="store_true", help="List configured apps and exit."
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Debug logging.")
    return p.parse_args(argv)


def _select_apps(config: Config, keys: list[str] | None) -> list[AppConfig]:
    if not keys:
        return [a for a in config.apps if a.enabled]
    selected: list[AppConfig] = []
    for key in keys:
        app = config.app_by_key(key)
        if app is None:
            raise SystemExit(f"Unknown app: {key!r}")
        selected.append(app)
    return selected


def _build_report_for_app(
    app: AppConfig,
    *,
    config: Config,
    days: int,
    ch: ClickHouseClient,
    today: date,
    generated_at: str,
    include_empty: bool,
) -> AppReport | None:
    rows = ch.fetch_report_events(app.dataset, config.report.event_prefix, days)
    if not rows and not include_empty:
        logger.info("App %s (%s): no events, skipping", app.name, app.domain)
        return None

    index = {}
    if rows:
        with QuizApiClient(config.api) as api:
            index = build_question_index(api, app.domain)

    return build_app_report(
        app_name=app.name,
        domain=app.domain,
        days=days,
        date_from=(today - timedelta(days=days)).isoformat(),
        date_to=today.isoformat(),
        generated_at=generated_at,
        rows=rows,
        index=index,
        config=config,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = load_config(args.config)

    if args.list_apps:
        for a in config.apps:
            flag = "" if a.enabled else " (disabled)"
            print(f"{a.name}\t{a.domain}\t{a.dataset}{flag}")
        return 0

    days = args.days if args.days is not None else config.report.days
    apps = _select_apps(config, args.apps)
    if not apps:
        logger.warning("No apps selected.")
        return 0

    output_dir = Path(args.output_dir) if args.output_dir else None
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).date()
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    ch = ClickHouseClient(config.clickhouse)
    mailer = Mailer(config.smtp)
    failures = 0

    try:
        for app in apps:
            try:
                report = _build_report_for_app(
                    app,
                    config=config,
                    days=days,
                    ch=ch,
                    today=today,
                    generated_at=generated_at,
                    include_empty=args.include_empty,
                )
            except Exception:  # noqa: BLE001 - one bad app must not abort the rest
                logger.exception("Failed to build report for %s", app.name)
                failures += 1
                continue

            if report is None:
                continue

            html = render_html(report)

            if output_dir:
                out = output_dir / f"{app.domain}.html"
                out.write_text(html, encoding="utf-8")
                logger.info("Wrote %s", out)

            summary = (
                f"{app.name} ({app.domain}): {report.report_count} reports, "
                f"{len(report.questions)} questions, {report.reset_count} resets"
            )

            if args.dry_run:
                logger.info("[dry-run] %s — not sending", summary)
                print(f"[dry-run] {summary}")
                continue

            try:
                mailer.send_html(
                    to=config.maintainers,
                    subject=subject_line(report),
                    html=html,
                )
                print(f"[sent] {summary}")
            except Exception:  # noqa: BLE001
                logger.exception("Failed to send report for %s", app.name)
                failures += 1
    finally:
        ch.close()

    return 1 if failures else 0
