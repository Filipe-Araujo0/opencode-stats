import sqlite3
from collections.abc import Iterator
from pathlib import Path

from .models import SessionUsage

DEFAULT_DATABASE = Path.home() / ".local" / "share" / "opencode" / "opencode.db"


def read_sessions(database: Path, start_ms: int, end_ms: int) -> Iterator[SessionUsage]:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT id, title, directory, model, time_created,
                   tokens_input, tokens_output, tokens_reasoning,
                   tokens_cache_read, tokens_cache_write, cost
            FROM session
            WHERE time_created >= ? AND time_created < ?
            ORDER BY time_created, id
            """,
            (start_ms, end_ms),
        )
        for row in rows:
            yield SessionUsage(
                session_id=row["id"],
                title=row["title"],
                directory=row["directory"],
                model=row["model"],
                created_at_ms=row["time_created"],
                input_tokens=row["tokens_input"],
                output_tokens=row["tokens_output"],
                reasoning_tokens=row["tokens_reasoning"],
                cache_read_tokens=row["tokens_cache_read"],
                cache_write_tokens=row["tokens_cache_write"],
                cost=row["cost"],
            )
    finally:
        connection.close()
