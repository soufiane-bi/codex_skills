"""Shared output formatting for Snowflake query results."""

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

EXPORT_DIR = Path.home() / "snowflake-exports"
PREVIEW_ROWS = 200


def format_output(
    columns,
    rows,
    fmt="txt",
    save_fmt=None,
    save_path=None,
    no_save=False,
    sql=None,
    stream=sys.stdout,
):
    """Print a preview and optionally save full results."""
    if not columns and not rows:
        print("No results.", file=sys.stderr)
        return

    actual_save_fmt = save_fmt or fmt
    actual_save_path = save_path
    if not actual_save_path and not no_save:
        EXPORT_DIR.mkdir(exist_ok=True)
        ext = {"txt": "txt", "csv": "csv", "json": "json"}[actual_save_fmt]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        actual_save_path = str(EXPORT_DIR / f"query-{timestamp}.{ext}")

    if actual_save_path:
        _write_to_file(columns, rows, actual_save_fmt, actual_save_path)

    if len(rows) > PREVIEW_ROWS:
        _write_output(columns, rows[:PREVIEW_ROWS], fmt, stream)
        print(f"\n... showing {PREVIEW_ROWS} of {len(rows)} rows", file=sys.stderr)
    else:
        _write_output(columns, rows, fmt, stream)

    if actual_save_path:
        print(f"Results saved to: {actual_save_path}", file=sys.stderr)
        if sql:
            sql_path = str(Path(actual_save_path).with_suffix(".sql"))
            Path(sql_path).write_text(sql)
            print(f"SQL saved to: {sql_path}", file=sys.stderr)


def _write_output(columns, rows, fmt, stream):
    if fmt == "txt":
        _format_txt(columns, rows, stream)
    elif fmt == "csv":
        _format_csv(columns, rows, stream)
    elif fmt == "json":
        _format_json(columns, rows, stream)


def _write_to_file(columns, rows, fmt, path):
    with open(path, "w", newline="") as f:
        _write_output(columns, rows, fmt, f)


def _format_txt(columns, rows, stream):
    str_rows = [[_to_str(value) for value in row] for row in rows]
    widths = [len(column) for column in columns]
    for row in str_rows:
        for index, value in enumerate(row):
            if index < len(widths):
                widths[index] = max(widths[index], len(value))

    header = "  ".join(column.ljust(widths[index]) for index, column in enumerate(columns))
    separator = "  ".join("-" * width for width in widths)
    stream.write(header + "\n")
    stream.write(separator + "\n")

    for row in str_rows:
        line = "  ".join(
            (row[index] if index < len(row) else "").ljust(widths[index])
            for index in range(len(columns))
        )
        stream.write(line + "\n")


def _format_csv(columns, rows, stream):
    writer = csv.writer(stream)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_to_str(value) for value in row])


def _format_json(columns, rows, stream):
    result = []
    for row in rows:
        result.append({column: row[index] if index < len(row) else None for index, column in enumerate(columns)})
    stream.write(json.dumps(result, indent=2, default=str) + "\n")


def _to_str(value):
    if value is None:
        return "NULL"
    return str(value)


def format_duration(seconds):
    if seconds < 1:
        return f"{round(seconds * 1000)}ms"
    seconds = round(seconds)
    if seconds >= 60:
        minutes, seconds = divmod(seconds, 60)
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"
