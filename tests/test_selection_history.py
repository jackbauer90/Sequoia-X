import json
import pandas as pd
from dashboard import render_stock_page
from selection_history import update_history


def test_same_day_weekend_fourth_day_and_reentry(tmp_path):
    path = tmp_path / 'history.json'
    days = ['2026-09-03', '2026-09-04', '2026-09-07', '2026-09-08', '2026-09-09', '2026-09-10']
    hits = {'A': ['000001'], 'B': ['000001']}
    for index, day in enumerate(days[:4], 1):
        visible, ages = update_history(path, day, hits, days)
        assert ages['000001'] == index
        assert bool(visible['A']) == (index <= 3)
        assert update_history(path, day, hits, days)[1]['000001'] == index
    assert json.loads(path.read_text(encoding='utf-8'))['snapshots'][days[3]]['A'] == ['000001']
    update_history(path, days[4], {'A': [], 'B': []}, days)
    assert update_history(path, days[5], hits, days)[1]['000001'] == 1


def test_missing_scan_does_not_fabricate_consecutive_days(tmp_path):
    days = ['2026-09-07', '2026-09-08', '2026-09-09']
    path = tmp_path / 'history.json'
    update_history(path, days[0], {'A': ['000001']}, days)
    assert update_history(path, days[2], {'A': ['000001']}, days)[1]['000001'] == 1


def test_detail_shows_name_code_business_and_age():
    page = render_stock_page('000001', pd.DataFrame(), 'local', '平安银行', '主板', '主要从事商业银行业务。', 2)
    assert '平安银行<span class="stock-code">000001</span>' in page
    assert '主要从事商业银行业务。' in page
    assert '已记录连续命中 2 个交易日' in page


def test_new_hits_compare_previous_trading_day_across_all_strategies():
    from selection_history import new_hits
    snapshots = {'2026-09-04': {'A': ['000001', '000002']},
                 '2026-09-07': {'A': ['000003'], 'B': ['000001']}}
    assert new_hits(snapshots, '2026-09-07', ['2026-09-04', '2026-09-07']) == {'000003'}
    assert new_hits(snapshots, '2026-09-07', ['2026-09-03', '2026-09-04', '2026-09-07']) == {'000003'}
    assert new_hits(snapshots, '2026-09-07', ['2026-09-06', '2026-09-07']) is None


def test_removed_strategy_history_does_not_suppress_new_hit_or_extend_age(tmp_path):
    from selection_history import new_hits
    days = ['2026-09-08', '2026-09-09']
    path = tmp_path / 'history.json'
    update_history(path, days[0], {'海龟突破（联网）': ['000001']}, days)
    visible, ages = update_history(path, days[1], {'均线放量': ['000001']}, days)
    snapshots = json.loads(path.read_text(encoding='utf-8'))['snapshots']

    assert visible == {'均线放量': ['000001']}
    assert ages['000001'] == 1
    assert new_hits(snapshots, days[1], days, active_strategies={'均线放量'}) == {'000001'}


def test_offline_render_keeps_original_historical_snapshot(tmp_path):
    path = tmp_path / 'history.json'
    days = ['2026-09-08']
    original = {'均线放量': ['000001'], '海龟突破（联网）': ['000002']}
    update_history(path, days[0], original, days)

    visible, ages = update_history(path, days[0], {'均线放量': ['000001']}, days, persist=False)

    assert visible == {'均线放量': ['000001']}
    assert ages == {'000001': 1}
    assert json.loads(path.read_text(encoding='utf-8'))['snapshots'][days[0]] == original


def test_new_hit_badge_is_only_on_new_stock():
    from dashboard import _render_dashboard_original, MarketSummary
    page = _render_dashboard_original(MarketSummary(2, 2, '2026-09-08', '2026-09-09', 2),
                            {'均线放量': ['000001', '000002']}, 'now',
                            new_symbols={'000002'})
    assert page.count('class="new-hit"') == 1
    assert '今日新增' in page
    assert '000002.html">名称待更新<small class="new-hit"' in page
