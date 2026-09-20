"""从三策略专属日志生成受门卫保护的近30天访问记录页。"""
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import argparse
import gzip
import html
import ipaddress
import json
import re


def device_info(ua):
    text = ua.lower()
    device = '自动程序' if re.search(r'bot|spider|crawler|python|curl|powershell', text) else ('平板' if 'ipad' in text or ('android' in text and 'mobile' not in text) else ('手机' if 'iphone' in text or 'mobile' in text else '电脑/未知'))
    system = next((label for token, label in [('iphone', 'iOS'), ('ipad', 'iPadOS'), ('android', 'Android'), ('windows', 'Windows'), ('mac os', 'macOS'), ('linux', 'Linux')] if token in text), '未知系统')
    browser = next((label for token, label in [('micromessenger', '微信'), ('edg/', 'Edge'), ('firefox/', 'Firefox'), ('chrome/', 'Chrome'), ('safari/', 'Safari')] if token in text), '未知浏览器')
    return device, system, browser


def read_visits(directory, now):
    cutoff = now - timedelta(days=30)
    rows = []
    for path in Path(directory).glob('sequoia-visits.log*'):
        opener = gzip.open if path.suffix == '.gz' else open
        with opener(path, 'rt', encoding='utf-8', errors='replace') as source:
            for line in source:
                try:
                    row = json.loads(line)
                    stamp = datetime.fromisoformat(row['time'])
                    ipaddress.ip_address(row['ip'])
                    if not cutoff <= stamp <= now or row.get('status') not in ('200', '304'):
                        continue
                    if not re.fullmatch(r'/sequoia-five/(?:index\.html|stocks/\d{6}\.html)?', row['uri']):
                        continue
                    rows.append({key: str(row.get(key, '')) for key in ('time', 'ip', 'uri', 'ua', 'refresh')})
                except (ValueError, KeyError, TypeError):
                    continue
    return sorted(rows, key=lambda row: row['time'], reverse=True)


def render_visits(rows, generated_at):
    esc = html.escape
    def time_text(value):
        return datetime.fromisoformat(value).astimezone(ZoneInfo('Asia/Shanghai')).strftime('%m-%d %H:%M:%S')
    groups = {}
    for row in rows:
        key = (row['ip'], row['ua'])
        group = groups.setdefault(key, {'first': row['time'], 'last': row['time'], 'count': 0})
        group['first'] = min(group['first'], row['time'])
        group['count'] += 1
    overview = ''.join(f'<tr><td>{esc(ip)}<small>身份未知 · 按IP与设备区分</small></td><td title="{esc(ua, quote=True)}">{esc(" / ".join(device_info(ua)))}</td><td>{time_text(value["first"])}</td><td>{time_text(value["last"])}</td><td>{value["count"]}</td></tr>' for (ip, ua), value in list(groups.items())[:200])
    details = ''.join(f'<tr><td>{time_text(row["time"])}</td><td>{esc(row["ip"])}</td><td>{esc(" / ".join(device_info(row["ua"])))}</td><td>{esc("三策略首页" if not "/stocks/" in row["uri"] else "股票K线 · " + Path(row["uri"]).stem)}</td><td><span class="tag">{"自动刷新" if row["refresh"] else "页面请求"}</span></td></tr>' for row in rows[:200])
    empty = '<tr><td colspan="5">尚无成功访问记录。启用后开始记录，每分钟更新。</td></tr>'
    css = Path(__file__).with_name('ui_theme.css').read_text(encoding='utf-8')
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="60"><link rel="icon" href="data:,"><title>访问记录 · 三策略</title><style>{css}</style></head><body><main class="shell">
<div class="tape"><span>SEQUOIA / ACCESS RECORDS</span><a href="../sequoia-five/">打开三策略 →</a></div>
<header class="hero"><div><p class="eyebrow">投资工具箱 · 管理视图</p><h1>访问记录</h1></div><p>三策略页面的访问足迹。<br>仅记录IP、时间、访问页面及设备标识，不记录密码或Cookie。</p></header>
<div class="privacy">近30天 · 北京时间 · 每分钟更新 · IP和设备不等于真实身份，同一网络可能共用IP，设备信息由浏览器声明，可能被伪装。只统计成功页面请求；自动刷新单独标注，不把请求次数当成人数。</div>
<section class="metrics visits-metrics" style="margin-top:22px"><div class="metric"><span>访问IP数</span><strong>{len({row['ip'] for row in rows})}</strong></div><div class="metric"><span>页面请求（含自动刷新）</span><strong>{len(rows)}</strong></div><div class="metric"><span>自动刷新请求</span><strong>{sum(bool(row['refresh']) for row in rows)}</strong></div><div class="metric"><span>最后访问</span><strong>{time_text(rows[0]['time']) if rows else '—'}</strong></div></section>
<div class="section-title"><h2>访问来源</h2><span>最多展示最近200组IP与设备</span></div><div class="table-card table-scroll"><table><thead><tr><th>IP / 身份</th><th>设备 / 系统 / 浏览器</th><th>首次访问</th><th>最后访问</th><th>请求数</th></tr></thead><tbody>{overview or empty}</tbody></table></div>
<div class="section-title"><h2>最近访问明细</h2><span>最近200次成功请求</span></div><div class="table-card table-scroll"><table><thead><tr><th>访问时间</th><th>IP</th><th>设备信息</th><th>访问页面</th><th>请求类型</th></tr></thead><tbody>{details or empty}</tbody></table></div>
<footer>更新于 {esc(generated_at)} · 本板块沿用投资工具箱访问权限。从启用专属日志起记录，不补写未知历史；原始日志轮转保留30份日文件，页面只显示最近30天。</footer></main></body></html>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--logs', default='/var/log/nginx/sequoia')
    parser.add_argument('--output', default='/opt/sequoia-x/visits/index.html')
    args = parser.parse_args()
    now = datetime.now(ZoneInfo('Asia/Shanghai'))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.tmp')
    temporary.write_text(render_visits(read_visits(args.logs, now), now.strftime('%Y-%m-%d %H:%M:%S')), encoding='utf-8')
    temporary.replace(output)


if __name__ == '__main__':
    main()
