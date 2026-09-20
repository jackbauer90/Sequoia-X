"""在腾讯主机上以 sudo 运行：为新模块添加受保护路由，不输出门卫凭据。"""
from pathlib import Path
from datetime import datetime
import re
import shutil
import subprocess
import urllib.request
import urllib.error

config = Path('/etc/nginx/sites-available/strategies-site')
nav = Path('/var/www/nav/index.html')
text = config.read_text()
page = nav.read_text()
route = '/sequoia-five/'
stamp = datetime.now().strftime('%Y%m%d%H%M%S')
if route not in text:
    match = re.search(r'    location (/nav-[^/]+/) \{.*?\n    \}', text, re.S)
    assert match and 'if (' in match[0], 'Protected navigation block not found'
    block = match[0].replace(match[1], route).replace('/var/www/nav/', '/opt/sequoia-x/site/')
    block = block.replace('        autoindex off;', '        autoindex off;\n        add_header Cache-Control "no-cache, no-store, must-revalidate";')
    text = text.replace('    include /etc/nginx/snippets/w-bottom-dashboard.conf;', block + '\n\n    include /etc/nginx/snippets/w-bottom-dashboard.conf;')
    assert route in text
card = '''
        <a class="card" href="/sequoia-five/">
            <div class="card-icon">🔎</div>
            <div class="card-title">主板与创业板三策略初选股</div>
            <div class="card-desc">均线放量 · 高窄旗形 · RPS突破<br>股票名称与板块分类 · K线均线及策略点位 · 已记录命中天数</div>
            <div class="card-tags"><span class="tag tag-green">三策略</span><span class="tag">剔除ST</span><span class="tag tag-orange">只读 · 不推送</span></div>
        </a>
'''
existing_card = re.search(r'<a class="card" href="/sequoia-five/">.*?</a>', page, re.S)
if existing_card:
    page = page.replace(existing_card.group(), card.strip(), 1)
else:
    assert '<div class="grid">' in page
    page = page.replace('<div class="grid">', '<div class="grid">' + card, 1)
for path in (config, nav):
    shutil.copy2(path, str(path) + '.bak.' + stamp)
config.write_text(text)
nav.write_text(page)
check = subprocess.run(['nginx', '-t'], capture_output=True)
if check.returncode:
    for path in (config, nav):
        shutil.copy2(str(path) + '.bak.' + stamp, path)
    raise RuntimeError('nginx validation failed; original files restored')
subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
cookie = re.search(r'map \$cookie_(\w+)\s+\$\w+\s*\{.*?"([^"]+)"\s+1;', text, re.S)
assert cookie, 'Authentication mapping not found'
request = urllib.request.Request('http://127.0.0.1:8899' + route, headers={'Cookie': cookie[1] + '=' + cookie[2]})
with urllib.request.urlopen(request) as response:
    body = response.read().decode()
    assert response.status == 200
    assert '主板与创业板三策略初选股' in body
print('Authenticated page OK:', route)
try:
    urllib.request.urlopen('http://127.0.0.1:8899' + route)
    raise RuntimeError('Unauthenticated request unexpectedly allowed')
except urllib.error.HTTPError as error:
    assert error.code in (403, 404)
    print('Unauthenticated access blocked:', error.code)
print('Navigation installed; backups:', stamp)
