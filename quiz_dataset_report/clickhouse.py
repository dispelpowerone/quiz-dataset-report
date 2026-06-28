"""ClickHouse client for fetching report telemetry, via clickhouse-connect."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import clickhouse_connect
from clickhouse_connect.driver.client import Client

from .config import ClickHouseConfig
from .models import TelemetryRow

logger = logging.getLogger(__name__)

# Aggregate custom_report_* events for one app's dataset over the last N days.
# Parameterized with server-side bindings so values never touch the SQL string.
_QUERY = """
SELECT
    event_name AS event_name,
    toInt64(JSONExtractFloat(event_params_json, 'question_id')) AS question_id,
    toInt32(JSONExtractFloat(event_params_json, 'language_id')) AS language_id,
    user_pseudo_id AS user_pseudo_id,
    toInt64(JSONExtractFloat(event_params_json, 'ga_session_id')) AS session_id,
    count() AS count
FROM {database:Identifier}.{table:Identifier}
WHERE import_dataset = {dataset:String}
  AND event_name LIKE {pattern:String}
  AND event_date >= today() - {days:UInt32}
  AND JSONExtractFloat(event_params_json, 'question_id') > 0
GROUP BY event_name, question_id, language_id, user_pseudo_id, session_id
ORDER BY count DESC
"""


class ClickHouseClient:
    def __init__(self, config: ClickHouseConfig) -> None:
        self._config = config
        parsed = urlparse(config.url)
        self._client: Client = clickhouse_connect.get_client(
            host=parsed.hostname or "localhost",
            port=parsed.port or (8443 if parsed.scheme == "https" else 8123),
            username=config.user,
            password=config.password,
            database=config.database,
            secure=parsed.scheme == "https",
            connect_timeout=config.timeout_seconds,
            send_receive_timeout=config.timeout_seconds,
        )

    def fetch_report_events(
        self, dataset: str, prefix: str, days: int
    ) -> list[TelemetryRow]:
        parameters = {
            "database": self._config.database,
            "table": self._config.table,
            "dataset": dataset,
            "pattern": f"{prefix}%",
            "days": days,
        }
        logger.debug("Querying ClickHouse for dataset=%s days=%d", dataset, days)
        result = self._client.query(_QUERY, parameters=parameters)
        rows = [
            TelemetryRow(
                event_name=row[0],
                question_id=int(row[1]),
                language_id=int(row[2]),
                user_pseudo_id=row[3],
                session_id=int(row[4]),
                count=int(row[5]),
            )
            for row in result.result_rows
        ]
        logger.info("Dataset %s: %d telemetry buckets", dataset, len(rows))
        return rows

    def close(self) -> None:
        self._client.close()
