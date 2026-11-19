import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from opencode_stats.cli import _date_range
from opencode_stats.database import read_sessions
from opencode_stats.report import build_report


def create_session_table(database: Path, table: str) -> None:
    assert table in {"session", "session_v2"}
    with sqlite3.connect(database) as connection:
        connection.execute(
            f"""
            CREATE TABLE {table} (
                id TEXT PRIMARY KEY,
                title TEXT,
                directory TEXT NOT NULL,
                model TEXT,
                time_created INTEGER NOT NULL,
                tokens_input INTEGER NOT NULL DEFAULT 0,
                tokens_output INTEGER NOT NULL DEFAULT 0,
                tokens_reasoning INTEGER NOT NULL DEFAULT 0,
                tokens_cache_read INTEGER NOT NULL DEFAULT 0,
                tokens_cache_write INTEGER NOT NULL DEFAULT 0,
                cost REAL NOT NULL DEFAULT 0
            )
            """
        )


def insert_session(
    database: Path,
    table: str,
    session_id: str,
    created_at_ms: int,
    *,
    input_tokens: int = 100,
    title: str | None = "Test session",
) -> None:
    assert table in {"session", "session_v2"}
    with sqlite3.connect(database) as connection:
        connection.execute(
            f"""
            INSERT INTO {table} (
                id, title, directory, model, time_created, tokens_input,
                tokens_output, tokens_reasoning, tokens_cache_read,
                tokens_cache_write, cost
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id, title, "/project", "test-model", created_at_ms,
                input_tokens, 20, 5, 300, 10, 0.5,
            ),
        )


def test_reads_v2_usage_and_report(tmp_path: Path) -> None:
    database = tmp_path / "opencode.db"
    create_session_table(database, "session_v2")
    insert_session(database, "session_v2", "ses_v2", 2000, title=None)

    sessions = list(read_sessions(database, 1000, 3000))
    report = build_report(sessions, "2026-11-19")

    assert len(sessions) == 1
    assert sessions[0].title is None
    assert sessions[0].session_id == "ses_v2"
    assert sessions[0].cost == 0.5
    assert report["totals"]["input_tokens"] == 100
    assert report["totals"]["cache_hit_rate"] == 0.75


def test_legacy_schema_fallback(tmp_path: Path) -> None:
    database = tmp_path / "legacy.db"
    create_session_table(database, "session")
    insert_session(database, "session", "ses_v1", 2000)

    sessions = list(read_sessions(database, 1000, 3000))

    assert [session.session_id for session in sessions] == ["ses_v1"]


def test_prefers_v2_when_both_schemas_exist(tmp_path: Path) -> None:
    database = tmp_path / "mixed.db"
    create_session_table(database, "session")
    create_session_table(database, "session_v2")
    insert_session(database, "session", "ses_legacy", 2000, input_tokens=50)
    insert_session(database, "session_v2", "ses_v2", 2000, input_tokens=150)

    sessions = list(read_sessions(database, 1000, 3000))

    assert [(s.session_id, s.input_tokens) for s in sessions] == [
        ("ses_v2", 150)
    ]


def test_does_not_mix_legacy_rows_into_empty_v2(tmp_path: Path) -> None:
    database = tmp_path / "mixed.db"
    create_session_table(database, "session")
    create_session_table(database, "session_v2")
    insert_session(database, "session", "ses_legacy", 2000)

    assert list(read_sessions(database, 1000, 3000)) == []


def test_date_range_start_is_inclusive_end_exclusive(tmp_path: Path) -> None:
    database = tmp_path / "opencode.db"
    create_session_table(database, "session_v2")
    for created_at in (999, 1000, 2999, 3000):
        insert_session(database, "session_v2", f"ses_{created_at}", created_at)

    sessions = list(read_sessions(database, 1000, 3000))

    assert [s.created_at_ms for s in sessions] == [1000, 2999]


def test_reports_unsupported_schema(tmp_path: Path) -> None:
    database = tmp_path / "unsupported.db"
    sqlite3.connect(database).close()

    with pytest.raises(ValueError, match="session_v2"):
        list(read_sessions(database, 0, 3000))


def test_cli_json_with_v2_database(tmp_path: Path) -> None:
    database = tmp_path / "opencode.db"
    create_session_table(database, "session_v2")
    selected_day = "2026-11-19"
    start_ms = _date_range(selected_day)[1]
    insert_session(database, "session_v2", "ses_v2", start_ms + 1000)

    result = subprocess.run(
        [
            sys.executable, "-m", "opencode_stats", "--date", selected_day,
            "--database", str(database), "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(result.stdout)
    assert report["session_count"] == 1
    assert report["totals"]["input_tokens"] == 100
