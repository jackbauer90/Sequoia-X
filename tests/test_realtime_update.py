import sqlite3

import pandas as pd

from tests.test_data_engine import make_engine_in


def seeded(tmp_path):
    engine, _ = make_engine_in(str(tmp_path))
    with sqlite3.connect(engine.db_path) as conn:
        conn.execute(
            "INSERT INTO stock_daily(symbol,date,open,high,low,close,volume,turnover) "
            "VALUES('600000','2026-09-10',18,22,17,20,1000,20000)"
        )
        conn.execute(
            "CREATE TABLE tushare_anchor(symbol TEXT PRIMARY KEY, date TEXT, scale REAL)"
        )
        conn.execute("INSERT INTO tushare_anchor VALUES('600000','2026-09-10',2)")
        conn.execute(
            "CREATE TABLE tushare_market_cap(symbol TEXT, date TEXT, value REAL, PRIMARY KEY(symbol,date))"
        )
        conn.execute("INSERT INTO tushare_market_cap VALUES('600000','2026-09-10',1000000)")
    return engine


def test_tencent_quote_parser_returns_complete_daily_bar_in_database_units():
    from sequoia_x.data.realtime_update import parse_tencent_quotes

    text = (
        'v_sh600000="1~浦发银行~600000~9.26~9.35~9.35~653273~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~'
        '20260911150003~-0.09~-0.96~9.35~9.22~9.26/653273/604625882~653273~60463";'
    )

    frame = parse_tencent_quotes(text, '2026-09-11')

    assert frame.to_dict('records') == [{
        'symbol': '600000', 'date': '2026-09-11', 'open': 9.35,
        'high': 9.35, 'low': 9.22, 'close': 9.26,
        'volume': 65327300.0, 'turnover': 604625882.0,
    }]


def test_realtime_sync_falls_back_and_preserves_adjusted_price_basis(tmp_path):
    from sequoia_x.data.realtime_update import sync_realtime

    engine = seeded(tmp_path)
    frame = pd.DataFrame([{
        'symbol': '600000', 'date': '2026-09-11', 'open': 9.0,
        'high': 11.0, 'low': 8.5, 'close': 10.0,
        'volume': 2000.0, 'turnover': 30000.0,
    }])
    calls = []

    def unavailable(_symbols, _day):
        calls.append('腾讯实时行情')
        raise OSError('unavailable')

    def eastmoney(_symbols, _day):
        calls.append('东方财富实时行情')
        return frame

    class Pro:
        def adj_factor(self, trade_date):
            return pd.DataFrame([{
                'ts_code': '600000.SH', 'trade_date': trade_date, 'adj_factor': 3,
            }])

    source, count = sync_realtime(
        engine.db_path,
        Pro(),
        '2026-09-11',
        providers=[('腾讯实时行情', unavailable), ('东方财富实时行情', eastmoney)],
    )

    assert (source, count) == ('东方财富实时行情', 1)
    assert calls == ['腾讯实时行情', '东方财富实时行情']
    with sqlite3.connect(engine.db_path) as conn:
        assert conn.execute(
            "SELECT open,high,low,close,volume,turnover FROM stock_daily WHERE date='2026-09-11'"
        ).fetchone() == (54, 66, 51, 60, 2000, 30000)
        assert conn.execute(
            "SELECT source,phase FROM market_data_publication WHERE date='2026-09-11'"
        ).fetchone() == ('东方财富实时行情', '15:05首版')
        assert conn.execute(
            "SELECT value FROM tushare_market_cap WHERE symbol='600000' AND date='2026-09-11'"
        ).fetchone() == (1000000,)
    import dashboard
    assert dashboard.price_source(engine.db_path).startswith('东方财富实时行情 · 15:05首版')


def test_realtime_sync_rejects_stale_trading_day(tmp_path):
    from sequoia_x.data.realtime_update import sync_realtime

    engine = seeded(tmp_path)
    stale = pd.DataFrame([{
        'symbol': '600000', 'date': '2026-09-10', 'open': 9.0,
        'high': 11.0, 'low': 8.5, 'close': 10.0,
        'volume': 2000.0, 'turnover': 30000.0,
    }])

    class Pro:
        def adj_factor(self, trade_date):
            return pd.DataFrame([{
                'ts_code': '600000.SH', 'trade_date': trade_date, 'adj_factor': 3,
            }])

    try:
        sync_realtime(engine.db_path, Pro(), '2026-09-11', providers=[('腾讯实时行情', lambda *_: stale)])
    except RuntimeError as error:
        assert '可发布' in str(error)
    else:
        raise AssertionError('stale realtime data must not publish')


def test_eastmoney_fetch_reads_every_result_page():
    from urllib.parse import parse_qs, urlparse
    from sequoia_x.data.realtime_update import fetch_eastmoney

    items = [
        {'f12': code, 'f2': 10, 'f17': 9, 'f15': 11, 'f16': 8,
         'f5': 20, 'f6': 3000, 'f124': 1789114305}
        for code in ('600000', '600001', '600002')
    ]

    def requester(url):
        page = int(parse_qs(urlparse(url).query)['pn'][0])
        start = (page - 1) * 2
        return {'data': {'total': 3, 'diff': items[start:start + 2]}}

    frame = fetch_eastmoney(
        ['600000', '600001', '600002'],
        '2026-09-11',
        requester=requester,
        page_size=2,
    )

    assert frame.symbol.tolist() == ['600000', '600001', '600002']
