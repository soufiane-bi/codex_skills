#!/usr/bin/env python3
"""Search Snowflake tables, views, and columns."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.client import add_connection_args, execute_query, qualified_name, resolve_config, sql_literal
from lib.formatter import format_duration, format_output


def main():
    parser = argparse.ArgumentParser(description="Search Snowflake objects and columns")
    add_connection_args(parser)
    parser.add_argument("--pattern", required=True, help="Text to search for")
    args = parser.parse_args()
    config = resolve_config(args)

    database = args.database or config.get("database")
    if not database:
        print("ERROR: database is required. Pass --database or run setup with a default database.", file=sys.stderr)
        sys.exit(1)

    pattern = sql_literal("%" + args.pattern + "%")
    tables = qualified_name(database=database, schema="INFORMATION_SCHEMA", name="TABLES")
    columns = qualified_name(database=database, schema="INFORMATION_SCHEMA", name="COLUMNS")
    sql = f"""
    SELECT 'table' AS match_type,
           table_schema,
           table_name,
           NULL AS column_name,
           table_type AS detail
    FROM   {tables}
    WHERE  table_schema <> 'INFORMATION_SCHEMA'
    AND    table_name ILIKE {pattern}

    UNION ALL

    SELECT 'column' AS match_type,
           table_schema,
           table_name,
           column_name,
           data_type AS detail
    FROM   {columns}
    WHERE  table_schema <> 'INFORMATION_SCHEMA'
    AND    column_name ILIKE {pattern}

    ORDER  BY match_type,
              table_schema,
              table_name,
              column_name
    """

    columns_out, rows, meta = execute_query(sql, config, timeout=args.timeout, max_rows=args.max_rows)
    format_output(columns_out, rows, fmt=args.format, save_fmt=args.save_format, save_path=args.save, no_save=args.no_save, sql=sql if args.save_sql else None)
    print(f"{len(rows)} matches. Duration: {format_duration(meta['duration_secs'])}", file=sys.stderr)


if __name__ == "__main__":
    main()
