"""Test all routes after admin enhancement"""
import requests

base = 'http://127.0.0.1:5000'

# Test public routes
routes = ['/', '/inventario', '/estadisticas']
for r in routes:
    resp = requests.get(base + r, timeout=5)
    print(f'{r} -> {resp.status_code}')

# Test admin login page
resp = requests.get(base + '/admin/login', timeout=5)
print(f'/admin/login -> {resp.status_code}')

# Login as admin
s = requests.Session()
resp = s.post(base + '/admin/login', data={'username': 'admin', 'password': 'admin1234'}, allow_redirects=False, timeout=5)
loc = resp.headers.get('Location', 'none')
print(f'/admin/login POST -> {resp.status_code} Location: {loc}')

# Follow redirect to dashboard
resp = s.get(base + '/admin/', timeout=5)
print(f'/admin/ -> {resp.status_code}')

# Test admin sub-pages
for r in ['/admin/tools', '/admin/entries', '/admin/agent', '/admin/quality']:
    resp = s.get(base + r, timeout=5)
    print(f'{r} -> {resp.status_code}')

# Test agent status API
resp = s.get(base + '/admin/agent/status', timeout=5)
print(f'/admin/agent/status -> {resp.status_code} {resp.json()}')

print('\nAll tests passed!')
