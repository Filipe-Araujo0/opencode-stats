import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import date, time
from pathlib import Path

import pytest

from opencode_stats.cli import _activity_range, _clock_time, _date_range
from opencode_stats.database import read_sessions
from opencode_stats.report import build_report


def make_database(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE session_v2 (
                id TEXT PRIMARY KEY,
                title TEXT,
                directory TEXT NOT NULL,
                model TEXT,
                fork_session_id TEXT,
                time_created INTEGER NOT NULL,
                tokens_input INTEGER NOT NULL DEFAULT 0,
                tokens_output INTEGER NOT NULL DEFAULT 0,
                tokens_reasoning INTEGER NOT NULL DEFAULT 0,
                tokens_cache_read INTEGER NOT NULL DEFAULT 0,
                tokens_cache_write INTEGER NOT NULL DEFAULT 0,
                cost REAL NOT NULL DEFAULT 0
            );
            CREATE TABLE session_message (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                type TEXT NOT NULL,
                time_created INTEGER NOT NULL,
                data TEXT NOT NULL
            );
            """
        )


def insert_session(
    database: Path,
    session_id: str,
    created_at_ms: int,
    *,
    model: str | None = None,
    provider: str = "openai",
    fork_session_id: str | None = None,
) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO session_v2 (
                id, title, directory, model, fork_session_id,
                time_created, tokens_input, cost
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id, "Session title", "/tmp/repo",
                json.dumps({"id": model, "providerID": provider}) if model else None,
                fork_session_id, created_at_ms, 999, 88.0,
            ),
        )


def insert_message(
    database: Path,
    message_id: str,
    session_id: str,
    created_at_ms: int,
    *,
    model: str | None = "model-a",
    provider: str | None = "openai",
    input_tokens: int | None = 20,
    output_tokens: int | None = 10,
    cache_read_tokens: int | None = 30,
    cost: float = 0.25,
    role: str = "assistant",
) -> None:
    model_info = {"id": model, "providerID": provider} if model is not None else {}
    payload = {
        "model": model_info,
        "tokens": {
            "input": input_tokens,
            "output": output_tokens,
            "reasoning": 2,
            "cache": {"read": cache_read_tokens, "write": 5},
        },
        "cost": cost,
    }
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO session_message (id, session_id, type, time_created, data)
            VALUES (?, ?, ?, ?, ?)
            """,
            (message_id, session_id, role, created_at_ms, json.dumps(payload)),
        )


def test_unfiltered_v2_stays_session_based_and_parses_model_json(tmp_path: Path) -> None:
    database = tmp_path / "opencode.db"
    make_database(database)
    insert_session(database, "ses1", 1000, model="model-old", provider="anthropic")
    insert_message(database, "msg1", "ses1", 2000)

    sessions = list(read_sessions(database, 0, 3000))

    assert len(sessions) == 1
    assert sessions[0].input_tokens == 999
    assert sessions[0].model == "model-old"
    assert sessions[0].provider == "anthropic"


def test_model_and_provider_filter_each_message_not_session(tmp_path: Path) -> None:
    database = tmp_path / "opencode.db"
    make_database(database)
    insert_session(database, "ses1", 1000, model="model-old", provider="other")
    insert_message(database, "msg1", "ses1", 2000, model="model-a", provider="openai")
    insert_message(database, "msg2", "ses1", 3000, model="model-a", provider="anthropic")
    insert_message(database, "msg3", "ses1", 4000, model="model-b", provider="openai")
    insert_message(database, "msg4", "ses1", 4000, model="model-a", provider="openai", role="user")

    sessions = list(read_sessions(database, 1500, 5000, model="model-a", provider="openai"))
    report = build_report(sessions, "2026-11-19")

    assert report["session_count"] == 1
    assert report["totals"]["input_tokens"] == 20
    assert report["totals"]["cache_hit_rate"] == 0.6
    assert report["totals"]["cost"] == 0.25
    assert sessions[0].model == "model-a"
    assert sessions[0].provider == "openai"
    assert sessions[0].created_at_ms == 1000


def test_filters_aggregate_only_matching_messages_for_older_session(tmp_path: Path) -> None:
    database = tmp_path / "opencode.db"
    make_database(database)
    insert_session(database, "old_session", 1000, model="model-old")
    insert_session(database, "second", 1000)
    insert_message(database, "msg1", "old_session", 2200, model="model-a", input_tokens=10)
    insert_message(database, "msg2", "old_session", 3200, model="model-a", input_tokens=15)
    insert_message(database, "msg3", "second", 1200, model="model-a", input_tokens=50)

    sessions = list(read_sessions(database, 2000, 4000, model="model-a"))

    assert len(sessions) == 1
    assert sessions[0].session_id == "old_session"
    assert sessions[0].input_tokens == 25
    assert sessions[0].output_tokens == 20
    assert sessions[0].cost == 0.5


def test_multiple_models_in_one_session_are_not_misattributed(tmp_path: Path) -> None:
    database = tmp_path / "opencode.db"
    make_database(database)
    insert_session(database, "ses1", 1000)
    insert_message(database, "msg1", "ses1", 2000, model="model-a", provider="openai")
    insert_message(database, "msg2", "ses1", 2500, model="model-b", provider="anthropic")

    sessions = list(read_sessions(database, 1000, 3000, message_usage=True))
    report = build_report(sessions, "2026-11-19")

    assert report["session_count"] == 1
    assert report["totals"]["input_tokens"] == 40
    assert sessions[0].model is None
    assert sessions[0].provider is None


