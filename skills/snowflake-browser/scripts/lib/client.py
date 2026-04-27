"""Snowflake connector helpers, config, read-only guard, and query execution."""

import argparse
import getpass
import json
import os
import re
import sys
import time
from pathlib import Path

CONFIG_DIR = Path.home() / ".snowflake-skill"
CONFIG_FILE = CONFIG_DIR / "config.json"

ALLOWED_KEYWORDS = {"SELECT", "WITH", "SHOW", "DESCRIBE", "DESC", "EXPLAIN"}
DANGEROUS_KEYWORDS = {
    "ALTER",
    "BEGIN",
    "CALL",
    "COMMIT",
    "COPY",
    "CREATE",
    "DELETE",
    "DROP",
    "GET",
    "GRANT",
    "INSERT",
    "MERGE",
    "PUT",
    "REMOVE",
    "REVOKE",
    "ROLLBACK",
    "SET",
    "TRUNCATE",
    "UPDATE",
    "USE",
}


def load_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def save_config(config):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(sanitized_config(config), indent=2) + "\n")


def sanitized_config(config):
    blocked_keys = {"password", "token", "pat", "programmatic_access_token"}
    return {
        key: value
        for key, value in config.items()
        if key not in blocked_keys and not key.startswith("_")
    }


def apply_ca_bundle(config):
    ca_bundle = config.get("ca_bundle")
    if not ca_bundle:
        return
    ca_path = Path(ca_bundle).expanduser()
    if not ca_path.exists():
        raise RuntimeError(f"Configured CA bundle does not exist: {ca_path}")
    os.environ["REQUESTS_CA_BUNDLE"] = str(ca_path)
    os.environ["SSL_CERT_FILE"] = str(ca_path)


def add_connection_args(parser):
    parser.add_argument("--account", help="Snowflake account identifier")
    parser.add_argument("--user", help="Snowflake username/email")
    parser.add_argument("--warehouse", help="Snowflake warehouse")
    parser.add_argument("--database", help="Snowflake database")
    parser.add_argument("--schema", help="Snowflake schema")
    parser.add_argument("--role", help="Snowflake role")
    parser.add_argument("--authenticator", help="Authenticator, default snowflake for username/password or PAT")
    parser.add_argument(
        "--credential-type",
        choices=["programmatic_access_token", "password"],
        help="Credential prompt/env-var type for username/password auth",
    )
    parser.add_argument("--format", choices=["txt", "csv", "json"], default="txt", help="Terminal output format")
    parser.add_argument("--save-format", dest="save_format", choices=["txt", "csv", "json"], default="csv")
    parser.add_argument("--timeout", type=int, default=120, help="Query timeout seconds")
    parser.add_argument("--max-rows", dest="max_rows", type=int, default=1000, help="Maximum rows to fetch")
    parser.add_argument("--save", help="Save output to a file path")
    parser.add_argument("--no-save", dest="no_save", action="store_true", help="Do not auto-save results")
    parser.add_argument("--save-sql", dest="save_sql", action="store_true", help="Save SQL next to result file")


def resolve_config(args):
    config = load_config()
    for key in ["account", "user", "warehouse", "database", "schema", "role", "authenticator", "credential_type"]:
        value = getattr(args, key, None)
        if value:
            config[key] = value

    config.setdefault("authenticator", "snowflake")
    missing = [key for key in ["account", "user"] if not config.get(key)]
    if missing:
        print(f"ERROR: Missing connection parameter(s): {', '.join(missing)}", file=sys.stderr)
        print(f"Run setup first: python {Path(__file__).resolve().parent.parent / 'setup.py'}", file=sys.stderr)
        sys.exit(1)
    return config


