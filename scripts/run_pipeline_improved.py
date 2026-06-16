import os, sys, sqlite3, requests, json, csv, logging, threading, time
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()
ENV_PATH = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(ENV_PATH)

GITHUB_TOKEN=os.get...EN', '')
OPENROUTER_KEY = os.getenv('OPENROUTER_OWL_KEY', '')
OPENROUTER_URL = os.getenv('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')
MODEL = os.getenv('OPENROUTER_MODEL', 'owl-alpha')
DB_PATH = os.getenv('DB_PATH', 'D:/DevIntent AI/data/devintent.db')
OUTPUT_DIR = os.getenv('OUTPUT_DIR', 'D:/DevIntent AI/data')
MIN_SCORE = int(os.getenv('MIN_LEAD_SCORE', '60'))
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '50'))
MAX_WORKERS = int(os.getenv('MAX_WORKERS', '8'))
USER_CACHE_TTL = int(os.getenv('USER_CACHE_TTL', '21600'))
TARGET_REPOS = [r.strip() for r in os.getenv('TARGET_REPOS', '').split(',') if r.strip()]

log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
log_handler = logging.FileHandler(os.path.join(os.path.dirname(__file__), '..', 'logs', 'pipeline.log'))
log_handler.setFormatter(log_formatter)
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger = logging.getLogger('DevIntentPipeline')
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)
logger.addHandler(console_handler)

GITHUB_HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}' if GITHUB_TOKEN else '',
    'Accept': 'application/vnd.github.v3+json',
    'User-Agent': 'DevIntent-Hermes/1.0'
}
OPENROUTER_HEADERS = {
    'Authorization': f'Bearer {OPENROUTER_KEY}',
    'Content-Type': 'application/json',
    'HTTP-Referer': 'https://devintent.local',
    'X-Title': 'DevIntent AI'
}

CLASSIFICATION_PROMPT = '''You are an expert B2B sales intelligence analyst.
Classify the GitHub activity into ONE category:
1. AI Coding Agent (Devin, Cursor, Claude Code, etc.)
2. AI Meeting / Productivity Tools
3. Enterprise Knowledge Base / Search
4. Developer Infrastructure / DevOps
5. Other / Low Intent
Return ONLY JSON: {"category": "...", "intent_strength": 1-10, "reason": "..."}'''

def get_db():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, repo TEXT, event_type TEXT,
        github_username TEXT, event_time TEXT, raw_data TEXT,
        processed INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT, github_username TEXT UNIQUE,
        real_name TEXT, email TEXT, company TEXT, job_title TEXT,
        intent_category TEXT, intent_score INTEGER, icp_fit_score INTEGER,
        source_repos TEXT, enriched_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT, finished_at TEXT,
        signals_found INTEGER, new_leads INTEGER, status TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_cache (
        github_username TEXT PRIMARY KEY,
        data_json TEXT,
        fetched_at TEXT)''')
    conn.commit()
    conn.close()
    logger.info('Database initialized')

def github_get(url, params=None, headers=None, max_attempts=3):
    if headers is None:
        headers = GITHUB_HEADERS
    for attempt in range(max_attempts):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            if resp.status_code == 401:
                logger.error('GitHub 401 Unauthorized - check token')
                resp.raise_for_status()
            if resp.status_code == 403:
                reset = resp.headers.get('X-RateLimit-Reset')
                if reset:
                    wait = int(reset) - int(time.time())
                    logger.warning(f'GitHub rate limit hit, waiting {wait}s')
                    time.sleep(max(wait, 0))
                continue
            resp.raise_for_status()
            return resp
        except Exception as e:
            logger.warning(f'Attempt {attempt+1} failed for {url}: {e}')
            if attempt == max_attempts - 1:
                raise
            time.sleep(2 ** attempt)
    raise Exception('Max attempts exceeded')

def fetch_since(repo, event_type, since_iso):
    url = f'https://api.github.com/repos/{repo}/events'
    params = {'per_page': 100}
    if since_iso:
        params['since'] = since_iso
    results = []
    try:
        resp = github_get(url, params=params)
        for event in resp.json():
            if event.get('type') == event_type:
                actor = event.get('actor', {}).get('login')
                if actor:
                    results.append({
                        'repo': repo,
                        'event_type': event_type.lower(),
                        'github_username': actor,
                        'event_time': event.get('created_at'),
                        'raw_data': json.dumps(event)
                    })
        while 'Link' in resp.headers:
            links = resp.headers['Link']
            if 'rel=\"next\"' not in links:
                break
            next_url = [ln.split(';')[0].strip('<> ') for ln in links.split(',') if 'rel=\"next\"' in ln][0]
            resp = github_get(next_url)
            for event in resp.json():
                if event.get('type') == event_type:
                    actor = event.get('actor', {}).get('login')
                    if actor:
                        results.append({
                            'repo': repo,
                            'event_type': event_type.lower(),
                            'github_username': actor,
                            'event_time': event.get('created_at'),
                            'raw_data': json.dumps(event)
                        })
    except Exception as e:
        logger.error(f'Error fetching {event_type} for {repo}: {e}')
    return results

def get_last_processed_time(repo, event_type):
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT MAX(event_time) FROM signals WHERE repo=? AND event_type=?''', (repo, event_type))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        return row[0]
    return None

def fetch_stargazers(repo):
    since = get_last_processed_time(repo, 'WatchEvent')
    return fetch_since(repo, 'WatchEvent', since)

def fetch_forks(repo):
    since = get_last_processed_time(repo, 'ForkEvent')
    return fetch_since(repo, 'ForkEvent', since)

def store_signals(signals):
    if not signals:
        return 0
    conn = get_db()
    c = conn.cursor()
    new = 0
    for s in signals:
        try:
            c.execute('''INSERT OR IGNORE INTO signals 
                (repo, event_type, github_username, event_time, raw_data) 
                VALUES (?,?,?,?,?)''',
                (s['repo'], s['event_type'], s['github_username'], s['event_time'], s['raw_data']))
            if c.rowcount > 0:
                new += 1
        except Exception as e:
            logger.error(f'Failed to insert signal: {e}
