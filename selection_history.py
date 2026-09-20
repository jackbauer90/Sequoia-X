"""按行情交易日保存原始命中，隐藏连续命中超过三个交易日的股票。"""
import json
from pathlib import Path


def new_hits(snapshots, trade_date, trading_days, active_strategies=None):
    previous = sorted(day for day in trading_days if day < trade_date)
    if not previous or previous[-1] not in snapshots or trade_date not in snapshots:
        return None
    today = {s for name, items in snapshots[trade_date].items() if active_strategies is None or name in active_strategies for s in items}
    yesterday = {s for name, items in snapshots[previous[-1]].items() if active_strategies is None or name in active_strategies for s in items}
    return today - yesterday


def update_history(path: Path, trade_date: str, results: dict, trading_days: list[str], persist: bool = True):
    history = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"snapshots": {}}
    snapshots = history["snapshots"]
    # 保留全部原始命中，不能把已隐藏股票从历史中移除。
    snapshots[trade_date] = results
    sets = {day: {s for name, items in values.items() if name in results for s in items} for day, values in snapshots.items()}
    ages = {}
    for symbol in sets[trade_date]:
        count = 0
        for day in reversed(sorted(d for d in trading_days if d <= trade_date)):
            if day not in sets or symbol not in sets[day]:
                break
            count += 1
        ages[symbol] = count
    visible = {name: [s for s in symbols if ages[s] <= 3] for name, symbols in results.items()}
    if persist:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    return visible, ages
