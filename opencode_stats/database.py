import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from .models import SessionUsage

DEFAULT_DATABASE = Path.home() / ".local" / "share" / "opencode" / "opencode.db"


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }


def _session_table(connection: sqlite3.Connection) -> str:
    tables = _tables(connection)
    if "session_v2" in tables:
        return "session_v2"
    if "session" in tables:
        return "session"
    raise ValueError(
        "OpenCode session table not found: expected 'session_v2' (v2) "
        "or 'session' (legacy). Check the --database path."
    )


def _session_model(value: str | None, schema: str) -> tuple[str | None, str | None]:
    if schema != "session_v2" or value is None:
        return value, None
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value, None
    if not isinstance(parsed, dict):
        return value, None
    model_id = parsed.get("id")
    provider_id = parsed.get("providerID")
    return (
        model_id if isinstance(model_id, str) else None,
        provider_id if isinstance(provider_id, str) else None,
    )


def _read_session_totals(
    connection: sqlite3.Connection, table: str, start_ms: int, end_ms: int
) -> Iterator[SessionUsage]:
    # The table name is selected from two fixed, internal identifiers above.
    rows = connection.execute(
        f"""
        SELECT id, title, directory, model, time_created,
               tokens_input, tokens_output, tokens_reasoning,
               tokens_cache_read, tokens_cache_write, cost
        FROM {table}
        WHERE time_created >= ? AND time_created < ?
        ORDER BY time_created, id
        """,
        (start_ms, end_ms),
    )
    for row in rows:
        model, provider = _session_model(row["model"], table)
        yield SessionUsage(
            session_id=row["id"],
            title=row["title"],
            directory=row["directory"],
            model=model,
            created_at_ms=row["time_created"],
            input_tokens=row["tokens_input"],
            output_tokens=row["tokens_output"],
            reasoning_tokens=row["tokens_reasoning"],
            cache_read_tokens=row["tokens_cache_read"],
            cache_write_tokens=row["tokens_cache_write"],
            cost=row["cost"],
            provider=provider,
        )


def _read_message_totals(
    connection: sqlite3.Connection,
    start_ms: int,
    end_ms: int,
    model: str | None,
    provider: str | None,
) -> Iterator[SessionUsage]:
    if "session_message" not in _tables(connection):
        raise ValueError(
            "OpenCode v2 message table 'session_message' not found. "
            "Model, provider and time filters require per-message usage."
        )

    conditions = [
        "message.type = 'assistant'",
        "message.time_created >= ?",
        "message.time_created < ?",
    ]
    params: list[str | int] = [start_ms, end_ms]

    # Forked sessions can contain copied messages from an earlier session.
    # The current v2 schema marks those messages via fork_session_id.
    columns = {row[1] for row in connection.execute("PRAGMA table_info(session_v2)")}
    if "fork_session_id" in columns:
        conditions.append(
            "(session.fork_session_id IS NULL OR "
            "message.time_created >= session.time_created)"
        )
    if model is not None:
        conditions.append("json_extract(message.data, '$.model.id') = ?")
        params.append(model)
    if provider is not None:
        conditions.append("json_extract(message.data, '$.model.providerID') = ?")
        params.append(provider)

    where_clause = " AND ".join(conditions)
    rows = connection.execute(
        f"""
        SELECT
            session.id AS session_id,
            session.title AS title,
            session.directory AS directory,
            session.time_created AS created_at_ms,
            CASE
                WHEN COUNT(DISTINCT json_extract(message.data, '$.model.id')) = 1
                 AND COUNT(json_extract(message.data, '$.model.id')) = COUNT(*)
                THEN MIN(json_extract(message.data, '$.model.id'))
                ELSE NULL
            END AS model,
            CASE
                WHEN COUNT(DISTINCT json_extract(message.data, '$.model.providerID')) = 1
                 AND COUNT(json_extract(message.data, '$.model.providerID')) = COUNT(*)
                THEN MIN(json_extract(message.data, '$.model.providerID'))
                ELSE NULL
            END AS provider,
            SUM(COALESCE(json_extract(message.data, '$.tokens.input'), 0)) AS input_tokens,
            SUM(COALESCE(json_extract(message.data, '$.tokens.output'), 0)) AS output_tokens,
            SUM(COALESCE(json_extract(message.data, '$.tokens.reasoning'), 0)) AS reasoning_tokens,
            SUM(COALESCE(json_extract(message.data, '$.tokens.cache.read'), 0)) AS cache_read_tokens,
            SUM(COALESCE(json_extract(message.data, '$.tokens.cache.write'), 0)) AS cache_write_tokens,
            SUM(COALESCE(json_extract(message.data, '$.cost'), 0)) AS cost
        FROM session_message AS message
        JOIN session_v2 AS session ON session.id = message.session_id
        WHERE {where_clause}
        GROUP BY session.id
        ORDER BY MIN(message.time_created), session.id
        """,
        params,
    )
    for row in rows:
        yield SessionUsage(
            session_id=row["session_id"],
            title=row["title"],
            directory=row["directory"],
            model=row["model"],
            created_at_ms=row["created_at_ms"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            reasoning_tokens=row["reasoning_tokens"],
            cache_read_tokens=row["cache_read_tokens"],
            cache_write_tokens=row["cache_write_tokens"],
            cost=row["cost"],
            provider=row["provider"],
        )


def read_sessions(
    database: Path,
    start_ms: int,
    end_ms: int,
    *,
    model: str | None = None,
    provider: str | None = None,
    message_usage: bool = False,
) -> Iterator[SessionUsage]:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        session_table = _session_table(connection)
        if model is not None or provider is not None or message_usage:
            if session_table != "session_v2":
                raise ValueError(
                    "Model, provider and time filters require the OpenCode v2 "
                    "schema ('session_v2' and 'session_message')."
                )
            yield from _read_message_totals(connection, start_ms, end_ms, model, provider)
        else:
            yield from _read_session_totals(connection, session_table, start_ms, end_ms)
    finally:
        connection.close()
