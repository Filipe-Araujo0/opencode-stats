import argparse
import json
import re
import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path

from .database import DEFAULT_DATABASE, read_sessions
from .report import build_report


def _date_range(value: str) -> tuple[date, int, int]:
    selected = date.today() if value == "today" else date.fromisoformat(value)
    start = datetime.combine(selected, time.min).astimezone().timestamp() * 1000
    end = datetime.combine(selected + timedelta(days=1), time.min).astimezone().timestamp() * 1000
    return selected, int(start), int(end)


def _clock_time(value: str) -> time:
    if not re.fullmatch(r"\d{2}:\d{2}", value):
        raise argparse.ArgumentTypeError("Informe o horário local no formato HH:MM (ex.: 09:30)")
    try:
        return time.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Horário inválido: " + value) from error


def _activity_range(
    selected: date, start_time: time | None, end_time: time | None
) -> tuple[int, int]:
    start = datetime.combine(selected, start_time or time.min).astimezone()
    if end_time is None:
        end_date = selected + timedelta(days=1)
        end_clock = time.min
    else:
        end_date = selected
        end_clock = end_time
        if end_clock <= (start_time or time.min):
            end_date += timedelta(days=1)
    end = datetime.combine(end_date, end_clock).astimezone()
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def main() -> None:
    parser = argparse.ArgumentParser(description="Estatísticas locais do OpenCode (somente leitura)")
    parser.add_argument("--date", default="today", help="today ou data ISO YYYY-MM-DD")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--model", help="ID exato do modelo no OpenCode (ex.: claude-sonnet-4-5)")
    parser.add_argument("--provider", help="ID exato do provedor no OpenCode (ex.: anthropic)")
    parser.add_argument(
        "--start-time", "--from-time", dest="start_time", type=_clock_time,
        metavar="HH:MM", help="Horário inicial local (inclusivo) da data selecionada",
    )
    parser.add_argument(
        "--end-time", "--to-time", dest="end_time", type=_clock_time,
        metavar="HH:MM", help="Horário final local (exclusivo); pode passar da meia-noite",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    try:
        selected, start_ms, end_ms = _date_range(args.date)
    except ValueError as error:
        parser.error(f"Data inválida em --date: {error}")

    filtered = any(
        item is not None
        for item in (args.model, args.provider, args.start_time, args.end_time)
    )
    if args.start_time is not None or args.end_time is not None:
        start_ms, end_ms = _activity_range(selected, args.start_time, args.end_time)

    try:
        report = build_report(
            read_sessions(
                args.database, start_ms, end_ms,
                model=args.model,
                provider=args.provider,
                message_usage=filtered,
            ),
            selected.isoformat(),
        )
    except (OSError, ValueError, sqlite3.DatabaseError) as error:
        parser.error(str(error))

    report["aggregation"] = "message" if filtered else "session"
    report["filters"] = {
        "model": args.model,
        "provider": args.provider,
        "start_time": args.start_time.isoformat(timespec="minutes") if args.start_time else None,
        "end_time": args.end_time.isoformat(timespec="minutes") if args.end_time else None,
        "start_ms": start_ms,
        "end_ms_exclusive": end_ms,
    }
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    totals = report["totals"]
    print(f"OpenCode stats: {report['date']}")
    if filtered:
        print("Agregação: mensagens do assistente (horário da atividade)")
        if args.model:
            print(f"Modelo: {args.model}")
        if args.provider:
            print(f"Provedor: {args.provider}")
        print(
            f"Janela (horário local): "
            f"{datetime.fromtimestamp(start_ms / 1000).astimezone():%Y-%m-%d %H:%M} "
            f"até {datetime.fromtimestamp(end_ms / 1000).astimezone():%Y-%m-%d %H:%M} "
            "(limite final exclusivo)"
        )
    print(f"Sessões: {report['session_count']}")
    print(f"Input: {totals['input_tokens']}")
    print(f"Output: {totals['output_tokens']}")
    print(f"Reasoning: {totals['reasoning_tokens']}")
    print(f"Cache read: {totals['cache_read_tokens']}")
    print(f"Cache write: {totals['cache_write_tokens']}")
    print(f"Custo (USD): {totals['cost']}")
    print(f"Cache hit rate: {totals['cache_hit_rate']}")
    print(f"Sessões sem usage: {report['sessions_without_usage']}")


if __name__ == "__main__":
    main()
