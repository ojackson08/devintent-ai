import requests

env_path = 'C:\\c\\Users\\Otis\\devintent\\.env'
token = ''
with open(env_path, 'r') as f:
    for line in f:
        line = line.strip()
        if line.startswith('GITHUB_TOKEN=') and not line.startswith('GITHUB_TOKEN=***'):
            token = line[len('GITHUB_TOKEN='):]
            break

if not token:
    print('ERROR: No GITHUB_TOKEN found in .env')
    exit(1)

print('Token found:', token[:20], '...', token[-10:])
print('Token length:', len(token))

headers = {
    'Authorization': 'token ' + token,
    'Accept': 'application/vnd.github.v3+json',
    'User-Agent': 'DevIntent-Test/1.0'
}

# Test 1: auth
r = requests.get('https://api.github.com/user', headers=headers, timeout=15)
print('Auth status:', r.status_code)
if r.status_code == 200:
    print('Logged in as:', r.json()['login'])
else:
    print('Auth error:', r.text[:300])

# Test 2: stargazers endpoint
r2 = requests.get('https://api.github.com/repos/ollama/ollama/stargazers?per_page=3', headers=headers, timeout=15)
print('Stargazers status:', r2.status_code)
if r2.status_code == 200:
    print('Got', len(r2.json()), 'stargazers')
else:
    print('Stargazers error:', r2.text[:300])

# Test 3: events endpoint (alternative)
r3 = requests.get('https://api.github.com/repos/ollama/ollama/events?per_page=3', headers=headers, timeout=15)
print('Events status:', r3.status_code)
if r3.status_code == 200:
    print('Got', len(r3.json()), 'events')
else:
    print('Events error:', r3.text[:300])
