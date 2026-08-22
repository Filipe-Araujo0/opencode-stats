import argparse
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

from .database import DEFAULT_DATABASE, read_sessions
from .report import build_report


def _date_range(value: str) -> tuple[date, int, int]:
    selected = date.today() if value == "today" else date.fromisoformat(value)
    start = datetime.combine(selected, time.min).astimezone().timestamp() * 1000
    end = datetime.combine(selected + timedelta(days=1), time.min).astimezone().timestamp() * 1000
    return selected, int(start), int(end)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default="today", help="today ou data ISO YYYY-MM-DD")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    selected, start_ms, end_ms = _date_range(args.date)
    report = build_report(
        read_sessions(args.database, start_ms, end_ms), selected.isoformat()
    )
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    totals = report["totals"]
    print(f"OpenCode stats: {report['date']}")
    print(f"Sessões: {report['session_count']}")
    print(f"Input: {totals['input_tokens']}")
    print(f"Output: {totals['output_tokens']}")
    print(f"Reasoning: {totals['reasoning_tokens']}")
    print(f"Cache read: {totals['cache_read_tokens']}")
    print(f"Cache write: {totals['cache_write_tokens']}")
    print(f"Cache hit rate: {totals['cache_hit_rate']}")
    print(f"Sessões sem usage: {report['sessions_without_usage']}")
