# Security Policy

## Sensitive Data Handling

DevIntent AI processes GitHub user data (usernames, public emails, company names) from public GitHub profiles. All data is stored locally in SQLite and CSV files — never transmitted to third-party services except for LLM classification via OpenRouter.

**Never commit the following to version control:**
- `.env` files containing API keys
- `data/*.db` SQLite databases containing lead records
- `data/*.csv` CSV exports containing enriched lead data
- `logs/*.log` pipeline log files

All of the above are listed in `.gitignore`.

## API Key Security

- **GitHub PAT:** Use a fine-grained token with `public_repo` read-only scope. Rotate immediately if exposed.
- **OpenRouter Key:** Scope to minimum required permissions. Rotate immediately if exposed.

If you accidentally commit a key, revoke it immediately at:
- GitHub: https://github.com/settings/tokens
- OpenRouter: https://openrouter.ai/keys

## Responsible Use

This tool only accesses **public** GitHub data via the official GitHub REST API, in compliance with GitHub's Terms of Service. Do not use this tool to scrape private repositories or violate any platform's terms of service.

## Reporting a Vulnerability

To report a security issue, email [ojack@merkabacreatives.org](mailto:ojack@merkabacreatives.org) with subject line `[SECURITY] DevIntent AI`.
