#!/usr/bin/env python3
"""List Snowflake tables and views in a schema."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.client import add_connection_args, execute_query, qualified_name, resolve_config, sql_literal
from lib.formatter import format_duration, format_output


def main():
    parser = argparse.ArgumentParser(description="List Snowflake tables and views")
    add_connection_args(parser)
    parser.add_argument("--schema", required=True, help="Schema name")
    parser.add_argument("--pattern", help="Optional table/view name pattern")
    parser.add_argument("--include-views", action="store_true", help="Include views as well as base tables")
    args = parser.parse_args()
    config = resolve_config(args)

    database = args.database or config.get("database")
    if not database:
        print("ERROR: database is required. Pass --database or run setup with a default database.", file=sys.stderr)
        sys.exit(1)

    table_types = "'BASE TABLE', 'VIEW'" if args.include_views else "'BASE TABLE'"
    filters = [
        f"table_schema = {sql_literal(args.schema.upper())}",
        f"table_type IN ({table_types})",
    ]
    if args.pattern:
        filters.append(f"table_name ILIKE {sql_literal('%' + args.pattern + '%')}")

    sql = f"""
    SELECT table_schema,
           table_name,
           table_type,
           row_count,
           bytes,
           created,
           last_altered
    FROM   {qualified_name(database=database, schema="INFORMATION_SCHEMA", name="TABLES")}
    WHERE  {" AND ".join(filters)}
    ORDER  BY table_schema,
              table_name
    """

    columns, rows, meta = execute_query(sql, config, timeout=args.timeout, max_rows=args.max_rows)
    format_output(columns, rows, fmt=args.format, save_fmt=args.save_format, save_path=args.save, no_save=args.no_save, sql=sql if args.save_sql else None)
    print(f"{len(rows)} objects. Duration: {format_duration(meta['duration_secs'])}", file=sys.stderr)


if __name__ == "__main__":
    main()
