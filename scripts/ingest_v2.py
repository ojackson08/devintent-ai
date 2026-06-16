import requests, json, sqlite3, os
from datetime import datetime, timezone

DB_PATH = "D:/DevIntent AI/data/devintent.db"

# No auth needed for public repo search
HEADERS = {"User-Agent": "DevIntent-Hermes/1.0"}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        repo TEXT, event_type TEXT, github_username TEXT,
        event_time TEXT, raw_data TEXT, processed INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        github_username TEXT UNIQUE, real_name TEXT, email TEXT,
        company TEXT, bio TEXT, intent_category TEXT,
        intent_score INTEGER, icp_fit_score INTEGER,
        source_repos TEXT, enriched_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT, finished_at TEXT,
        signals_found INTEGER, status TEXT)""")
    conn.commit()
    conn.close()

def search_recent_stars(repo):
    """Use GitHub Events API (no auth needed for public events)."""
    url = f"https://api.github.com/repos/{repo}/events"
    params = {"per_page": 100}
    users = []
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=20)
        if r.status_code != 200:
            print(f"  {r.status_code} for {repo}")
            return users
        for event in r.json():
            if event.get("type") == "WatchEvent":
                actor = event.get("actor", {}).get("login", "")
                if actor:
                    users.append({
                        "repo": repo,
                        "event_type": "star",
                        "github_username": actor,
                        "event_time": event.get("created_at", datetime.now(timezone.utc).isoformat()),
                        "raw_data": json.dumps(event)
                    })
    except Exception as e:
        print(f"  Error: {e}")
    return users

def search_recent_forks(repo):
    """Use GitHub Events API for forks."""
    url = f"https://api.github.com/repos/{repo}/events"
    params = {"per_page": 100}
    users = []
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=20)
        if r.status_code != 200:
            return users
        for event in r.json():
            if event.get("type") == "ForkEvent":
                actor = event.get("actor", {}).get("login", "")
                if actor:
                    users.append({
                        "repo": repo,
                        "event_type": "fork",
                        "github_username": actor,
                        "event_time": event.get("created_at", datetime.now(timezone.utc).isoformat()),
                        "raw_data": json.dumps(event)
                    })
    except Exception as e:
        print(f"  Error: {e}")
    return users

def store_signals(signals):
    if not signals:
        return 0
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    new = 0
    for s in signals:
        try:
            c.execute("""INSERT OR IGNORE INTO signals (repo, event_type, github_username, event_time, raw_data)
                VALUES (?, ?, ?, ?, ?)""",
                (s["repo"], s["event_type"], s["github_username"], s["event_time"], s["raw_data"]))
            if c.rowcount > 0:
                new += 1
        except:
            pass
    conn.commit()
    conn.close()
    return new

def main():
    print(f"DevIntent Ingestion v2 (no auth) - {datetime.now()}")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    init_db()

    repos = [
        "x1xhlol/system-prompts-and-models-of-ai-tools",
        "anthropics/skills",
        "openclaw/openclaw",
        "Significant-Gravitas/AutoGPT",
        "open-webui/open-webui",
        "ollama/ollama",
        "n8n-io/n8n",
        "langgenius/dify",
    ]

    total = 0
    for repo in repos:
        print(f"  {repo}...")
        stars = search_recent_stars(repo)
        new_s = store_signals(stars)
        forks = search_recent_forks(repo)
        new_f = store_signals(forks)
        total += new_s + new_f
        print(f"    stars={len(stars)} (new={new_s}), forks={len(forks)} (new={new_f})")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO runs (started_at, finished_at, signals_found, status) VALUES (?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat(), total, "success"))
    conn.commit()
    conn.close()
    print(f"Done. {total} new signals.")

if __name__ == "__main__":
    main()
