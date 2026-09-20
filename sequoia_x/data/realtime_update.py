"""15:05 收盘首版行情：腾讯优先，东方财富备用。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
import json
import re
import sqlite3
import time

import pandas as pd


COLUMNS = ['symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'turnover']


def _request(url, encoding='utf-8'):
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    last_error = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=20) as response:
                return response.read().decode(encoding)
        except OSError as error:
            last_error = error
            if attempt < 2:
                time.sleep(attempt + 1)
    raise RuntimeError(f'实时行情请求失败: {last_error}') from last_error


def parse_tencent_quotes(text, expected_day):
    rows = []
    for match in re.finditer(r'v_[a-z0-9]+="([^"]*)";', text):
        fields = match.group(1).split('~')
        if len(fields) < 38 or len(fields[30]) < 8:
            continue
        day = f'{fields[30][:4]}-{fields[30][4:6]}-{fields[30][6:8]}'
        if day != expected_day:
            continue
        try:
            price_volume_amount = fields[35].split('/')
            row = {
                'symbol': fields[2], 'date': day,
                'open': float(fields[5]), 'high': float(fields[33]),
                'low': float(fields[34]), 'close': float(fields[3]),
                'volume': float(price_volume_amount[1]) * 100,
                'turnover': float(price_volume_amount[2]),
            }
        except (ValueError, IndexError):
            continue
        if row['close'] > 0 and row['volume'] > 0:
            rows.append(row)
    return pd.DataFrame(rows, columns=COLUMNS)


def fetch_tencent(symbols, day):
    server_symbols = [('sh' if symbol.startswith('6') else 'sz') + symbol for symbol in symbols]
    batches = [server_symbols[index:index + 60] for index in range(0, len(server_symbols), 60)]

    def fetch(batch):
        url = 'https://qt.gtimg.cn/q=' + quote(','.join(batch), safe=',')
        return parse_tencent_quotes(_request(url, 'gb18030'), day)

    with ThreadPoolExecutor(max_workers=8) as pool:
        frames = list(pool.map(fetch, batches))
    frames = [frame for frame in frames if not frame.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)


def parse_eastmoney_payload(payload, symbols, expected_day):
    wanted = set(symbols)
    rows = []
    for item in ((payload.get('data') or {}).get('diff') or []):
        try:
            day = datetime.fromtimestamp(int(item['f124']), ZoneInfo('Asia/Shanghai')).date().isoformat()
            row = {
                'symbol': str(item['f12']), 'date': day,
                'open': float(item['f17']), 'high': float(item['f15']),
                'low': float(item['f16']), 'close': float(item['f2']),
                'volume': float(item['f5']) * 100,
                'turnover': float(item['f6']),
            }
        except (KeyError, TypeError, ValueError, OSError):
            continue
        if row['symbol'] in wanted and day == expected_day and row['close'] > 0 and row['volume'] > 0:
            rows.append(row)
    return pd.DataFrame(rows, columns=COLUMNS)


def fetch_eastmoney(symbols, day, requester=None, page_size=100):
    requester = requester or (lambda url: json.loads(_request(url)))

    def fetch_page(page):
        parameters = {
            'pn': page, 'pz': page_size, 'po': 1, 'np': 1, 'fltt': 2, 'invt': 2, 'fid': 'f3',
            'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',
            'fields': 'f12,f2,f17,f15,f16,f5,f6,f124',
        }
        url = 'https://push2.eastmoney.com/api/qt/clist/get?' + urlencode(parameters)
        return requester(url)

    first = fetch_page(1)
    total = int((first.get('data') or {}).get('total') or 0)
    pages = (total + page_size - 1) // page_size
    payloads = [first]
    if pages > 1:
        with ThreadPoolExecutor(max_workers=8) as pool:
            payloads.extend(pool.map(fetch_page, range(2, pages + 1)))
    frames = [parse_eastmoney_payload(payload, symbols, day) for payload in payloads]
    frames = [frame for frame in frames if not frame.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)


def sync_realtime(db_path, pro, day, providers=None):
    providers = providers or [('腾讯实时行情', fetch_tencent), ('东方财富实时行情', fetch_eastmoney)]
    with sqlite3.connect(db_path) as connection:
        reference_day = connection.execute(
            'SELECT MAX(date) FROM stock_daily WHERE date<?', (day,)
        ).fetchone()[0]
        if not reference_day:
            raise RuntimeError('缺少前一交易日行情，不能生成实时首版')
        symbols = [row[0] for row in connection.execute(
            'SELECT symbol FROM stock_daily WHERE date=? ORDER BY symbol', (reference_day,)
        )]
        anchors = pd.read_sql_query('SELECT symbol,scale FROM tushare_anchor', connection)

        factors = pro.adj_factor(trade_date=day.replace('-', ''))
        if factors is None or factors.empty:
            raise RuntimeError('当日复权因子缺失，不能生成实时首版')
        if not (factors.trade_date.astype(str) == day.replace('-', '')).all():
            raise RuntimeError('复权因子日期不一致，不能生成实时首版')
        factors = factors.assign(symbol=factors.ts_code.str.split('.').str[0])[['symbol', 'adj_factor']]

        errors = []
        selected = None
        source = None
        minimum = max(1, len(symbols) * .98)
        for name, provider in providers:
            try:
                frame = provider(symbols, day)
                frame = frame.loc[frame.date == day, COLUMNS].drop_duplicates('symbol', keep='last')
                frame = frame.merge(anchors, on='symbol', validate='one_to_one')
                frame = frame.merge(factors, on='symbol', validate='one_to_one')
                if len(frame) < minimum:
                    raise RuntimeError(f'覆盖{len(frame)}只，低于发布门槛{minimum:.0f}只')
                selected, source = frame, name
                break
            except Exception as error:
                errors.append(f'{name}: {type(error).__name__}')
        if selected is None:
            raise RuntimeError('腾讯和东财均无可发布实时行情；' + '，'.join(errors))

        for column in ('open', 'high', 'low', 'close'):
            selected[column] *= selected.adj_factor * selected.scale
        rows = selected[COLUMNS].itertuples(index=False, name=None)

        with connection:
            connection.execute('DELETE FROM stock_daily WHERE date=?', (day,))
            connection.executemany(
                'INSERT INTO stock_daily(symbol,date,open,high,low,close,volume,turnover) VALUES(?,?,?,?,?,?,?,?)',
                rows,
            )
            connection.execute(
                'CREATE TABLE IF NOT EXISTS market_data_publication('
                'date TEXT PRIMARY KEY, source TEXT NOT NULL, phase TEXT NOT NULL, updated_at TEXT NOT NULL)'
            )
            connection.execute(
                'INSERT OR REPLACE INTO market_data_publication VALUES(?,?,?,?)',
                (day, source, '15:05首版', datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()),
            )
            connection.execute('DELETE FROM tushare_market_cap WHERE date=?', (day,))
            connection.execute(
                'INSERT INTO tushare_market_cap(symbol,date,value) '
                'SELECT symbol,?,value FROM tushare_market_cap WHERE date=?',
                (day, reference_day),
            )
    return source, len(selected)
