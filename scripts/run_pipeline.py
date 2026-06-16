import os, sys, sqlite3, requests, json, csv
from datetime import datetime, timezone

# Read .env manually to avoid any parsing issues
_env_file = os.path.join(os.path.dirname(__file__), '..', '.env')
_env = {}
with open(_env_file, 'r') as _f:
    for _line in _f:
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            _k, _v = _line.split('=', 1)
            _env[_k] = _v

GITHUB_TOKEN = _env.get('GITHUB_TOKEN', '')
OPENROUTER_KEY = _env.get('OPENROUTER_OWL_KEY', '')
OPENROUTER_URL = _env.get('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')
MODEL = _env.get('OPENROUTER_MODEL', 'owl-alpha')
DB_PATH = _env.get('DB_PATH', 'C:/Users/Otis/devintent/data/devintent.db')
OUTPUT_DIR = _env.get('OUTPUT_DIR', 'C:/Users/Otis/devintent/data')
MIN_SCORE = int(_env.get('MIN_LEAD_SCORE', '60'))
TARGET_REPOS = [r.strip() for r in _env.get('TARGET_REPOS', '').split(',') if r.strip()]
BATCH = int(_env.get('BATCH_SIZE', '20'))

GITHUB_HEADERS = {
    'Authorization': 'token ' + GITHUB_TOKEN,
    'Accept': 'application/vnd.github.v3+json',
    'User-Agent': 'DevIntent-Hermes/1.0'
}

