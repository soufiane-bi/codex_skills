# codex_skills

Shared Codex skills.

## Available Skills

### Snowflake

Read-only Snowflake querying, metadata exploration, table profiling, and validation using either programmatic access token (PAT) authentication or browser SSO.

Install from GitHub:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo soufiane-bi/codex_skills \
  --path skills/snowflake
```

Or install from a GitHub URL:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --url https://github.com/soufiane-bi/codex_skills/tree/main/skills/snowflake
```

After installing, restart Codex so the new skill appears in the available skills list.

First-time setup:

```bash
cd ~/.codex/skills/snowflake
python3 scripts/setup.py
```

The setup wizard asks for:

- Snowflake account identifier
- Username/email
- Default warehouse
- Default database
- Default schema
- Default role
- Authentication method:
  - Programmatic access token, recommended when SSO is not enabled
  - Browser connection, for Snowflake SSO/federated authentication only
- Whether to test the connection now

No password or PAT is stored in config. On macOS, PAT/password prompts use a hidden popup by default and fall back to a hidden terminal prompt when needed. The popup explains that the PAT is only saved for the current session and is not written to config or Keychain.

For repeated commands in one terminal session:

```bash
cd ~/.codex/skills/snowflake
python3 scripts/session.py
```

Paste the PAT into the popup once. Commands launched from that temporary shell can use Snowflake until the shell is closed.
