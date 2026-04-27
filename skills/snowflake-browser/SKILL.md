---
name: snowflake
description: Query Snowflake safely using programmatic access token or browser SSO authentication. Use whenever the user mentions Snowflake, Snowflake SQL, warehouse/database/schema exploration, table metadata, DDL, sample data, query execution, or business analysis backed by Snowflake. Always use this skill for Snowflake-related tasks and enforce read-only SQL guardrails.
---

# Snowflake Skill

Read-only Snowflake exploration and business analysis using the Snowflake Python connector with programmatic access token (PAT) or browser SSO authentication.

All scripts are in the skill's `scripts/` folder and require Python 3. The setup wizard installs `snowflake-connector-python` if it is missing.

## Python Command

Read `~/.snowflake-skill/config.json` and use the `"python"` key as the Python command. If config does not exist yet, try `python3 --version`, then `python --version`.

Before using a Python for Snowflake, check its TLS backend:

```bash
PYTHON -c "import ssl, sys; print(sys.executable); print(ssl.OPENSSL_VERSION)"
```

Prefer Python 3.11+ or 3.12 linked against OpenSSL 3. Apple's CommandLineTools Python can report `LibreSSL 2.8.3`; with the Snowflake connector this may produce `NotOpenSSLWarning`, `bad handshake`, or `certificate verify failed` during external browser SSO even when simple HTTPS requests succeed. If that happens, install or use Homebrew Python:

```bash
/opt/homebrew/bin/brew install python@3.12
/opt/homebrew/bin/python3.12 scripts/setup.py
```

Throughout this document, `PYTHON` means the detected Python command.

## First-Time Setup

The setup wizard is interactive and can test the connection after saving non-secret settings, so ask the user to run it in their terminal:

```bash
python3 scripts/setup.py
```

In Codex, run the setup in an interactive TTY. Non-interactive execution can fail with `EOFError: EOF when reading a line` at the first prompt.

The wizard asks for:

- Snowflake account identifier, such as `orgname-accountname` or an account locator
- Username or email
- Default warehouse
- Default database
- Default schema
- Default role
- Authentication method: two choices only:
  - `Programmatic access token` — recommended when Snowflake SSO is not enabled
  - `Browser connection` — use only when Snowflake SSO/federated authentication is enabled
- Whether to test the Snowflake connection now

It saves non-secret connection details to `~/.snowflake-skill/config.json`. It does not store passwords or tokens. If the user agrees to test the connection, PAT/password auth uses a hidden macOS popup, with terminal fallback, and then reports `CURRENT_USER()`, `CURRENT_ACCOUNT()`, role, warehouse, database, and schema.

All PAT/password prompts are session-only. The popup tells the user: "This PAT is only saved for this session; it is not written to config or Keychain."

For repeated local work without storing a secret, start a temporary terminal session:

```bash
PYTHON scripts/session.py
```

Paste the PAT into the hidden prompt. The helper starts a child shell with `SNOWFLAKE_PAT` set only for that shell and its child commands. Type `exit` when finished and the token is gone from the session. This is the preferred local workflow when the user does not want Keychain storage.

On macOS, `session.py` opens a hidden-input popup by default. Use `--prompt=terminal` only when a terminal prompt is preferred.

To run a single command through the same hidden prompt:

```bash
PYTHON scripts/session.py -- PYTHON scripts/query.py "SELECT CURRENT_USER()"
```

For non-interactive use, provide a fresh secret through the environment:

```bash
export SNOWFLAKE_PAT="..."
```

Programmatic access tokens are used as the Snowflake connector `password` value. They are safer than a real password for local automation because they can be rotated, revoked, and role-restricted. If a user pastes a token into chat or logs, tell them to rotate it and use a fresh token.

If Snowsight shows **Missing network policy** while generating a PAT, instruct the user to either enable the approved temporary network-policy bypass for that token or ask a Snowflake admin to attach a network policy that allows their current network.

On Homebrew Python, setup handles PEP 668's externally-managed Python restriction by installing
`snowflake-connector-python` into the user package directory with `--user --break-system-packages`.
No virtual environment is required for the default setup.

The setup wizard can also parse a Snowflake config block pasted from Snowsight:

```toml
[connections.my_example_connection]
account = "orgname-accountname"
user = "YOUR_USERNAME"
authenticator = "externalbrowser"
role = "ACCOUNTADMIN"
warehouse = "COMPUTE_WH"
database = "DEMO_DWH"
schema = "RETAIL_MART"
```

