import sqlite3

import pandas as pd
import pytest

from tests.test_data_engine import make_engine_in


class Feed:
    def daily(self, trade_date):
        if trade_date == '20260910':
            return pd.DataFrame()
        close = 10 if trade_date == '20260908' else 6
        return pd.DataFrame([dict(ts_code='000001.SZ', trade_date=trade_date,
                                  open=close, high=close+1, low=close-1, close=close,
                                  vol=10, amount=20)])

    def adj_factor(self, trade_date):
        return pd.DataFrame([dict(ts_code='000001.SZ', trade_date=trade_date,
                                  adj_factor=2 if trade_date == '20260908' else 4)])

    def trade_cal(self, **kwargs):
        return pd.DataFrame({'cal_date': ['20260908', '20260909', '20260910'], 'is_open': [1, 1, 1]})

    def daily_basic(self, trade_date, fields):
        return pd.DataFrame([dict(ts_code='000001.SZ', trade_date=trade_date, circ_mv=100)])


def seeded(tmp_path):
    engine, _ = make_engine_in(str(tmp_path))
    with sqlite3.connect(engine.db_path) as conn:
        conn.execute("INSERT INTO stock_daily(symbol,date,open,high,low,close,volume,turnover) VALUES('000001','2026-09-08',20,22,18,20,1000,20000)")
    return engine


def test_tushare_update_preserves_price_basis_units_and_unpublished_date(tmp_path):
    import sequoia_x.data.tushare_update as source
    engine = seeded(tmp_path)
    result = source.sync_tushare(engine.db_path, Feed(), '2026-09-10')
    assert result == ('2026-09-09', 1)
    with sqlite3.connect(engine.db_path) as conn:
        assert conn.execute("SELECT date,open,high,low,close,volume,turnover FROM stock_daily ORDER BY date DESC LIMIT 1").fetchone() == ('2026-09-09', 24, 28, 20, 24, 1000, 20000)
        assert conn.execute("SELECT close FROM stock_daily WHERE date='2026-09-08'").fetchone()[0] == 20
        assert conn.execute(
            "SELECT source,phase FROM market_data_publication WHERE date='2026-09-09'"
        ).fetchone() == ('Tushare正式日线', '18:30补全')
    assert source.sync_tushare(engine.db_path, Feed(), '2026-09-10') == ('2026-09-09', 0)
    with sqlite3.connect(engine.db_path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM stock_daily').fetchone()[0] == 2
    from sequoia_x.strategy.turtle_trade import TurtleTradeStrategy
    assert TurtleTradeStrategy(engine, None)._get_market_caps(['000001']) == {'000001': 1000000}


def test_missing_adjustment_cannot_create_unadjusted_prices(tmp_path):
    import sequoia_x.data.tushare_update as source
    engine = seeded(tmp_path)
    feed = Feed()
    feed.adj_factor = lambda trade_date: pd.DataFrame()
    with pytest.raises(RuntimeError):
        source.sync_tushare(engine.db_path, feed, '2026-09-09')
    assert len(engine.get_ohlcv('000001')) == 1


def test_partial_day_cannot_publish(tmp_path):
    import sequoia_x.data.tushare_update as source
    engine = seeded(tmp_path)
    with sqlite3.connect(engine.db_path) as conn:
        conn.execute("INSERT INTO stock_daily(symbol,date,close) VALUES('000002','2026-09-08',10)")
    with pytest.raises(RuntimeError):
        source.sync_tushare(engine.db_path, Feed(), '2026-09-09')
    assert len(engine.get_ohlcv('000001')) == 1


def test_latest_filter_does_not_report_stale_stock_as_today(tmp_path):
    import dashboard
    engine = seeded(tmp_path)
    with sqlite3.connect(engine.db_path) as conn:
        conn.execute("INSERT INTO stock_daily(symbol,date,close) VALUES('000002','2026-09-09',10)")
    assert dashboard.latest_results(engine.db_path, {'策略': ['000001', '000002']}) == {'策略': ['000002']}


def test_page_discloses_mixed_history_and_tushare_update(tmp_path):
    import dashboard
    import sequoia_x.data.tushare_update as source
    engine = seeded(tmp_path)
    source.sync_tushare(engine.db_path, Feed(), '2026-09-09')
    description = dashboard.price_source(engine.db_path)
    page = dashboard.render_dashboard(dashboard.load_market_summary(engine.db_path), {}, 'now', source=description)
    assert 'Tushare正式日线 · 18:30补全' in page and 'BaoStock' in page and '2026-09-08' in page
