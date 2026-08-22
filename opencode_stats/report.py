from collections.abc import Iterable
from statistics import mean, median
from typing import Any

from .models import SessionUsage


def build_report(sessions: Iterable[SessionUsage], date: str) -> dict[str, Any]:
    rows = list(sessions)
    total_input = sum(row.input_tokens for row in rows)
    total_output = sum(row.output_tokens for row in rows)
    total_reasoning = sum(row.reasoning_tokens for row in rows)
    total_cache_read = sum(row.cache_read_tokens for row in rows)
    total_cache_write = sum(row.cache_write_tokens for row in rows)
    cache_denominator = total_cache_read + total_input
    cache_hit_rate = (
        total_cache_read / cache_denominator if cache_denominator else None
    )
    cache_call_rates = [
        row.cache_hit_rate for row in rows if row.cache_hit_rate is not None
    ]

    return {
        "date": date,
        "session_count": len(rows),
        "totals": {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "reasoning_tokens": total_reasoning,
            "cache_read_tokens": total_cache_read,
            "cache_write_tokens": total_cache_write,
            "cost": sum(row.cost for row in rows),
            "cache_hit_rate": cache_hit_rate,
        },
        "cache_hit_rate_by_session": {
            "mean": mean(cache_call_rates) if cache_call_rates else None,
            "median": median(cache_call_rates) if cache_call_rates else None,
        },
        "sessions_without_usage": sum(
            row.input_tokens
            + row.output_tokens
            + row.reasoning_tokens
            + row.cache_read_tokens
            + row.cache_write_tokens
            == 0
            for row in rows
        ),
        "sessions": [row.to_dict() for row in rows],
    }
