"""Tushare 增量日线；固定重叠日锚点，接续既有后复权价格尺度。"""
from contextlib import closing
from datetime import datetime
import os
import sqlite3

import numpy as np
import pandas as pd


def client():
    import tushare as ts
    token = os.environ.get('TUSHARE_TOKEN')
    if not token:
        raise RuntimeError('未配置 Tushare Token')
    return ts.pro_api(token, timeout=30)


def trading_days(pro, start, end):
    calendar = pro.trade_cal(exchange='SSE', start_date=start.replace('-', ''), end_date=end.replace('-', ''))
    return sorted(datetime.strptime(str(day), '%Y%m%d').date().isoformat()
                  for day in calendar.loc[calendar.is_open.astype(str) == '1', 'cal_date'])


def adjusted_daily(pro, day):
    raw = pro.daily(trade_date=day.replace('-', ''))
    if raw.empty:
        return raw
    factors = pro.adj_factor(trade_date=day.replace('-', ''))
    if factors.empty:
        raise RuntimeError('Tushare 复权因子缺失')
    frame = raw.merge(factors, on=['ts_code', 'trade_date'], how='left', validate='one_to_one')
    numeric = ['open', 'high', 'low', 'close', 'vol', 'amount', 'adj_factor']
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors='coerce')
    if not (frame.trade_date.astype(str) == day.replace('-', '')).all():
        raise RuntimeError('Tushare 返回日期不一致')
    if not np.isfinite(frame[numeric]).all().all() or (frame.adj_factor <= 0).any():
        raise RuntimeError('Tushare 价格或复权因子无效')
    frame['symbol'] = frame.ts_code.str.split('.').str[0]
    return frame.loc[(frame.vol > 0) & (frame.close > 0)].copy()


def sync_tushare(db_path, pro, target):
    """在调用方的临时数据库更新；空的末日可延后，部分日拒绝提交。"""
    with closing(sqlite3.connect(db_path)) as conn, conn:
        latest = conn.execute('SELECT MAX(date) FROM stock_daily').fetchone()[0]
        previous_count = conn.execute('SELECT COUNT(*) FROM stock_daily WHERE date=?', (latest,)).fetchone()[0]
        conn.execute('CREATE TABLE IF NOT EXISTS tushare_anchor(symbol TEXT PRIMARY KEY, date TEXT, scale REAL)')
        conn.execute('CREATE TABLE IF NOT EXISTS tushare_market_cap(symbol TEXT, date TEXT, value REAL, PRIMARY KEY(symbol,date))')
        anchors = pd.read_sql_query('SELECT * FROM tushare_anchor', conn)
        if anchors.empty:
            overlap = adjusted_daily(pro, latest)
            if overlap.empty:
                raise RuntimeError('Tushare 缺少同日价格，无法校准后复权尺度')
            old = pd.read_sql_query('SELECT symbol,close AS old_close FROM stock_daily WHERE date=?', conn, params=(latest,))
            overlap = overlap.merge(old, on='symbol', validate='one_to_one')
            overlap['scale'] = overlap.old_close / (overlap.close * overlap.adj_factor)
            if len(overlap) < previous_count * .98 or not np.isfinite(overlap.scale).all() or (overlap.scale <= 0).any():
                raise RuntimeError('Tushare 复权锚点覆盖不足')
            conn.executemany('INSERT INTO tushare_anchor VALUES(?,?,?)',
                             [(r.symbol, latest, r.scale) for r in overlap.itertuples()])
            anchors = pd.read_sql_query('SELECT * FROM tushare_anchor', conn)
        added, published = 0, latest
        # 重拉最近已发布日，允许 18:30 修订实时首版；固定锚点不会随修订漂移。
        days = trading_days(pro, latest, target)
        if target > latest:
            days = [day for day in days if day > latest]
        for day in days:
            if day <= anchors.date.min():
                continue
            frame = adjusted_daily(pro, day)
            if frame.empty:
                break
            frame = frame.merge(anchors, on='symbol', validate='one_to_one')
            if len(frame) < previous_count * .98:
                raise RuntimeError('Tushare 行情覆盖不足前次的98%')
            for column in ['open', 'high', 'low', 'close']:
                frame[column] *= frame.adj_factor * frame.scale
            frame['date'] = day
            frame['volume'] = frame.vol * 100
            frame['turnover'] = frame.amount * 1000
            conn.executemany(
                'INSERT INTO stock_daily(symbol,date,open,high,low,close,volume,turnover) VALUES(?,?,?,?,?,?,?,?) '
                'ON CONFLICT(symbol,date) DO UPDATE SET open=excluded.open,high=excluded.high,low=excluded.low,close=excluded.close,volume=excluded.volume,turnover=excluded.turnover',
                frame[['symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'turnover']].itertuples(index=False, name=None))
            added += len(frame)
            published = day
            print(f'Tushare daily date={day} rows={len(frame)}', flush=True)
        if added:
            caps = pro.daily_basic(trade_date=published.replace('-', ''), fields='ts_code,trade_date,circ_mv')
            if not caps.empty:
                caps = caps.loc[caps.trade_date.astype(str) == published.replace('-', '')].dropna(subset=['circ_mv'])
                conn.executemany('INSERT OR REPLACE INTO tushare_market_cap VALUES(?,?,?)',
                                 [(r.ts_code.split('.')[0], published, float(r.circ_mv) * 10000) for r in caps.itertuples()])
            conn.execute(
                'CREATE TABLE IF NOT EXISTS market_data_publication('
                'date TEXT PRIMARY KEY, source TEXT NOT NULL, phase TEXT NOT NULL, updated_at TEXT NOT NULL)'
            )
            conn.execute(
                'INSERT OR REPLACE INTO market_data_publication VALUES(?,?,?,?)',
                (published, 'Tushare正式日线', '18:30补全', datetime.now().astimezone().isoformat()),
            )
        return published, added
