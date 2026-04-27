#!/usr/bin/env python3
"""Interactive setup wizard for the Snowflake skill."""

import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import sysconfig
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.client import CONFIG_DIR, CONFIG_FILE, apply_ca_bundle, save_config

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
    config = {
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
    if defaults.get("ca_bundle"):
        config["ca_bundle"] = defaults["ca_bundle"]
    return config


def python_runtime_notes():
    print(f"  Python: {sys.executable}")
    print(f"  SSL: {ssl.OPENSSL_VERSION}")
    check_expat_runtime()
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


def pyexpat_extension_path():
    suffix = sysconfig.get_config_var("EXT_SUFFIX") or ""
    stdlib = Path(sysconfig.get_path("stdlib"))
    candidate = stdlib / "lib-dynload" / f"pyexpat{suffix}"
    return candidate if candidate.exists() else None


def check_expat_runtime():
    """Detect the Homebrew Python pyexpat/libexpat mismatch before pip crashes."""
    result = subprocess.run(
        [sys.executable, "-c", "from xml.parsers import expat; print(expat.EXPAT_VERSION)"],
        text=True,
        capture_output=True,
        timeout=10,
    )
    if result.returncode == 0:
        print(f"  expat: {result.stdout.strip()}")
        return

    print()
    print("  WARNING: This Python cannot import xml.parsers.expat.")
    print("  pip may fail before installing the Snowflake connector.")
    if result.stderr.strip():
        print("  Python error:")
        for line in result.stderr.strip().splitlines():
            print(f"    {line}")

    pyexpat_path = pyexpat_extension_path()
    brew_expat = Path("/opt/homebrew/opt/expat/lib/libexpat.1.dylib")
    install_name_tool = shutil.which("install_name_tool")
    codesign = shutil.which("codesign")

    if pyexpat_path and brew_expat.exists() and install_name_tool and codesign:
        print()
        print("  A common Homebrew fix is to link pyexpat to Homebrew's expat and re-sign it.")
        choice = prompt("Apply this pyexpat fix now? (y/N)", "N", required=False).lower()
        if choice in {"y", "yes"}:
            subprocess.check_call(
                [
                    install_name_tool,
                    "-change",
                    "/usr/lib/libexpat.1.dylib",
                    str(brew_expat),
                    str(pyexpat_path),
                ]
            )
            subprocess.check_call([codesign, "--force", "--sign", "-", str(pyexpat_path)])
            retry = subprocess.run(
                [sys.executable, "-c", "from xml.parsers import expat; print(expat.EXPAT_VERSION)"],
                text=True,
                capture_output=True,
                timeout=10,
            )
            if retry.returncode == 0:
                print(f"  expat fixed: {retry.stdout.strip()}")
                return
            print("  ERROR: pyexpat still fails after the fix.")
            if retry.stderr.strip():
                print(retry.stderr.strip())
            sys.exit(1)

    if pyexpat_path and brew_expat.exists():
        print()
        print("  Manual fix:")
        print(
            "    install_name_tool -change /usr/lib/libexpat.1.dylib "
            f"{brew_expat} {pyexpat_path}"
        )
        print(f"    codesign --force --sign - {pyexpat_path}")


def externally_managed_python():
    marker = Path(sysconfig.get_path("stdlib")) / "EXTERNALLY-MANAGED"
    return marker.exists()


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
        pip_args = [sys.executable, "-m", "pip", "install", "snowflake-connector-python"]
        if externally_managed_python():
            print()
            print("  This Python is externally managed, so global pip installs are blocked.")
            print("  Installing into the user package directory instead.")
            pip_args = [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--user",
                "--break-system-packages",
                "snowflake-connector-python",
            ]
        subprocess.check_call(pip_args)
        print("  Restarting setup so Python can see the newly installed package...")
        os.execv(sys.executable, [sys.executable, *sys.argv])
    else:
        print("  Install later with: python -m pip install snowflake-connector-python")
        sys.exit(1)


def connection_failure_help(exc):
    text = str(exc).lower()
    print(f"  ERROR: Connection test failed: {exc}")
    if "390190" in text or "saml identity provider account parameter" in text:
        print()
        print("  Troubleshooting:")
        print("  - Python, connector installation, and TLS reached Snowflake successfully.")
        print("  - Snowflake rejected the browser SSO flow because the IdP account URL/configuration does not match.")
        print("  - Re-copy the account identifier from Snowsight > View account details > Config File.")
        print("  - If the account URL includes a region, cloud, or privatelink suffix, include it in the account identifier.")
        print("  - Ask a Snowflake admin to verify the SAML integration issuer/ACS URL or legacy")
        print("    SAML_IDENTITY_PROVIDER account parameter matches the account URL used by the connector.")
    elif any(marker in text for marker in ["certificate verify failed", "bad handshake", "notopensslwarning"]):
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


def is_certificate_verify_failure(exc):
    text = str(exc).lower()
    return "certificate verify failed" in text or "sslcertverificationerror" in text


def keychain_certificates(common_name):
    security = shutil.which("security")
    if not security:
        return ""
    result = subprocess.run(
        [security, "find-certificate", "-a", "-c", common_name, "-p"],
        text=True,
        capture_output=True,
    )
    return result.stdout if result.returncode == 0 else ""


def create_ca_bundle_from_keychain(common_name="Cisco"):
    try:
        import certifi
    except ImportError:
        print("  ERROR: certifi is not installed, so a CA bundle cannot be created.")
        return None

    extra_certs = keychain_certificates(common_name).strip()
    if not extra_certs:
        print(f"  No macOS Keychain certificates found matching: {common_name}")
        return None

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    bundle = CONFIG_DIR / "cacert.pem"
    base_certs = Path(certifi.where()).read_text()
    bundle.write_text(
        base_certs.rstrip()
        + "\n\n# Extra certificates from macOS Keychain for Snowflake connectivity\n"
        + extra_certs
        + "\n"
    )
    return bundle


def maybe_retry_with_keychain_ca(exc, config):
    if not is_certificate_verify_failure(exc):
        return False

    print()
    print("  Certificate verification failed.")
    print("  If your network uses Cisco Secure Access or similar TLS inspection,")
    print("  Snowflake's requests stack may need a CA bundle that includes that root certificate.")
    choice = prompt(
        "Create Snowflake CA bundle from certifi + Cisco Keychain certificates and retry? (Y/n)",
        "Y",
        required=False,
    ).lower()
    if choice not in {"", "y", "yes"}:
        return False

    bundle = create_ca_bundle_from_keychain("Cisco")
    if not bundle:
        return False

    config["ca_bundle"] = str(bundle)
    apply_ca_bundle(config)
    print(f"  Using CA bundle: {bundle}")
    save_config(config)
    print(f"  Saved interim config to {CONFIG_FILE}")
    return True


def test_connection(config):
    apply_ca_bundle(config)
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
        if maybe_retry_with_keychain_ca(exc, config):
            try:
                result = test_connection(config)
            except Exception as retry_exc:
                connection_failure_help(retry_exc)
                sys.exit(1)
        else:
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
