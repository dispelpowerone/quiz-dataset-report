# quiz-dataset-report

Generates an HTML report of user-reported quiz issues and emails it to the
maintainers. For each app it reads `custom_report_*` telemetry from ClickHouse
over the last *N* days, resolves the affected questions against the quiz content
API, groups the issues **per question** (sorted by number of reports), and emails
one report per app.

Each question card shows the English question text, its image, all answers
(correct one marked), and a per-issue table broken down by language.

## Requirements

- Python ≥ 3.11, [`uv`](https://docs.astral.sh/uv/)
- Network access to:
  - ClickHouse: `http://pi.local:8123/` (database `firebase`)
  - Quiz API: `https://pi.local/api` (docs at `/api/docs`)
- An SMTP account for sending mail (Gmail/Workspace App Password by default)

## Setup

```bash
uv sync                          # install dependencies into .venv
cp config.example.yaml config.yaml
$EDITOR config.yaml              # set maintainers; domains are pre-filled
```

SMTP credentials are read from the environment (referenced via `${VAR}` in the
config), so they never live in the file:

```bash
export SMTP_USERNAME="you@gmail.com"
export SMTP_PASSWORD="your-16-char-google-app-password"
```

> Google App Password: Google account → Security → 2-Step Verification →
> App passwords. Use that 16-character value, not your login password.

## Usage

Run as a module (this project is not installed as a package):

```bash
# Default window (30 days), all enabled apps, send email to maintainers
uv run python -m quiz_dataset_report

# Preview without sending — write HTML to ./out and print a summary
uv run python -m quiz_dataset_report --dry-run --output-dir out

# Custom window and a single app
uv run python -m quiz_dataset_report --days 7 --app on

# List configured apps
uv run python -m quiz_dataset_report --list-apps
```

### Options

| Flag | Description |
|------|-------------|
| `-c, --config PATH` | Config file (default `config.yaml`). |
| `-d, --days N` | Reporting window; overrides `report.days`. |
| `-a, --app KEY` | Limit to an app by name or domain (repeatable). |
| `-o, --output-dir DIR` | Also write each report's HTML to `DIR/<domain>.html`. |
| `--dry-run` | Build reports but do not send email. |
| `--include-empty` | Also process/send apps with no events in the window. |
| `--list-apps` | Print configured apps and exit. |
| `-v, --verbose` | Debug logging. |

The process exits non-zero if any app fails (one failing app does not abort the
others).

## Scheduling

This is a one-shot CLI; schedule it externally. Example monthly cron:

```cron
0 7 1 * * cd /path/to/quiz-dataset-report && \
  SMTP_USERNAME=... SMTP_PASSWORD=... \
  /path/to/uv run python -m quiz_dataset_report >> /var/log/quiz-report.log 2>&1
```

## Configuration

See `config.example.yaml`. Notable points:

- `apps[]` maps each app's API `domain` to its ClickHouse `import_dataset`.
- `maintainers` is a single global list; every per-app report goes to all of them.
- `languages` maps telemetry `language_id` → API localization code. Unknown ids
  render as `#<id>`.
- `api.image_url_template`: how question images are embedded. Images are served
  per-domain at `/api/images/{domain}/{filename}`; the template's `{domain}` and
  `{image}` placeholders are filled in. Set to `""` to show the filename only.
- `domain` values like `on` are kept as strings (the loader does not coerce
  `on`/`off`/`yes`/`no` to booleans).

## How it works

```
ClickHouse (firebase.analytics_events)        Quiz API (/tests/get, /questions/get)
        │  custom_report_* events                     │  question text, image, answers
        │  (question_id, language_id, count)          │
        └──────────────┬──────────────────────────────┘
                       ▼
             resolver: group by question, sort by report count
                       ▼
             Jinja2 → HTML  ──►  SMTP ──► maintainers
```

## Development

```bash
uv run pytest        # tests
uv run black .       # format
```

## Project layout

```
quiz_dataset_report/
  cli.py          argument parsing + orchestration
  config.py       YAML config models + loader (env expansion, strict bools)
  clickhouse.py   telemetry query (clickhouse-connect, HTTP/8123)
  quiz_api.py     quiz content API client (httpx)
  resolver.py     join telemetry with questions → AppReport
  report.py       Jinja2 HTML rendering
  mailer.py       SMTP delivery
  models.py       dataclasses
  templates/report.html.j2
tests/
config.example.yaml
```
