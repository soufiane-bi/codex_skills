#!/usr/bin/env python3
"""Interactive setup wizard for the Snowflake skill."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.client import CONFIG_FILE, save_config


def prompt(message, default=None, required=True):
    if default:
        value = input(f"  {message} [{default}]: ").strip() or default
    else:
        value = input(f"  {message}: ").strip()
    if required and not value:
        print(f"  ERROR: {message} is required")
        return prompt(message, default, required)
    return value


def load_existing_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def ensure_connector():
    try:
        import snowflake.connector  # noqa: F401
        print("  snowflake-connector-python is installed")
        return
    except ImportError:
        pass

    print("  snowflake-connector-python is not installed")
    choice = prompt("Install it now with pip? (Y/n)", "Y", required=False).lower()
    if choice in {"", "y", "yes"}:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "snowflake-connector-python"])
    else:
        print("  Install later with: python -m pip install snowflake-connector-python")
        sys.exit(1)


def test_connection(config):
    import snowflake.connector

    kwargs = {
        "account": config["account"],
        "user": config["user"],
        "authenticator": config["authenticator"],
    }
    for key in ["warehouse", "database", "schema", "role"]:
        if config.get(key):
            kwargs[key] = config[key]

    connection = snowflake.connector.connect(**kwargs)
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                SELECT CURRENT_USER() AS connected_user,
                       CURRENT_ACCOUNT() AS account_name,
                       CURRENT_ROLE() AS role_name,
                       CURRENT_WAREHOUSE() AS warehouse_name,
                       CURRENT_DATABASE() AS database_name,
                       CURRENT_SCHEMA() AS schema_name
                """
            )
            row = cursor.fetchone()
            columns = [col[0].lower() for col in cursor.description]
        finally:
            cursor.close()
    finally:
        connection.close()
    return dict(zip(columns, row))


def main():
    print("=" * 44)
    print("  Snowflake Skill Setup")
    print("=" * 44)
    print()
    print("This setup uses browser SSO and stores no password.")
    print()

    print("Step 1: Checking Python dependency")
    ensure_connector()
    print()

    existing = load_existing_config()
    config = {
        "python": sys.executable,
        "account": prompt("Snowflake account identifier", existing.get("account")),
        "user": prompt("Username/email", existing.get("user")),
        "warehouse": prompt("Default warehouse", existing.get("warehouse"), required=False),
        "database": prompt("Default database", existing.get("database"), required=False),
        "schema": prompt("Default schema", existing.get("schema"), required=False),
        "role": prompt("Default role", existing.get("role"), required=False),
        "authenticator": prompt("Authenticator", existing.get("authenticator", "externalbrowser")),
    }

    print()
    print("Step 2: Testing connection")
    print("A browser window may open. Complete SSO there, then return to this terminal.")
    try:
        result = test_connection(config)
    except Exception as exc:
        print(f"  ERROR: Connection test failed: {exc}")
        sys.exit(1)

    print("  Connected successfully:")
    for key, value in result.items():
        print(f"    {key}: {value}")

    save_config(config)
    print()
    print(f"Saved config to {CONFIG_FILE}")
    print("Setup complete.")


if __name__ == "__main__":
    main()