To find this in Snowsight, open the account selector, choose **View account details**, then select the **Config File** tab. The local guide is `references/snowflake-account-settings.md`, with a small visual guide at `assets/snowsight-config-file-screen.svg`. This path is based on Snowflake's account identifier documentation.

## Setup Troubleshooting

- If `snowflake-connector-python` is installed during setup and the same run later says `No module named 'snowflake'`, rerun `scripts/setup.py` in a fresh Python process. The setup script now restarts itself after installing the connector to avoid this issue.
- If setup prints `NotOpenSSLWarning`, `bad handshake`, or `certificate verify failed`, check the Python SSL backend. On macOS, prefer Homebrew Python linked to OpenSSL 3 instead of `/usr/bin/python3` from CommandLineTools.
- If Homebrew Python fails with `Symbol not found: _XML_SetAllocTrackerActivationThreshold` while importing `pyexpat`, setup detects this before pip runs and can apply the local fix: relink `pyexpat` to Homebrew's `expat` library, then re-sign the extension with `codesign --force --sign -`.
- If pip prints `externally-managed-environment`, do not create a virtual environment by default. The setup script should install with:

```bash
PYTHON -m pip install --user --break-system-packages snowflake-connector-python
```

- If the connector fails with `certificate verify failed` on a corporate network, check whether the server certificate is issued by a local proxy such as Cisco Secure Access. Setup can create `~/.snowflake-skill/cacert.pem` from certifi plus matching macOS Keychain certificates and saves it as `ca_bundle` in config; all Snowflake scripts then set `REQUESTS_CA_BUNDLE` and `SSL_CERT_FILE` automatically.
- If PAT auth fails with `Network policy is required`, Snowflake reached the account but rejected PAT use because programmatic access tokens require an active network policy for the user or account. Attach a network policy that allows the current network, regenerate the token with an approved temporary network-policy bypass if allowed, or use password authentication instead.
- If PAT auth fails with `PAT_INVALID`, generate a fresh token, make sure it belongs to the configured user, check role restrictions, and confirm Snowflake authentication/network policies allow `PROGRAMMATIC_ACCESS_TOKEN`.
- If TLS succeeds but Snowflake returns `390190` mentioning the SAML Identity Provider account parameter, local setup has moved past Python/TLS. Verify the exact Snowflake account identifier from Snowsight, including any region/cloud or `privatelink` suffix in the account URL, and confirm the IdP/SAML issuer/ACS URL or legacy `SAML_IDENTITY_PROVIDER` account parameter matches that account URL; this can require a Snowflake admin-side fix.
- If a plain `requests.get("https://<account>.snowflakecomputing.com")` succeeds but the connector fails, treat it as a connector/runtime compatibility issue first, especially with LibreSSL.
- If Homebrew commands are run from a sandboxed Codex session and fail writing under `~/Library/Caches/Homebrew`, rerun with elevated permission or ask the user to run the Homebrew command directly.
- The connector may warn that `keyring` is not installed and cannot cache the id token. This is optional but useful for fewer SSO prompts:

```bash
PYTHON -m pip install "snowflake-connector-python[secure-local-storage]"
```

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
| Profile table | `profile_table.py` | `--schema=NAME --table=NAME [--grain=COL1,COL2]` |
| Temporary PAT session | `session.py` | `[--credential-type=programmatic_access_token|password] [--prompt=auto|popup|terminal] [-- COMMAND ...]` |

Common options:

| Option | Description |
|--------|-------------|
| `--account` | Override Snowflake account identifier |
| `--user` | Override Snowflake user |
| `--warehouse` | Override default warehouse |
| `--database` | Override default database |
| `--schema` | Override default schema |
| `--role` | Override default role |
| `--authenticator` | Override authenticator, default `snowflake`; use `externalbrowser` only for SSO |
| `--credential-type=programmatic_access_token|password` | Secret type used for connector password auth; setup presents PAT as the normal non-SSO path |
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
- When checking duplicates, only assert uniqueness when the table grain is known. Use `profile_table.py --grain=...` for explicit grain validation.

## Profiling and Validation

Use `profile_table.py` before writing larger analytical SQL or when validating a new dataset. It reports:

- table row count and storage metadata
- per-column null count and null percentage
- per-column approximate distinct count
- optional grain validation when `--grain` is supplied

Example:

```bash
PYTHON scripts/profile_table.py --database DEMO_DWH --schema RETAIL_MART --table FACT_SALES --grain=KNOWN_GRAIN_COL1,KNOWN_GRAIN_COL2
```

Do not infer a primary key or fact-table grain from names alone. If the business grain is unknown, profile the table first, inspect likely key columns, then ask the user before running duplicate-grain assertions.

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
