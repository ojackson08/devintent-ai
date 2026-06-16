# DevIntent AI

**GitHub intent signal pipeline for B2B lead generation.**

DevIntent AI monitors stars and forks on high-traffic AI/developer GitHub repositories, enriches each user via the GitHub API, classifies their purchase intent using an LLM, scores them as B2B leads, and exports daily CSVs — fully automated.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Powered by OpenRouter](https://img.shields.io/badge/LLM-OpenRouter-purple)](https://openrouter.ai)

---

## What It Does

```
GitHub Repos (stars/forks)
        ↓
  Signal Ingestion          ← Monitors AutoGPT, Ollama, n8n, Dify, etc.
        ↓
  GitHub API Enrichment     ← Real name, email, company, bio
        ↓
  LLM Classification        ← Intent category + strength score (1–10)
        ↓
  ICP Scoring               ← Composite fit score (0–100)
        ↓
  SQLite Storage + CSV Export ← Daily leads_YYYY-MM-DD.csv
```

---

## Intent Categories

The pipeline classifies each GitHub user into one of five B2B intent buckets:

| Category | Description |
|----------|-------------|
| **AI Coding Agent** | Devin, Cursor, Claude Code, Copilot users |
| **AI Meeting / Productivity** | Otter.ai, Notion AI, meeting automation |
| **Enterprise Knowledge Base** | RAG, search, internal knowledge tools |
| **Developer Infrastructure / DevOps** | CI/CD, observability, platform engineering |
| **Other / Low Intent** | Filtered out below MIN_LEAD_SCORE |

---

## Lead Output Schema

Each exported CSV row contains:

| Field | Description |
|-------|-------------|
| `username` | GitHub username |
| `name` | Real name (from GitHub profile) |
| `email` | Public email (if available) |
| `company` | Company (from GitHub profile) |
| `category` | Intent category |
| `intent_score` | LLM-assigned intent strength (1–10) |
| `icp_score` | Composite ICP fit score (0–100) |
| `repo` | Source repo that triggered the signal |
| `enriched_at` | UTC timestamp |

---

## Project Structure

```
devintent-ai/
├── scripts/
│   ├── run_pipeline.py           # Main pipeline (ingest → classify → export)
│   ├── run_pipeline_improved.py  # Parallel version with ThreadPoolExecutor
│   ├── ingest_v2.py              # Standalone ingestion (no auth fallback)
│   └── test_auth.py              # Validate GitHub + OpenRouter credentials
├── website/
│   └── index.html                # DevIntent AI landing page
├── data/                         # SQLite DB + CSV exports (gitignored)
├── logs/                         # Pipeline run logs (gitignored)
├── .env.example                  # Environment variable template
├── requirements.txt
└── README.md
```

---

## Quick Start

### 1. Clone and install dependencies

```bash
git clone https://github.com/ojackson08/devintent-ai.git
cd devintent-ai
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your GitHub PAT and OpenRouter key
```

### 3. Validate credentials

```bash
python scripts/test_auth.py
```

### 4. Run the pipeline

```bash
# Standard pipeline
python scripts/run_pipeline.py

# Parallel pipeline (faster, recommended for large batches)
python scripts/run_pipeline_improved.py
```

Leads are exported to `data/leads_YYYY-MM-DD.csv` and stored in `data/devintent.db`.

---

## Configuration

All settings are controlled via `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `GITHUB_TOKEN` | — | GitHub Personal Access Token (required) |
| `OPENROUTER_OWL_KEY` | — | OpenRouter API key (required) |
| `TARGET_REPOS` | see `.env.example` | Comma-separated repos to monitor |
| `MIN_LEAD_SCORE` | `60` | Minimum ICP score to save a lead |
| `BATCH_SIZE` | `50` | Signals processed per batch |
| `MAX_WORKERS` | `8` | Parallel threads (improved pipeline) |
| `DB_PATH` | `./data/devintent.db` | SQLite database path |
| `OUTPUT_DIR` | `./data` | CSV export directory |

---

## Monitored Repos (Default)

The pipeline ships pre-configured to monitor high-signal AI repositories:

- `Significant-Gravitas/AutoGPT`
- `open-webui/open-webui`
- `ollama/ollama`
- `n8n-io/n8n`
- `langgenius/dify`
- `x1xhlol/system-prompts-and-models-of-ai-tools`

Add any public GitHub repo to `TARGET_REPOS` in `.env` to expand coverage.

---

## Architecture

**Phase 1 — Ingestion:** Fetches recent stargazers and forkers from target repos via the GitHub REST API. New signals are stored in SQLite with deduplication.

**Phase 2 — Classification:** Unprocessed signals are batched and sent to an LLM (via OpenRouter) with a structured prompt that returns `{ category, intent_strength, reason }` as JSON.

**Phase 3 — Enrichment & Scoring:** GitHub profile data (name, email, company, bio) is fetched for each user. An ICP fit score is computed from intent strength, company presence, and event type (star vs. fork).

**Phase 4 — Export:** Leads above `MIN_LEAD_SCORE` are written to a dated CSV and persisted in SQLite for deduplication across runs.

---

## Security Notes

- **Never commit your `.env` file.** It is listed in `.gitignore`.
- Use a GitHub PAT with `public_repo` read-only scope — no write permissions needed.
- Lead data (CSV + SQLite) is gitignored and stays local.
- See [SECURITY.md](SECURITY.md) for responsible disclosure.

---

## Built With

| Tool | Purpose |
|------|---------|
| Python 3.10+ | Core runtime |
| GitHub REST API | Signal ingestion + user enrichment |
| OpenRouter (LLM) | Intent classification |
| SQLite | Local lead storage |
| `concurrent.futures` | Parallel signal processing |

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

*Built by [Otis Jackson](https://merkabacreatives.org) · [ojack@merkabacreatives.org](mailto:ojack@merkabacreatives.org)*
