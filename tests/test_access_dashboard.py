import json
from datetime import datetime, timezone
from access_dashboard import read_visits, render_visits, device_info


def test_only_recent_five_strategy_pages_are_counted(tmp_path):
    entries = [
        {'time': '2026-09-09T12:00:00+08:00', 'ip': '203.0.113.8', 'uri': '/sequoia-five/', 'status': '200', 'ua': 'Mozilla Windows NT 10.0 Chrome/140.0', 'refresh': ''},
        {'time': '2026-09-09T12:01:00+08:00', 'ip': '203.0.113.8', 'uri': '/sequoia-five/stocks/000001.html', 'status': '200', 'ua': 'iPhone Safari/600', 'refresh': ''},
        {'time': '2026-09-09T12:01:00+08:00', 'ip': '203.0.113.8', 'uri': '/sequoia-five/status.json', 'status': '200', 'ua': '', 'refresh': ''},
        {'time': '2026-07-09T12:01:00+08:00', 'ip': '203.0.113.8', 'uri': '/sequoia-five/', 'status': '200', 'ua': '', 'refresh': ''},
        {'time': '2026-09-09T12:01:00+08:00', 'ip': '203.0.113.8', 'uri': '/sequoia-five/', 'status': '404', 'ua': '', 'refresh': ''},
    ]
    (tmp_path / 'sequoia-visits.log').write_text('\n'.join(json.dumps(e) for e in entries) + '\n{incomplete', encoding='utf-8')
    rows = read_visits(tmp_path, datetime(2026, 9, 9, 5, tzinfo=timezone.utc))
    assert len(rows) == 2
    assert rows[0]['uri'].endswith('000001.html')
    assert device_info(rows[0]['ua']) == ('手机', 'iOS', 'Safari')


def test_access_page_escapes_untrusted_user_agent():
    row = {'time': '2026-09-09T12:00:00+08:00', 'ip': '203.0.113.8', 'uri': '/sequoia-five/', 'ua': '<script>alert(1)</script>', 'refresh': ''}
    page = render_visits([row], '2026-09-09 12:00')
    assert '<script>alert(1)</script>' not in page
    assert '203.0.113.8' in page
    assert '2026-09-09' in page