def test_missing_token_fields_are_zero_and_null_model_is_unknown(tmp_path: Path) -> None:
    database = tmp_path / "opencode.db"
    make_database(database)
    insert_session(database, "ses1", 1000)
    insert_message(database, "msg1", "ses1", 2000, model=None,
                   input_tokens=None, output_tokens=None, cache_read_tokens=None)

    sessions = list(read_sessions(database, 1000, 3000, message_usage=True))

    assert sessions[0].model is None
    assert sessions[0].input_tokens == 0
    assert sessions[0].cache_read_tokens == 0
    assert sessions[0].cost == 0.25


def test_time_window_boundaries_and_overnight(tmp_path: Path) -> None:
    database = tmp_path / "opencode.db"
    make_database(database)
    selected = date(2026, 11, 19)
    midnight = _date_range(selected.isoformat())[1]
    insert_session(database, "ses1", midnight - 86_400_000)
    insert_message(database, "before", "ses1", midnight + 8 * 3_600_000 + 59 * 60_000)
    insert_message(database, "included", "ses1", midnight + 9 * 3_600_000)
    insert_message(database, "included2", "ses1", midnight + 10 * 3_600_000)
    insert_message(database, "excluded", "ses1", midnight + 11 * 3_600_000)

    start, end = _activity_range(selected, time(9), time(11))
    sessions = list(read_sessions(database, start, end, message_usage=True))

    assert sessions[0].input_tokens == 40
    assert start == midnight + 9 * 3_600_000
    assert end == midnight + 11 * 3_600_000

    overnight_start, overnight_end = _activity_range(selected, time(23), time(2))
    assert overnight_start == midnight + 23 * 3_600_000
    assert overnight_end == midnight + 26 * 3_600_000
    insert_message(database, "next-day", "ses1", overnight_start)
    insert_message(database, "next-day2", "ses1", midnight + 25 * 3_600_000)
    overnight = list(read_sessions(database, overnight_start, overnight_end, message_usage=True))
    assert overnight[0].input_tokens == 40


def test_forked_session_does_not_count_copied_messages(tmp_path: Path) -> None:
    database = tmp_path / "opencode.db"
    make_database(database)
    insert_session(database, "original", 1000)
    insert_session(database, "fork", 5000, fork_session_id="original")
    insert_message(database, "copied", "fork", 4000, input_tokens=300)
    insert_message(database, "new", "fork", 6000, input_tokens=15)

    sessions = list(read_sessions(database, 2000, 7000, message_usage=True))
    assert len(sessions) == 1
    assert sessions[0].input_tokens == 15


def test_legacy_and_missing_message_table_give_explanatory_errors(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.db"
    with sqlite3.connect(legacy) as connection:
        connection.execute("CREATE TABLE session (id TEXT)")
    with pytest.raises(ValueError, match="OpenCode v2"):
        list(read_sessions(legacy, 0, 100, provider="openai"))

    missing_message = tmp_path / "missing.db"
    with sqlite3.connect(missing_message) as connection:
        connection.execute("CREATE TABLE session_v2 (id TEXT)")
    with pytest.raises(ValueError, match="session_message"):
        list(read_sessions(missing_message, 0, 100, message_usage=True))


def test_clock_time_validation_and_end_only(tmp_path: Path) -> None:
    for value in ["9:00", "25:00", "12:60", "12:00:30", "12:00+03:00"]:
        with pytest.raises(argparse.ArgumentTypeError):
            _clock_time(value)
    assert _clock_time("09:30") == time(9, 30)

    selected = date(2026, 11, 19)
    start, end = _activity_range(selected, None, time(12))
    assert end - start == 12 * 60 * 60 * 1000
    start, end = _activity_range(selected, None, time.min)
    assert end - start == 24 * 60 * 60 * 1000


def test_cli_json_with_all_filters(tmp_path: Path) -> None:
    database = tmp_path / "opencode.db"
    make_database(database)
    selected = "2026-11-19"
    midnight = _date_range(selected)[1]
    insert_session(database, "ses1", midnight - 50_000)
    insert_message(database, "wrong_hour", "ses1", midnight + 8 * 3_600_000)
    insert_message(database, "wrong_provider", "ses1", midnight + 9 * 3_600_000,
                   provider="anthropic")
    insert_message(database, "correct", "ses1", midnight + 9 * 3_600_000,
                   model="model-a", provider="openai", input_tokens=42)

    result = subprocess.run(
        [sys.executable, "-m", "opencode_stats", "--date", selected,
         "--database", str(database), "--provider", "openai",
         "--model", "model-a", "--start-time", "09:00",
         "--end-time", "10:00", "--json"],
        check=True, capture_output=True, text=True,
    )
    report = json.loads(result.stdout)
    assert report["session_count"] == 1
    assert report["totals"]["input_tokens"] == 42
    assert report["aggregation"] == "message"
    assert report["filters"]["model"] == "model-a"
    assert report["filters"]["provider"] == "openai"


def test_sql_parameters_are_not_interpolated(tmp_path: Path) -> None:
    database = tmp_path / "opencode.db"
    make_database(database)
    insert_session(database, "ses1", 1000)
    insert_message(database, "msg1", "ses1", 2000)
    assert list(read_sessions(database, 0, 3000, model="model-a' OR 1=1 --")) == []
