---
name: snowflake
description: Query Snowflake safely using browser SSO authentication. Use whenever the user mentions Snowflake, Snowflake SQL, warehouse/database/schema exploration, table metadata, DDL, sample data, query execution, or business analysis backed by Snowflake. Always use this skill for Snowflake-related tasks and enforce read-only SQL guardrails.
---

# Snowflake Skill

Read-only Snowflake exploration and business analysis using the Snowflake Python connector with browser authentication (`externalbrowser`).

All scripts are in the skill's `scripts/` folder and require Python 3. The setup wizard installs `snowflake-connector-python` if it is missing.

## Python Command

Read `~/.snowflake-skill/config.json` and use the `"python"` key as the Python command. If config does not exist yet, try `python3 --version`, then `python --version`.

Throughout this document, `PYTHON` means the detected Python command.

## First-Time Setup

The setup wizard is interactive and opens a browser for SSO, so ask the user to run it in their terminal:

```bash
python3 scripts/setup.py
```

The wizard asks for:

- Snowflake account identifier, such as `orgname-accountname` or an account locator
- Username or email
- Default warehouse
- Default database
- Default schema
- Default role
- Authenticator, defaulted to `externalbrowser`

It saves non-password connection details to `~/.snowflake-skill/config.json`. It does not store a password.

## Quick Reference

| Task | Script | Key Args |
|------|--------|----------|
| Run SQL | `query.py` | `"SELECT ..."` or `--sql-file=PATH` |
| List schemas | `schemas.py` | `[--database=NAME]` |
| List tables/views | `tables.py` | `--schema=NAME [--database=NAME] [--pattern=TEXT]` |
| List columns | `columns.py` | `--schema=NAME --table=NAME [--database=NAME]` |
| Sample rows | `sample.py` | `--schema=NAME --table=NAME [--limit=N]` |
| Get DDL | `ddl.py` | `--type=table|view --schema=NAME --name=NAME` |
| Search objects | `search.py` | `--pattern=TEXT [--database=NAME]` |

Common options:

| Option | Description |
|--------|-------------|
| `--account` | Override Snowflake account identifier |
| `--user` | Override Snowflake user |
| `--warehouse` | Override default warehouse |
| `--database` | Override default database |
| `--schema` | Override default schema |
| `--role` | Override default role |
| `--format=txt|csv|json` | Terminal display format, default `txt` |
| `--save-format=txt|csv|json` | Saved file format, default `csv` |
| `--save=PATH` | Save results to a specific path |
| `--no-save` | Do not auto-save results |
| `--save-sql` | Save SQL alongside results |
| `--timeout=N` | Query timeout seconds, default `120` |
| `--max-rows=N` | Maximum rows to fetch, default `1000` |

## Output and File Saving

Query results are automatically saved to `~/snowflake-exports/query-{timestamp}.csv`, unless `--no-save` is used. The terminal shows an aligned preview for quick inspection. Use `--save-sql` to save the SQL alongside the result file.

## Defensive Guardrails

The scripts enforce read-only SQL:

- Allowed statement starters: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `DESC`, `EXPLAIN`
- Blocked statement types include: `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `CREATE`, `DROP`, `ALTER`, `TRUNCATE`, `COPY`, `PUT`, `GET`, `REMOVE`, `CALL`, `GRANT`, `REVOKE`, `BEGIN`, `COMMIT`, `ROLLBACK`, `USE`, `SET`
- Multi-statement SQL is blocked
- Do not run unbounded raw data queries on large tables; use filters, aggregations, or `sample.py`
- Always add `LIMIT` when exploring unfamiliar tables
- Check table and column metadata before building larger joins

## SQL Standards

Every Snowflake query you write should be readable and reviewable:

- Add a short header comment explaining purpose, sources, and assumptions
- Use CTE names that describe the business concept
- Put one selected column per line
- Show the SQL to the user before or while running it
- For long SQL, save a `.sql` file and run `query.py --sql-file=...`

Example:

```sql
------------------------------------------------------------------------------------------------------------------------
-- Monthly stock value by supplier
-- Purpose: Summarise stock value by month and supplier for working capital analysis
-- Assumptions: Uses end-of-month snapshots and excludes suppliers with no stock
------------------------------------------------------------------------------------------------------------------------
WITH monthly_stock AS (
    SELECT  period,
            supplier_sk,
            SUM(stock_value) AS stock_value
    FROM    analytics.working_capital.stock_supplier_monthly
    WHERE   period >= DATEADD(month, -12, CURRENT_DATE)
    GROUP   BY 1, 2
)
SELECT  period,
        supplier_sk,
        stock_value
FROM    monthly_stock
ORDER   BY period,
          supplier_sk;
```
