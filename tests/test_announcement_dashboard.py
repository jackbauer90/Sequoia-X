from datetime import date, timedelta
from types import SimpleNamespace

import akshare
import pandas as pd

from sequoia_x.strategy.private_placement import PrivatePlacementStrategy


def test_announcement_excludes_future_issue_dates(monkeypatch):
    today = date.today()
    frame = pd.DataFrame({
        "股票代码": ["000001", "000002", "000003"],
        "发行方式": ["定向增发"] * 3,
        "发行日期": [today, today + timedelta(days=1), today - timedelta(days=8)],
    })
    monkeypatch.setattr(akshare, "stock_qbzf_em", lambda: frame)
    strategy = PrivatePlacementStrategy(SimpleNamespace(), SimpleNamespace())
    assert strategy.run() == ["000001"]


def test_announcement_failure_is_not_reported_as_no_hits(monkeypatch):
    def offline():
        raise ConnectionError("offline")
    monkeypatch.setattr(akshare, "stock_qbzf_em", offline)
    strategy = PrivatePlacementStrategy(SimpleNamespace(), SimpleNamespace())
    assert strategy.run() == []
    assert "无法判断" in strategy.last_error
