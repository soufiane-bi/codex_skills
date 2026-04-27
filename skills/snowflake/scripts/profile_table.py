#!/usr/bin/env python3
"""Profile a Snowflake table and optionally validate its grain."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.client import add_connection_args, execute_query, qualified_name, quote_ident, resolve_config, sql_literal
from lib.formatter import format_duration, format_output


def main():
    parser = argparse.ArgumentParser(description="Profile a Snowflake table and validate optional grain")
    add_connection_args(parser)
    parser.add_argument("--table", required=True, help="Table or view name")
    parser.add_argument(
        "--columns",
        help="Optional comma-separated columns to profile. Defaults to every column.",
    )
    parser.add_argument(
        "--grain",
        help="Optional comma-separated grain columns to check for nulls and duplicates.",
    )
    parser.add_argument(
        "--duplicate-examples",
        type=int,
        default=20,
        help="Number of duplicate grain examples to show when --grain is provided",
    )
    args = parser.parse_args()
    config = resolve_config(args)

    database = args.database or config.get("database")
    schema = args.schema or config.get("schema")
    if not database or not schema:
        print("ERROR: database and schema are required. Pass --database/--schema or run setup with defaults.", file=sys.stderr)
        sys.exit(1)

    table_name = args.table.upper()
    columns = get_columns(database, schema, table_name, config, args)
    if not columns:
        print(f"ERROR: No columns found for {database}.{schema}.{args.table}", file=sys.stderr)
        sys.exit(1)

    selected_columns = select_columns(columns, args.columns)
    if not selected_columns:
        print("ERROR: None of the requested columns exist on the table.", file=sys.stderr)
        sys.exit(1)

    table_ref = qualified_name(database=database, schema=schema, name=args.table)
    print(f"Table: {database}.{schema}.{args.table}")
    print()

    summary_sql = build_summary_sql(database, schema, table_name)
    summary_columns, summary_rows, summary_meta = execute_query(
        summary_sql,
        config,
        timeout=args.timeout,
        max_rows=1,
    )
    print("Table summary")
    format_output(summary_columns, summary_rows, fmt=args.format, no_save=True)
    print(f"Summary duration: {format_duration(summary_meta['duration_secs'])}", file=sys.stderr)
    print()

    profile_sql = build_column_profile_sql(table_ref, selected_columns)
    profile_columns, profile_rows, profile_meta = execute_query(
        profile_sql,
        config,
        timeout=args.timeout,
        max_rows=max(args.max_rows, len(selected_columns)),
    )
    print("Column profile")
    format_output(profile_columns, profile_rows, fmt=args.format, no_save=True)
    print(f"Profile duration: {format_duration(profile_meta['duration_secs'])}", file=sys.stderr)

    if args.grain:
        grain_columns = select_columns(columns, args.grain)
        requested_grain = parse_column_list(args.grain)
        missing = [column for column in requested_grain if column.upper() not in {c["column_name"] for c in columns}]
        if missing:
            print(f"ERROR: Grain column(s) not found: {', '.join(missing)}", file=sys.stderr)
            sys.exit(1)
        print()
        print(f"Grain validation: {', '.join(column['column_name'] for column in grain_columns)}")
        grain_sql = build_grain_summary_sql(table_ref, grain_columns)
        grain_summary_columns, grain_summary_rows, grain_summary_meta = execute_query(
            grain_sql,
            config,
            timeout=args.timeout,
            max_rows=1,
        )
        format_output(grain_summary_columns, grain_summary_rows, fmt=args.format, no_save=True)
        print(f"Grain summary duration: {format_duration(grain_summary_meta['duration_secs'])}", file=sys.stderr)

        examples_limit = max(0, args.duplicate_examples)
        if examples_limit:
            examples_sql = build_duplicate_examples_sql(table_ref, grain_columns, examples_limit)
            example_columns, example_rows, examples_meta = execute_query(
                examples_sql,
                config,
                timeout=args.timeout,
                max_rows=examples_limit,
            )
            if example_rows:
                print()
                print("Duplicate grain examples")
                format_output(example_columns, example_rows, fmt=args.format, no_save=True)
            print(f"Duplicate example duration: {format_duration(examples_meta['duration_secs'])}", file=sys.stderr)


def get_columns(database, schema, table_name, config, args):
    sql = f"""
    ------------------------------------------------------------------------------------------------------------------------
    -- Column metadata for table profiling
    -- Purpose: Identify columns and data types before generating read-only profiling SQL.
    ------------------------------------------------------------------------------------------------------------------------
    SELECT  ordinal_position,
            column_name,
            data_type,
            is_nullable
    FROM    {qualified_name(database=database, schema="INFORMATION_SCHEMA", name="COLUMNS")}
    WHERE   table_schema = {sql_literal(schema.upper())}
    AND     table_name = {sql_literal(table_name)}
    ORDER   BY ordinal_position
    """
    result_columns, rows, _ = execute_query(sql, config, timeout=args.timeout, max_rows=args.max_rows)
    return [dict(zip(result_columns, row)) for row in rows]


def select_columns(columns, requested):
    if not requested:
        return columns
    requested_names = {column.upper() for column in parse_column_list(requested)}
    return [column for column in columns if column["column_name"].upper() in requested_names]


def parse_column_list(value):
    return [part.strip() for part in value.split(",") if part.strip()]


def build_summary_sql(database, schema, table_name):
    return f"""
    ------------------------------------------------------------------------------------------------------------------------
    -- Table summary for profiling
    -- Purpose: Report row count and storage metadata from Snowflake INFORMATION_SCHEMA.
    ------------------------------------------------------------------------------------------------------------------------
    SELECT  table_schema,
            table_name,
            table_type,
            row_count,
            bytes,
            created,
            last_altered
    FROM    {qualified_name(database=database, schema="INFORMATION_SCHEMA", name="TABLES")}
    WHERE   table_schema = {sql_literal(schema.upper())}
    AND     table_name = {sql_literal(table_name)}
    """


def build_column_profile_sql(table_ref, columns):
    aggregate_expressions = ["COUNT(*) AS row_count"]
    selects = []
    for index, column in enumerate(columns, start=1):
        column_name = column["column_name"]
        column_ref = quote_ident(column_name)
        null_alias = f"c{index}_null_count"
        distinct_alias = f"c{index}_approx_distinct"
        aggregate_expressions.append(f"COUNT_IF({column_ref} IS NULL) AS {null_alias}")
        aggregate_expressions.append(f"APPROX_COUNT_DISTINCT({column_ref}) AS {distinct_alias}")
        selects.append(
            "SELECT "
            f"{sql_literal(column_name)} AS column_name, "
            f"{sql_literal(column['data_type'])} AS data_type, "
            f"{sql_literal(column['is_nullable'])} AS is_nullable, "
            "row_count, "
            f"{null_alias} AS null_count, "
            f"ROUND(100 * {null_alias} / NULLIF(row_count, 0), 2) AS null_pct, "
            f"{distinct_alias} AS approx_distinct_count "
            "FROM profile"
        )

    aggregate_sql = ",\n                ".join(aggregate_expressions)
    profile_select_sql = " UNION ALL ".join(selects)
    return f"""
    ------------------------------------------------------------------------------------------------------------------------
    -- Column profile
    -- Purpose: Calculate row count, null percentage, and approximate distinct count per selected column.
    ------------------------------------------------------------------------------------------------------------------------
    WITH profile AS (
        SELECT  {aggregate_sql}
        FROM    {table_ref}
    )
    {profile_select_sql}
    ORDER BY column_name
    """


def build_grain_summary_sql(table_ref, grain_columns):
    grain_refs = [quote_ident(column["column_name"]) for column in grain_columns]
    null_predicate = " OR ".join(f"{column_ref} IS NULL" for column_ref in grain_refs)
    return f"""
    ------------------------------------------------------------------------------------------------------------------------
    -- Grain validation summary
    -- Purpose: Check whether the supplied grain columns are non-null and unique.
    ------------------------------------------------------------------------------------------------------------------------
    WITH grain_counts AS (
        SELECT  {", ".join(grain_refs)},
                COUNT(*) AS row_count
        FROM    {table_ref}
        GROUP   BY {", ".join(grain_refs)}
    ),
    duplicate_summary AS (
        SELECT  COUNT_IF(row_count > 1) AS duplicate_grain_values,
                COALESCE(SUM(IFF(row_count > 1, row_count, 0)), 0) AS duplicate_rows
        FROM    grain_counts
    ),
    base_summary AS (
        SELECT  COUNT(*) AS total_rows,
                COUNT_IF({null_predicate}) AS rows_with_null_grain
        FROM    {table_ref}
    )
    SELECT  total_rows,
            rows_with_null_grain,
            duplicate_grain_values,
            duplicate_rows,
            IFF(rows_with_null_grain = 0 AND duplicate_grain_values = 0, 'PASS', 'FAIL') AS grain_status
    FROM    base_summary
            CROSS JOIN duplicate_summary
    """


def build_duplicate_examples_sql(table_ref, grain_columns, limit):
    grain_refs = [quote_ident(column["column_name"]) for column in grain_columns]
    return f"""
    ------------------------------------------------------------------------------------------------------------------------
    -- Duplicate grain examples
    -- Purpose: Show sample grain values that occur more than once.
    ------------------------------------------------------------------------------------------------------------------------
    SELECT  {", ".join(grain_refs)},
            COUNT(*) AS row_count
    FROM    {table_ref}
    GROUP   BY {", ".join(grain_refs)}
    HAVING  COUNT(*) > 1
    ORDER   BY row_count DESC
    LIMIT   {limit}
    """


if __name__ == "__main__":
    main()
