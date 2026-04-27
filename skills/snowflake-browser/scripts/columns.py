#!/usr/bin/env python3
"""List Snowflake columns for a table or view."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.client import add_connection_args, execute_query, qualified_name, resolve_config, sql_literal
from lib.formatter import format_duration, format_output


def main():
    parser = argparse.ArgumentParser(description="List Snowflake table columns")
    add_connection_args(parser)
    parser.add_argument("--table", required=True, help="Table or view name")
    args = parser.parse_args()
    config = resolve_config(args)

    database = args.database or config.get("database")
    schema = args.schema or config.get("schema")
    if not database or not schema:
        print("ERROR: database and schema are required. Pass --database/--schema or run setup with defaults.", file=sys.stderr)
        sys.exit(1)

    sql = f"""
    SELECT ordinal_position,
           column_name,
           data_type,
           is_nullable,
           column_default,
           comment
    FROM   {qualified_name(database=database, schema="INFORMATION_SCHEMA", name="COLUMNS")}
    WHERE  table_schema = {sql_literal(schema.upper())}
    AND    table_name = {sql_literal(args.table.upper())}
    ORDER  BY ordinal_position
    """

    columns, rows, meta = execute_query(sql, config, timeout=args.timeout, max_rows=args.max_rows)
    format_output(columns, rows, fmt=args.format, save_fmt=args.save_format, save_path=args.save, no_save=args.no_save, sql=sql if args.save_sql else None)
    print(f"{len(rows)} columns. Duration: {format_duration(meta['duration_secs'])}", file=sys.stderr)


if __name__ == "__main__":
    main()
