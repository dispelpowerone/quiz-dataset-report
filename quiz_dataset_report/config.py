"""Configuration models and loader.

Configuration is read from a YAML file. Any ``${VAR}`` placeholders in string
values are expanded from environment variables at load time, which keeps
secrets (such as SMTP credentials) out of the config file.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class _StrictBoolLoader(yaml.SafeLoader):
    """SafeLoader that only treats true/false as booleans.

    Standard YAML 1.1 (and PyYAML) coerce ``on``/``off``/``yes``/``no`` to
    booleans, which would silently turn the ``on`` domain into ``True``. This
    loader resolves only ``true``/``false`` as booleans, like YAML 1.2.
    """


# Drop the broad bool resolver from every first-character bucket it lives in...
for _ch in "yYnNtTfFoO":
    _StrictBoolLoader.yaml_implicit_resolvers[_ch] = [
        (tag, regexp)
        for tag, regexp in yaml.SafeLoader.yaml_implicit_resolvers.get(_ch, [])
        if tag != "tag:yaml.org,2002:bool"
    ]
# ...then re-add a strict true/false-only resolver.
_StrictBoolLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
)

# Default mapping of telemetry ``language_id`` -> language code used by the API
# localizations. Order follows the API's TextLocalizations schema. Override in
# config under ``languages:`` if the backend assigns ids differently.
DEFAULT_LANGUAGES: dict[int, str] = {
    1: "EN",
    2: "FR",
    3: "ZH",
    4: "ES",
    5: "RU",
    6: "FA",
    7: "PA",
    8: "PT",
}


class ClickHouseConfig(BaseModel):
    url: str = "http://pi.local:8123/"
    database: str = "firebase"
    table: str = "analytics_events"
    user: str = "default"
    password: str = ""
    timeout_seconds: int = 60


class ApiConfig(BaseModel):
    base_url: str = "https://pi.local/api"
    verify_tls: bool = False
    timeout_seconds: int = 30
    # Template for rendering question images. The API returns an image filename
    # (e.g. "101-1.png"); images are served per-domain at
    # /api/images/{domain}/{filename}. Supports {domain} and {image}
    # placeholders. Set to "" to show the filename only (no <img>).
    image_url_template: str = "https://pi.local/api/images/{domain}/{image}"


class SmtpConfig(BaseModel):
    host: str = "smtp.gmail.com"
    port: int = 587
    use_starttls: bool = True
    username: str | None = None
    password: str | None = None
    from_address: str = ""
    # Generous default: embedded-image emails can be several MB and slow to
    # upload, which would trip a short socket timeout mid-send.
    timeout_seconds: int = 120


class ReportConfig(BaseModel):
    days: int = 30
    event_prefix: str = "custom_report_"
    # Download question images and embed them inline in the email so they render
    # even when clients block remote images. Disable with --no-embed-images.
    embed_images: bool = True
    # Downscale/re-encode embedded images to keep the email small. Images wider
    # than image_max_width are resized; opaque images are re-encoded as JPEG at
    # image_jpeg_quality (images with transparency stay PNG). Set max_width to 0
    # to disable downscaling and embed originals.
    image_max_width: int = 600
    image_jpeg_quality: int = 80


class AppConfig(BaseModel):
    name: str
    domain: str
    dataset: str
    enabled: bool = True


class Config(BaseModel):
    clickhouse: ClickHouseConfig = Field(default_factory=ClickHouseConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    smtp: SmtpConfig = Field(default_factory=SmtpConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)
    languages: dict[int, str] = Field(default_factory=lambda: dict(DEFAULT_LANGUAGES))
    # Single global list of maintainers; every per-app report is sent to all of them.
    maintainers: list[str] = Field(default_factory=list)
    apps: list[AppConfig] = Field(default_factory=list)

    def app_by_key(self, key: str) -> AppConfig | None:
        """Look up an app by its name or domain (case-insensitive)."""
        key_l = key.lower()
        for app in self.apps:
            if app.name.lower() == key_l or app.domain.lower() == key_l:
                return app
        return None


def _expand_env(value: Any) -> Any:
    """Recursively expand ``${VAR}`` references in string values."""
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def load_config(path: str | Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    raw = yaml.load(path.read_text(), Loader=_StrictBoolLoader) or {}
    raw = _expand_env(raw)
    return Config.model_validate(raw)
