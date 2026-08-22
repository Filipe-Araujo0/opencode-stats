from opencode_stats.models import SessionUsage
from opencode_stats.report import build_report


def make_session(**overrides: object) -> SessionUsage:
    values: dict[str, object] = {
        "session_id": "session-1",
        "title": "Test",
        "directory": "/tmp/project",
        "model": "model",
        "created_at_ms": 0,
        "input_tokens": 100,
        "output_tokens": 20,
        "reasoning_tokens": 5,
        "cache_read_tokens": 300,
        "cache_write_tokens": 10,
        "cost": 0.5,
    }
    values.update(overrides)
    return SessionUsage(**values)


def test_cache_hit_rate_uses_input_and_cache_read() -> None:
    report = build_report([make_session()], "2026-08-22")

    assert report["totals"]["cache_hit_rate"] == 0.75


def test_sessions_without_usage_are_counted() -> None:
    report = build_report(
        [make_session(), make_session(session_id="session-2", input_tokens=0,
                                       output_tokens=0, reasoning_tokens=0,
                                       cache_read_tokens=0, cache_write_tokens=0)],
        "2026-08-22",
    )

    assert report["sessions_without_usage"] == 1
