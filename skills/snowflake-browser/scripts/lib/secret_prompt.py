"""Session-only secret prompts for the Snowflake skill."""

import getpass
import shutil
import subprocess
import sys


def credential_type(config):
    return config.get("credential_type") or "programmatic_access_token"


def credential_label(config):
    if credential_type(config) == "programmatic_access_token":
        return "PAT"
    return "password"


def prompt_snowflake_secret(config, prompt_method="auto"):
    """Prompt for a Snowflake secret without saving it to disk."""
    if prompt_method in {"auto", "popup"}:
        secret = prompt_macos_popup(config)
        if secret:
            return secret
        if prompt_method == "popup":
            raise RuntimeError("macOS popup prompt is unavailable.")

    if prompt_method in {"auto", "terminal"} and sys.stdin.isatty():
        label = "programmatic access token" if credential_type(config) == "programmatic_access_token" else "password"
        secret = getpass.getpass(f"Snowflake {label} for {config.get('user')}: ")
        if secret:
            return secret

    raise RuntimeError("No Snowflake secret was entered.")


def prompt_macos_popup(config):
    if sys.platform != "darwin" or not shutil.which("osascript"):
        return None

    title = f"Snowflake {credential_label(config)}"
    session_text = (
        "This PAT is only saved for this session; it is not written to config or Keychain."
        if credential_type(config) == "programmatic_access_token"
        else "This password is only used for this session; it is not written to config or Keychain."
    )
    message = (
        f"Paste Snowflake {credential_label(config)} for {config.get('user') or 'configured user'}"
        f" on {config.get('account') or 'the configured account'}. "
        + session_text
    )
    script = (
        "set dlg to display dialog "
        + applescript_quote(message)
        + ' default answer "" with hidden answer buttons {"Cancel", "Use"} '
        + 'default button "Use" cancel button "Cancel" with title '
        + applescript_quote(title)
        + "\nreturn text returned of dlg"
    )
    result = subprocess.run(["osascript", "-e", script], text=True, capture_output=True)
    if result.returncode == 0:
        return result.stdout.rstrip("\n")
    if "User canceled" in result.stderr or "-128" in result.stderr:
        raise RuntimeError("Secret entry cancelled.")
    return None


def applescript_quote(value):
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'
