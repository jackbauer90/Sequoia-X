"""仅为三策略安装专属访问日志及受保护的记录页；以sudo运行。"""
from pathlib import Path
from datetime import datetime
import grp
import pwd
import os
import re
import shutil
import subprocess

root = Path('/opt/sequoia-x')
config = Path('/etc/nginx/sites-available/strategies-site')
nav = Path('/var/www/nav/index.html')
format_config = Path('/etc/nginx/conf.d/sequoia-visits.conf')
stamp = datetime.now().strftime('%Y%m%d%H%M%S')
original = {path: path.read_bytes() if path.exists() else None for path in (config, nav, format_config)}
for path, content in original.items():
    if content is not None:
        shutil.copy2(path, str(path) + '.bak.' + stamp)
text = config.read_text()
match = re.search(r'    location /sequoia-five/ \{.*?\n    \}', text, re.S)
assert match and 'if (' in match[0], 'Protected source block missing'
block = match[0]
if 'sequoia_visits' not in block:
    new_block = block.replace('        autoindex off;', '        autoindex off;\n        access_log /var/log/nginx/strategies-access.log;\n        access_log /var/log/nginx/sequoia/sequoia-visits.log sequoia_visits if=$sequoia_page_visit;')
    text = text.replace(block, new_block, 1)
if 'location /sequoia-visits/' not in text:
    access_block = block.replace('/sequoia-five/', '/sequoia-visits/').replace('/opt/sequoia-x/site/', '/opt/sequoia-x/visits/')
    access_block = '\n'.join(line for line in access_block.splitlines() if 'access_log' not in line)
    text = text.replace('    include /etc/nginx/snippets/w-bottom-dashboard.conf;', access_block + '\n\n    include /etc/nginx/snippets/w-bottom-dashboard.conf;')
page = nav.read_text()
card = '''<a class="card" href="/sequoia-visits/">
<div class="card-icon">◷</div><div class="card-title">访问记录</div>
<div class="card-desc">三策略页面 · IP、设备、浏览器及访问时间<br>最近30天 · 每分钟更新 · 无法识别真实姓名</div>
<div class="card-tags"><span class="tag">三策略专属</span><span class="tag tag-green">受保护</span></div></a>'''
existing_card = re.search(r'<a class="card" href="/sequoia-visits/">.*?</a>', page, re.S)
if existing_card:
    page = page.replace(existing_card.group(), card, 1)
else:
    assert '<div class="grid">' in page
    page = page.replace('<div class="grid">', '<div class="grid">' + card, 1)
logs = Path('/var/log/nginx/sequoia')
logs.mkdir(exist_ok=True)
os.chown(logs, 0, grp.getgrnam('adm').gr_gid)
logs.chmod(0o750)
log = logs / 'sequoia-visits.log'
log.touch(exist_ok=True)
os.chown(log, pwd.getpwnam('www-data').pw_uid, grp.getgrnam('adm').gr_gid)
log.chmod(0o640)
(root / 'visits').mkdir(exist_ok=True)
os.chown(root / 'visits', pwd.getpwnam('ubuntu').pw_uid, grp.getgrnam('ubuntu').gr_gid)
config.write_text(text)
nav.write_text(page)
shutil.copy2(root / 'deploy/sequoia-visits.conf', format_config)
check = subprocess.run(['nginx', '-t'], capture_output=True)
if check.returncode:
    for path, content in original.items():
        if content is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(content)
    raise RuntimeError('nginx check failed; configurations restored')
for name in ('sequoia-visits.service', 'sequoia-visits.timer'):
    shutil.copy2(root / 'deploy' / name, Path('/etc/systemd/system') / name)
shutil.copy2(root / 'deploy/sequoia-visits.logrotate', '/etc/logrotate.d/sequoia-visits')
Path('/etc/logrotate.d/sequoia-visits').chmod(0o644)
subprocess.run(['systemctl', 'daemon-reload'], check=True)
subprocess.run(['systemctl', 'start', 'sequoia-visits.service'], check=True)
subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
subprocess.run(['systemctl', 'enable', '--now', 'sequoia-visits.timer'], check=True)
print('Protected access records installed; backup stamp:', stamp)