OPENROUTER_HEADERS = {
    'Authorization': 'Bearer ' + OPENROUTER_KEY,
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

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, repo TEXT, event_type TEXT,
        github_username TEXT, event_time TEXT, raw_data TEXT,
        processed INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT, github_username TEXT UNIQUE,
        real_name TEXT, email TEXT, company TEXT, job_title TEXT,
        intent_category TEXT, intent_score INTEGER, icp_fit_score INTEGER,
        source_repos TEXT, enriched_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT, finished_at TEXT,
        signals_found INTEGER, new_leads INTEGER, status TEXT)''')
    conn.commit()
    conn.close()

def fetch_stargazers(repo):
    url = 'https://api.github.com/repos/' + repo + '/stargazers?per_page=30'
    users = []
    try:
        r = requests.get(url, headers=GITHUB_HEADERS, timeout=20)
        r.raise_for_status()
        for item in r.json():
            users.append({
                'repo': repo, 'event_type': 'star',
                'github_username': item.get('login', ''),
                'event_time': datetime.now(timezone.utc).isoformat(),
                'raw_data': json.dumps(item)
            })
    except Exception as e:
        print('  err ' + repo + ': ' + str(e))
    return users

def fetch_forks(repo):
    url = 'https://api.github.com/repos/' + repo + '/forks?per_page=30'
    users = []
    try:
        r = requests.get(url, headers=GITHUB_HEADERS, timeout=20)
        r.raise_for_status()
        for item in r.json():
            owner = item.get('owner', {}).get('login', '')
            if owner:
                users.append({
                    'repo': repo, 'event_type': 'fork',
                    'github_username': owner,
                    'event_time': datetime.now(timezone.utc).isoformat(),
                    'raw_data': json.dumps(item)
                })
    except Exception as e:
        print('  err ' + repo + ': ' + str(e))
    return users

def store_signals(signals):
    if not signals:
        return 0
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    new = 0
    for s in signals:
        try:
            c.execute('INSERT OR IGNORE INTO signals (repo, event_type, github_username, event_time, raw_data) VALUES (?,?,?,?,?)',
                (s['repo'], s['event_type'], s['github_username'], s['event_time'], s['raw_data']))
            if c.rowcount > 0:
                new += 1
        except:
            pass
    conn.commit()
    conn.close()
    return new

def get_unprocessed(limit=None):
    if limit is None:
        limit = BATCH
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute('SELECT id, repo, event_type, github_username FROM signals WHERE processed=0 LIMIT ?', (limit,)).fetchall()
    conn.close()
    return rows

def classify(username, repo, event_type):
    payload = {
        'model': MODEL,
        'messages': [
            {'role': 'system', 'content': CLASSIFICATION_PROMPT},
            {'role': 'user', 'content': 'User \'' + username + '\' ' + event_type + 'ed the repo \'' + repo + '\''}
        ],
        'temperature': 0.2, 'max_tokens': 150
    }
    try:
        r = requests.post(OPENROUTER_URL + '/chat/completions', headers=OPENROUTER_HEADERS, json=payload, timeout=60)
        content = r.json()['choices'][0]['message']['content'].strip()
        if content.startswith('```'):
            content = content.split('\n', 1)[1]
            if content.endswith('```'):
                content = content[:-3]
        result = json.loads(content)
        return result.get('category', 'Other / Low Intent'), result.get('intent_strength', 3)
    except Exception as e:
        print('    cls err ' + username + ': ' + str(e))
        return 'Other / Low Intent', 2

def enrich(username):
    try:
        r = requests.get('https://api.github.com/users/' + username, headers=GITHUB_HEADERS, timeout=15)
        if r.status_code == 200:
            d = r.json()
            return {'real_name': d.get('name') or username, 'company': d.get('company'),
                    'job_title': d.get('bio'), 'email': d.get('email')}
    except:
        pass
    return {'real_name': username, 'company': None, 'job_title': None, 'email': None}

def score_lead(intent_str, company, event_type):
    s = intent_str * 8
    if company: s += 20
    if event_type in ['star', 'fork']: s += 10
    return min(max(s, 0), 100)

def save_lead(username, profile, category, intent_s, icp_s, repo):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT OR REPLACE INTO leads (github_username, real_name, email, company, job_title, intent_category, intent_score, icp_fit_score, source_repos, enriched_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
        (username, profile['real_name'], profile['email'], profile['company'],
         profile['job_title'], category, intent_s, icp_s, repo, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()

def export_csv():
    today = datetime.now().strftime('%Y-%m-%d')
    path = OUTPUT_DIR + '/leads_' + today + '.csv'
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT github_username, real_name, email, company, intent_category, intent_score, icp_fit_score, source_repos, enriched_at FROM leads WHERE DATE(enriched_at)=DATE('now') ORDER BY icp_fit_score DESC").fetchall()
    conn.close()
    if not rows:
        return path
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['username','name','email','company','category','intent_score','icp_score','repo','enriched_at'])
        w.writerows(rows)
    print('Exported ' + str(len(rows)) + ' leads to ' + path)
    return path

def count_all_signals():
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute('SELECT COUNT(*) FROM signals').fetchone()[0]
    conn.close()
    return total

def count_all_leads():
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute('SELECT COUNT(*) FROM leads').fetchone()[0]
    conn.close()
    return total

def main():
    startTime = datetime.now()
    print('=== DevIntent Pipeline v2 - ' + str(startTime) + ' ===')
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    init_db()

    print('\n--- Phase 1: Ingestion ---')
    total = 0
    for repo in TARGET_REPOS:
        stars = fetch_stargazers(repo)
        new_s = store_signals(stars)
        forks = fetch_forks(repo)
        new_f = store_signals(forks)
        total += new_s + new_f
        print('  ' + repo + ': +' + str(new_s + new_f))
    print('New signals: ' + str(total) + ' | Total in DB: ' + str(count_all_signals()))

    print('\n--- Phase 2: Classification (batch=' + str(BATCH) + ') ---')
    signals = get_unprocessed()
    print('Processing ' + str(len(signals)) + ' signals...')
    leads_saved = 0
    for sig_id, repo, et, user in signals:
        cat, intent = classify(user, repo, et)
        profile = enrich(user)
        icp = score_lead(intent, profile.get('company'), et)
        if icp >= MIN_SCORE:
            save_lead(user, profile, cat, intent, icp, repo)
            leads_saved += 1
        conn = sqlite3.connect(DB_PATH)
        conn.execute('UPDATE signals SET processed=1 WHERE id=?', (sig_id,))
        conn.commit()
        conn.close()
    print('Leads saved: ' + str(leads_saved) + ' | Leads in DB: ' + str(count_all_leads()))

    print('\n--- Phase 3: Export ---')
    csv_path = export_csv()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO runs (started_at, finished_at, signals_found, new_leads, status) VALUES (?,?,?,?,?)',
        (startTime.isoformat(), datetime.now().isoformat(), total, leads_saved, 'success'))
    conn.commit()
    conn.close()

    elapsed = (datetime.now() - startTime).total_seconds()
    print('\n=== Done in ' + str(int(elapsed)) + 's | CSV: ' + csv_path + ' ===')

if __name__ == '__main__':
    main()
