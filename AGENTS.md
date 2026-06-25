# AGENTS.md

Guidance for AI coding agents working in this repository.

## What this is

`quiz-dataset-report` reads `custom_report_*` quiz-issue telemetry from
ClickHouse, resolves the affected questions against the quiz content API, builds
one HTML report per app (grouped by question, sorted by report count), and emails
it to a global maintainer list. It is a one-shot CLI, not a long-running service.

## Setup & commands

```bash
uv sync                              # install deps into .venv (uv-managed)
uv run pytest                        # run tests
uv run black .                       # format (line length 88) — run before committing
uv run python -m quiz_dataset_report --list-apps
uv run python -m quiz_dataset_report --dry-run --output-dir out   # safe preview, no email
```

- Python ≥ 3.11. Dependencies and the venv are managed by **uv** — never edit
  `uv.lock` by hand; add deps via `pyproject.toml` then `uv sync`.
- Code is formatted with **black**. Keep it black-clean; do not hand-fight its
  formatting.
- The project is **run as a module** (`python -m quiz_dataset_report`); it is not
  installed as a package and intentionally has **no build backend**
  (`[tool.uv] package = false`). Don't add `[build-system]`/`[project.scripts]`
  unless the run model changes.

## Architecture

Single linear pipeline; each module has one job:

```
cli.py        argument parsing + per-app orchestration (one failing app ≠ abort)
config.py     YAML → pydantic models; ${ENV} expansion; strict-bool YAML loader
clickhouse.py telemetry query via clickhouse-connect (HTTP, port 8123)
quiz_api.py   quiz content API client (httpx): /tests/get, /questions/get
resolver.py   join telemetry + questions → AppReport (group by question)
report.py     Jinja2 → HTML
mailer.py     SMTP delivery (stdlib smtplib)
models.py     dataclasses (TelemetryRow, ResolvedQuestion, QuestionReport, ...)
templates/report.html.j2
```

Data flow: ClickHouse buckets `(event_name, question_id, language_id, count)` →
resolver groups by `question_id`, splits reset vs non-reset events, maps
`language_id` via `config.languages` → `AppReport` → HTML → email.

## External services (all on `pi.local`)

- **ClickHouse**: `http://pi.local:8123/`, database `firebase`, table
  `analytics_events`, user `default` (empty password). Native port 9000 is also
  open but we use the HTTP client deliberately. Report events are
  `custom_report_*`; `custom_report_reset_*` are corrections, tracked separately.
- **Quiz API**: `https://pi.local/api` (docs `/api/docs`, spec `/api/openapi.json`).
  Self-signed cert → `api.verify_tls: false`. Endpoints return
  `{error_code, payload}`; `error_code != 0` is an error.
- **Question images**: served per-domain at
  `https://pi.local/api/images/{domain}/{filename}`. Other `/images/...` paths
  return the SPA's `index.html` (HTTP 200 `text/html`) — that is NOT an image.

## Gotchas (learned the hard way — don't regress these)

- **YAML treats `on`/`off`/`yes`/`no` as booleans.** App domains include `on`
  (Ontario), which naive YAML parses as `True`. `config.py` installs a
  `_StrictBoolLoader` that resolves only `true`/`false`. Keep using it; don't
  switch back to `yaml.safe_load`.
- **Image URLs are domain-specific** and the bare `/images/<file>` path is a
  decoy (SPA fallback). Verify any image-URL change returns
  `Content-Type: image/png`, not `text/html`.
- **`language_id` mapping is an assumption.** Telemetry uses ids 1–9; the API
  exposes 8 localizations (EN/FR/ZH/ES/RU/FA/PA/PT). `config.languages` maps
  1–8; unmapped ids (e.g. 9) render as `#<id>`. Confirm with the backend before
  treating the mapping as ground truth.
- **Emailed images may not render**: clients block external images and `pi.local`
  is internal + self-signed. Opening the HTML in a browser works. If inline
  rendering in email is required, embed images as base64/CID attachments.

## Conventions

- Secrets (SMTP creds) come from the environment via `${VAR}` placeholders in
  config — never commit credentials. `config.yaml` is gitignored; edit
  `config.example.yaml` for shared defaults.
- ClickHouse queries use **server-side parameter binding** (`{name:Type}`), never
  string interpolation of values into SQL.
- Per-app failures are logged and counted, not raised, so one bad app doesn't
  block the others; the process exits non-zero if any app failed.

## Testing

- `tests/` uses pytest with `pythonpath = ["."]` (flat layout). Tests are
  offline — they don't hit ClickHouse or the API. Keep new unit tests offline;
  inject fakes/fixtures rather than calling `pi.local`.
- When changing telemetry aggregation or grouping, add/adjust cases in
  `tests/test_resolver.py`.
