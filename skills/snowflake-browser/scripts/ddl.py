#!/usr/bin/env python3
"""Get Snowflake DDL for a table or view."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.client import add_connection_args, execute_query, qualified_name, resolve_config, sql_literal
from lib.formatter import format_duration, format_output


def main():
    parser = argparse.ArgumentParser(description="Get Snowflake DDL")
    add_connection_args(parser)
    parser.add_argument("--type", choices=["table", "view"], default="table", help="Object type")
    parser.add_argument("--schema", required=True, help="Schema name")
    parser.add_argument("--name", required=True, help="Object name")
    args = parser.parse_args()
    config = resolve_config(args)

    database = args.database or config.get("database")
    if not database:
        print("ERROR: database is required. Pass --database or run setup with a default database.", file=sys.stderr)
        sys.exit(1)

    object_type = args.type.upper()
    object_name = qualified_name(database=database, schema=args.schema, name=args.name).replace('"', "")
    sql = f"SELECT GET_DDL({sql_literal(object_type)}, {sql_literal(object_name)}) AS ddl"

    columns, rows, meta = execute_query(sql, config, timeout=args.timeout, max_rows=args.max_rows)
    format_output(columns, rows, fmt=args.format, save_fmt=args.save_format, save_path=args.save, no_save=args.no_save, sql=sql if args.save_sql else None)
    print(f"{len(rows)} DDL row(s). Duration: {format_duration(meta['duration_secs'])}", file=sys.stderr)


if __name__ == "__main__":
    main()
