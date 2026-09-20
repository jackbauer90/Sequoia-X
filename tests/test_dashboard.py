"""本地只读仪表盘测试。"""

from html.parser import HTMLParser

import pandas as pd

from dashboard import (
    MarketSummary,
    collect_strategy_results,
    render_dashboard,
    render_stock_page,
    stock_board,
    _to_ts_code,
    exclude_st,
    _render_dashboard_original as render_dashboard_html,
)


class _RefreshMetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.refresh_seconds: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "meta" and attributes.get("http-equiv") == "refresh":
            self.refresh_seconds = attributes.get("content")


def test_dashboard_renders_market_status_and_strategy_results() -> None:
    """若数据状态或策略命中从页面消失，此测试应失败。"""
    summary = MarketSummary(
        stock_count=5216,
        row_count=123456,
        first_date="2024-01-02",
        latest_date="2026-09-08",
        latest_stock_count=5188,
    )
    results = {
        "均线放量": ["000001", "600519"],
        "高窄旗形": [],
    }

    page = render_dashboard_html(summary, results, generated_at="2026-09-08 19:00:00")

    assert "5,216" in page
    assert "123,456" in page
    assert "2026-09-08" in page
    assert "均线放量" in page
    assert "000001" in page
    assert "600519" in page
    assert 'href="stocks/000001.html"' in page
    assert "xueqiu.com" not in page
    assert "高窄旗形" in page
    assert "暂无命中" in page


def test_dashboard_escapes_strategy_content() -> None:
    """若外部文本能注入页面标签，此测试应失败。"""
    summary = MarketSummary(1, 1, "2026-09-08", "2026-09-08", 1)

    page = render_dashboard_html(
        summary,
        {"均线放量": ["000001"]},
        generated_at="2026-09-08 19:00:00",
        catalog={"000001": {"name": "<script>alert(1)</script>"}},
    )

    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_dashboard_runs_only_the_three_retained_strategies(
    tmp_path, monkeypatch
) -> None:
    """已移除的策略不能进入扫描结果。"""
    monkeypatch.setattr(
        "sequoia_x.strategy.private_placement.PrivatePlacementStrategy.run",
        lambda self: ["000001"],
    )
    db_path = tmp_path / "market.db"
    import sqlite3
    from tests.test_data_engine import make_engine_in
    engine, _ = make_engine_in(str(tmp_path))
    db_path = engine.db_path
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO stock_daily(symbol,date,close) VALUES('600000','2026-09-08',10)")

    results = collect_strategy_results(str(db_path))

    assert set(results) == {"均线放量", "高窄旗形", "RPS 突破"}
    assert "海龟突破（联网）" not in results
    assert "涨停洗盘" not in results
    assert "定增公告（联网）" not in results
    assert "趋势跌停" not in results


def test_dashboard_does_not_render_removed_sections_from_old_snapshot():
    summary = MarketSummary(1, 1, "2026-09-08", "2026-09-08", 1)
    page = render_dashboard(summary, {
        "均线放量": ["600000"],
        "高窄旗形": [],
        "RPS 突破": [],
        "海龟突破（联网）": ["600000"],
        "涨停洗盘": ["600000"],
    }, "now")

    assert "均线放量" in page
    assert "高窄旗形" in page
    assert "RPS 突破" in page
    assert "海龟突破（联网）" not in page
    assert "涨停洗盘" not in page


def test_stock_page_renders_candles_volume_source_and_back_link() -> None:
    """详情页必须真正包含 K 线、成交量、来源说明和返回入口。"""
    frame = pd.DataFrame(
        [
            {
                "date": "2026-09-07",
                "open": 10.0,
                "high": 11.0,
                "low": 9.8,
                "close": 10.8,
                "volume": 1000,
            },
            {
                "date": "2026-09-08",
                "open": 10.8,
                "high": 11.2,
                "low": 10.1,
                "close": 10.3,
                "volume": 1200,
            },
        ]
    )

    page = render_stock_page("000001", frame, "Tushare 日线（不复权）")

    assert "000001" in page
    assert "Tushare 日线（不复权）" in page
    assert page.count('class="candle-body') == 2
    assert page.count('class="volume-bar') == 2
    assert 'href="../index.html"' in page


def test_dashboard_refreshes_to_pick_up_background_backfill_progress() -> None:
    """若页面不再自动读取后台生成的新版本，此测试应失败。"""
    summary = MarketSummary(1, 1, "2026-09-08", "2026-09-08", 1)
    parser = _RefreshMetaParser()

    parser.feed(render_dashboard(summary, {}, "2026-09-08 19:00:00"))

    assert parser.refresh_seconds == "60"


def test_names_boards_and_failures_are_visible():
    catalog = {"000001": {"name": "平安银行", "market": "主板"}, "300750": {"name": "宁德时代", "market": "创业板"}}
    page = render_dashboard_html(MarketSummary(2, 2, "2026-09-08", "2026-09-08", 2), {"均线放量": list(catalog), "高窄旗形": []}, "now", catalog, {"高窄旗形": "接口访问失败"})
    assert '>平安银行</a>' in page
    assert '>宁德时代</a>' in page
    assert '>000001</a>' not in page
    assert '创业板' in page and '主板' in page
    assert '接口访问失败' in page
    assert stock_board('920001', {}) == '北交所'
    assert _to_ts_code('920001') == '920001.BJ'


def test_st_exclusion_applies_to_every_strategy_and_counts():
    names = ['ST测试', '*ST测试', 'S*ST测试', 'SST测试', ' st 测试', '平安银行']
    catalog = {str(i): {'name': name} for i, name in enumerate(names)}
    results = {'均线放量': list(catalog), '高窄旗形': list(catalog)}
    assert exclude_st(results, catalog) == {'均线放量': ['5'], '高窄旗形': ['5']}
    page = render_dashboard_html(MarketSummary(6, 6, 'today', 'today', 6), results, 'now', catalog)
    assert 'ST测试' not in page
    assert page.count('>平安银行</a>') == 2


def test_star_market_and_beijing_exchange_never_enter_strategy_results():
    """若任一策略重新放入科创板或北交所股票，此测试应失败。"""
    catalog = {
        "600000": {"name": "浦发银行", "market": "主板"},
        "300750": {"name": "宁德时代", "market": "创业板"},
        "688001": {"name": "华兴源创", "market": "科创板"},
        "920001": {"name": "北交样本", "market": "北交所"},
    }
    results = {
        "均线放量": ["600000", "688001", "920001"],
        "RPS 突破": ["300750", "688001", "920001"],
    }

    assert exclude_st(results, catalog) == {
        "均线放量": ["600000"],
        "RPS 突破": ["300750"],
    }
