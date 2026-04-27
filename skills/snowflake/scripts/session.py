#!/usr/bin/env python3
"""Prompt for a Snowflake secret and run commands in a temporary session."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.client import apply_ca_bundle, load_config
from lib.secret_prompt import prompt_snowflake_secret


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Prompt for a Snowflake PAT/password and start a temporary shell, "
            "or run one command, with the secret available only in that child process."
        )
    )
    parser.add_argument(
        "--credential-type",
        choices=["programmatic_access_token", "password"],
        help="Secret type to prompt for. Defaults to config credential_type, then PAT.",
    )
    parser.add_argument(
        "--shell",
        help="Shell to start when no command is supplied. Defaults to $SHELL, zsh, then sh.",
    )
    parser.add_argument(
        "--prompt",
        choices=["auto", "popup", "terminal"],
        default="auto",
        help="Secret prompt style. On macOS, auto uses a hidden popup and falls back to terminal.",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Optional command to run after --, for example: -- python scripts/query.py 'SELECT 1'",
    )
    return parser.parse_args()


def resolve_credential_type(args, config):
    return args.credential_type or config.get("credential_type") or "programmatic_access_token"


def child_environment(config, credential_type, secret):
    apply_ca_bundle(config)
    env = os.environ.copy()
    if credential_type == "programmatic_access_token":
        env["SNOWFLAKE_PAT"] = secret
        env.pop("SNOWFLAKE_PASSWORD", None)
    else:
        env["SNOWFLAKE_PASSWORD"] = secret
        env.pop("SNOWFLAKE_PAT", None)
    return env


def resolve_shell(args):
    return args.shell or os.environ.get("SHELL") or shutil.which("zsh") or shutil.which("sh") or "/bin/sh"


def run_child(args, env):
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]

    if command:
        return subprocess.call(command, env=env)

    shell = resolve_shell(args)
    print()
    print("Starting a temporary Snowflake session shell.")
    print("The secret is available only to this shell and its child commands.")
    print("Type exit when finished.")
    print()
    return subprocess.call([shell, "-i"], env=env)


def main():
    args = parse_args()
    config = load_config()
    credential_type = resolve_credential_type(args, config)
    config["credential_type"] = credential_type
    secret = prompt_snowflake_secret(config, prompt_method=args.prompt)
    try:
        env = child_environment(config, credential_type, secret)
        return run_child(args, env)
    finally:
        secret = None


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
