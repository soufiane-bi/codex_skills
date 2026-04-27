#!/usr/bin/env python3
"""List Snowflake schemas."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.client import add_connection_args, execute_query, qualified_name, resolve_config
from lib.formatter import format_duration, format_output


def main():
    parser = argparse.ArgumentParser(description="List Snowflake schemas")
    add_connection_args(parser)
    args = parser.parse_args()
    config = resolve_config(args)

    database = config.get("database")
    if database:
        sql = f"""
        SELECT schema_name,
               schema_owner,
               created,
               is_transient
        FROM   {qualified_name(database=database, schema="INFORMATION_SCHEMA", name="SCHEMATA")}
        WHERE  schema_name <> 'INFORMATION_SCHEMA'
        ORDER  BY schema_name
        """
    else:
        sql = "SHOW SCHEMAS"

    columns, rows, meta = execute_query(sql, config, timeout=args.timeout, max_rows=args.max_rows)
    format_output(columns, rows, fmt=args.format, save_fmt=args.save_format, save_path=args.save, no_save=args.no_save, sql=sql if args.save_sql else None)
    print(f"{len(rows)} schemas. Duration: {format_duration(meta['duration_secs'])}", file=sys.stderr)


if __name__ == "__main__":
    main()
