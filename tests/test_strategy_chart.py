import pandas as pd
from dashboard import render_stock_page
from strategy_chart import chart_indicators, strategy_levels


def prices():
    return pd.DataFrame({'date': pd.date_range('2026-01-01', periods=180).strftime('%Y-%m-%d'), 'open': range(1,181), 'close': range(1,181), 'high': range(2,182), 'low': range(0,180), 'volume': [100]*180})


def test_page_includes_warmed_up_moving_averages():
    page = render_stock_page('000001', prices(), '本地后复权')
    assert page.count('class="ma-line"') == 4
    assert 'MA60 150.50' in page
    assert page.count('class="candle-body') == 120


def test_thresholds_do_not_use_future_prices():
    frame = prices()
    frame.loc[150:, 'high'] = 9999
    assert strategy_levels(frame, 120, '海龟突破（联网）')[0][1] == 121
    assert strategy_levels(frame, 120, 'RPS 突破')[1][1] == 109.8
    assert chart_indicators(frame).iloc[60].MA60 == 31.5
