#!/usr/bin/env python3
"""Interactive setup wizard for the Snowflake skill."""

import json
import os
import re
import shutil
import ssl
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.client import CONFIG_FILE, save_config

SKILL_DIR = Path(__file__).resolve().parent.parent
SETTINGS_GUIDE = SKILL_DIR / "references" / "snowflake-account-settings.md"
SETTINGS_VISUAL = SKILL_DIR / "assets" / "snowsight-config-file-screen.svg"
SNOWFLAKE_ACCOUNT_DOCS_URL = (
    "https://docs.snowflake.com/en/user-guide/admin-account-identifier"
    "#finding-the-organization-and-account-name-for-an-account"
)
CONFIG_KEYS = {"account", "user", "warehouse", "database", "schema", "role", "authenticator"}


def prompt(message, default=None, required=True, help_callback=None):
    if default:
        value = input(f"  {message} [{default}]: ").strip() or default
    else:
        value = input(f"  {message}: ").strip()
    if value == "?" and help_callback:
        help_callback()
        return prompt(message, default, required, help_callback)
    if required and not value:
        print(f"  ERROR: {message} is required")
        return prompt(message, default, required, help_callback)
    return value


def load_existing_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def print_settings_help():
    print()
    print("  [info] Need help finding these Snowflake settings?")
    print("  In Snowsight:")
    print("    1. Select the account selector for your signed-in account.")
    print("    2. Select View account details.")
    print("    3. Open the Config File tab.")
    print("    4. Fill in warehouse, database, schema, and role if needed.")
    print("    5. Copy the generated [connections.<name>] block and paste it here.")
    print()
    print(f"  Snowflake docs: {SNOWFLAKE_ACCOUNT_DOCS_URL}")
    if SETTINGS_GUIDE.exists():
        print(f"  Local guide: {SETTINGS_GUIDE}")
    if SETTINGS_VISUAL.exists():
        print(f"  Visual guide: {SETTINGS_VISUAL}")
    print()
    print("  Tip: type ? at any connection prompt to show this help again.")
    print()


def parse_config_block(text):
    config = {}
    for line in text.splitlines():
        match = re.match(r'\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"(.*)"\s*$', line)
        if not match:
            continue
        key, value = match.groups()
        key = key.lower()
        if key in CONFIG_KEYS:
            config[key] = value.replace('\\"', '"')
    return config


def read_pasted_config_block():
    print()
    print("  Paste the Snowflake [connections.<name>] config block.")
    print("  Press Enter on a blank line when finished.")
    lines = []
    while True:
        line = input()
        if not line.strip():
            break
        lines.append(line)
    parsed = parse_config_block("\n".join(lines))
    if parsed:
        found = ", ".join(sorted(parsed))
        print(f"  Parsed settings: {found}")
    else:
        print("  No connection settings found in pasted block; continuing with manual prompts.")
    return parsed


def collect_connection_config(existing):
    print_settings_help()
    paste_choice = prompt(
        "Paste Snowflake config block now? (y/N)",
        "N",
        required=False,
        help_callback=print_settings_help,
    ).lower()
    pasted = read_pasted_config_block() if paste_choice in {"y", "yes"} else {}
    defaults = {**existing, **pasted}
    return {
        "python": sys.executable,
        "account": prompt("Snowflake account identifier", defaults.get("account"), help_callback=print_settings_help),
        "user": prompt("Username/email", defaults.get("user"), help_callback=print_settings_help),
        "warehouse": prompt(
            "Default warehouse",
            defaults.get("warehouse"),
            required=False,
            help_callback=print_settings_help,
        ),
        "database": prompt(
            "Default database",
            defaults.get("database"),
            required=False,
            help_callback=print_settings_help,
        ),
        "schema": prompt("Default schema", defaults.get("schema"), required=False, help_callback=print_settings_help),
        "role": prompt("Default role", defaults.get("role"), required=False, help_callback=print_settings_help),
        "authenticator": prompt(
            "Authenticator",
            defaults.get("authenticator", "externalbrowser"),
            help_callback=print_settings_help,
        ),
    }


def python_runtime_notes():
    print(f"  Python: {sys.executable}")
    print(f"  SSL: {ssl.OPENSSL_VERSION}")
    if "LibreSSL" not in ssl.OPENSSL_VERSION:
        return

    print()
    print("  WARNING: This Python is linked against LibreSSL.")
    print("  The Snowflake connector can fail SSO or TLS handshakes with Apple's")
    print("  CommandLineTools Python. Prefer a Homebrew Python linked to OpenSSL 3.")
    for candidate in [
        "/opt/homebrew/bin/python3.12",
        "/opt/homebrew/bin/python3.11",
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3.12",
        "/usr/local/bin/python3.11",
        "/usr/local/bin/python3",
    ]:
        if Path(candidate).exists():
            print(f"  Found possible alternative: {candidate}")
            print(f"  Retry with: {candidate} {Path(__file__).resolve()}")
            break
    else:
        brew = shutil.which("brew") or "/opt/homebrew/bin/brew"
        print(f"  Install one with: {brew} install python@3.12")


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
        print("  Restarting setup so Python can see the newly installed package...")
        os.execv(sys.executable, [sys.executable, *sys.argv])
    else:
        print("  Install later with: python -m pip install snowflake-connector-python")
        sys.exit(1)


def connection_failure_help(exc):
    text = str(exc).lower()
    print(f"  ERROR: Connection test failed: {exc}")
    if any(marker in text for marker in ["certificate verify failed", "bad handshake", "notopensslwarning"]):
        print()
        print("  Troubleshooting:")
        print("  - If this Python reports LibreSSL above, rerun setup with Homebrew Python 3.11+ or 3.12.")
        print("  - On Apple CommandLineTools Python, the connector can fail even when simple HTTPS works.")
        print("  - If you are on a corporate network, make sure the Snowflake host is trusted by this Python runtime.")
    elif "no module named 'snowflake'" in text:
        print()
        print("  Troubleshooting:")
        print("  - The connector was installed into a user site that this process did not load.")
        print("  - Rerun setup in a fresh terminal or use the Python printed at the top of this setup.")
    elif "externalbrowser" in text or "browser" in text:
        print()
        print("  Troubleshooting:")
        print("  - Complete the browser SSO prompt, then return to this terminal.")
        print("  - If no browser opens, run setup directly in your local terminal.")


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
    python_runtime_notes()
    ensure_connector()
    print()

    existing = load_existing_config()
    config = collect_connection_config(existing)

    print()
    print("Step 2: Testing connection")
    print("A browser window may open. Complete SSO there, then return to this terminal.")
    try:
        result = test_connection(config)
    except Exception as exc:
        connection_failure_help(exc)
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
