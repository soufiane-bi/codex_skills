# codex_skills

Shared Codex skills.

## Available Skills

### Snowflake Browser

Read-only Snowflake querying and metadata exploration using browser SSO authentication.

Install from GitHub:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo soufiane-bi/codex_skills \
  --path skills/snowflake-browser
```

Or install from a GitHub URL:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --url https://github.com/soufiane-bi/codex_skills/tree/main/skills/snowflake-browser
```

After installing, restart Codex so the new skill appears in the available skills list.

First-time setup:

```bash
cd ~/.codex/skills/snowflake-browser
python3 scripts/setup.py
```

The setup wizard asks for:

- Snowflake account identifier
- Username/email
- Default warehouse
- Default database
- Default schema
- Default role
- Authenticator, default `externalbrowser`

No password is stored. Browser SSO is used for authentication.