def validate_sql(sql):
    """Block writes, session changes, and multi-statement SQL."""
    clean = _strip_comments(sql).strip()
    if not clean:
        raise ValueError("Empty SQL statement")

    if re.search(r";\s*\S", clean):
        raise ValueError("Multi-statement SQL is not allowed")
    clean = re.sub(r";\s*$", "", clean).strip()

    first_keyword = clean.split()[0].upper().rstrip("(")
    if first_keyword not in ALLOWED_KEYWORDS:
        allowed = ", ".join(sorted(ALLOWED_KEYWORDS))
        raise ValueError(f"Blocked statement type: {first_keyword}. Only read-only statements are allowed: {allowed}")

    searchable = _mask_literals(clean)
    tokens = {token.upper() for token in re.findall(r"\b[A-Za-z_][A-Za-z0-9_$]*\b", searchable)}
    blocked = sorted(tokens & DANGEROUS_KEYWORDS)
    if blocked:
        raise ValueError(f"Blocked potentially unsafe keyword(s): {', '.join(blocked)}")


def connect(config):
    apply_ca_bundle(config)
    try:
        import snowflake.connector
    except ImportError as exc:
        raise RuntimeError(
            "snowflake-connector-python is not installed. Run scripts/setup.py first."
        ) from exc

    authenticator = (config.get("authenticator") or "snowflake").lower()
    kwargs = {
        "account": config.get("account"),
        "user": config.get("user"),
    }
    if password_authenticator(config):
        kwargs["password"] = resolve_password(config)
        if authenticator not in {"snowflake", "password", "programmatic_access_token"}:
            kwargs["authenticator"] = authenticator
    else:
        kwargs["authenticator"] = authenticator
    for key in ["warehouse", "database", "schema", "role"]:
        if config.get(key):
            kwargs[key] = config[key]
    return snowflake.connector.connect(**kwargs)


def password_authenticator(config):
    authenticator = (config.get("authenticator") or "snowflake").lower()
    return authenticator in {"snowflake", "password", "programmatic_access_token", "username_password_mfa"}


def resolve_password(config):
    for key in ["_password", "password", "_token", "token", "pat", "programmatic_access_token"]:
        if config.get(key):
            return config[key]

    credential_type = config.get("credential_type", "programmatic_access_token")
    env_names = ["SNOWFLAKE_PASSWORD"]
    if credential_type == "programmatic_access_token":
        env_names = ["SNOWFLAKE_PAT", "SNOWFLAKE_PASSWORD"]
    for env_name in env_names:
        if os.environ.get(env_name):
            return os.environ[env_name]

    if sys.stdin.isatty():
        label = "programmatic access token" if credential_type == "programmatic_access_token" else "password"
        return getpass.getpass(f"Snowflake {label} for {config.get('user')}: ")

    env_hint = "SNOWFLAKE_PAT or SNOWFLAKE_PASSWORD" if credential_type == "programmatic_access_token" else "SNOWFLAKE_PASSWORD"
    raise RuntimeError(
        f"Snowflake {credential_type} is required. Set {env_hint}, or rerun setup in an interactive terminal."
    )


def execute_query(sql, config, timeout=120, max_rows=1000):
    validate_sql(sql)
    started = time.time()
    connection = connect(config)
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(sql, timeout=timeout)
            description = cursor.description or []
            columns = [col[0] for col in description]
            rows = cursor.fetchmany(max_rows) if columns else []
        finally:
            cursor.close()
    finally:
        connection.close()

    return columns, rows, {
        "duration_secs": time.time() - started,
        "total_rows": len(rows),
    }


def sql_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def quote_ident(identifier):
    if identifier is None or str(identifier).strip() == "":
        raise ValueError("Identifier cannot be empty")
    text = str(identifier).strip()
    return '"' + text.replace('"', '""') + '"'


def qualified_name(database=None, schema=None, name=None):
    parts = [part for part in [database, schema, name] if part]
    return ".".join(quote_ident(part) for part in parts)


def _strip_comments(sql):
    no_line = re.sub(r"--[^\n]*", "", sql)
    return re.sub(r"/\*.*?\*/", "", no_line, flags=re.DOTALL)


def _mask_literals(sql):
    sql = re.sub(r"'(?:''|[^'])*'", "''", sql)
    sql = re.sub(r"\$\$.*?\$\$", "$$", sql, flags=re.DOTALL)
    return sql
