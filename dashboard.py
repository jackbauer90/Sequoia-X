"""生成并提供 Sequoia-X 本地只读仪表盘。"""

import argparse
import html
import json
import os
import re
from contextlib import closing
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from selection_history import update_history, new_hits


STRATEGY_MEANINGS = {
    "均线放量": "短期均线上穿中期均线，同时成交放大，寻找刚出现转强信号的股票。",
    "高窄旗形": "一轮大幅上涨后，在高位小幅波动、成交缩量，寻找强势整理的股票。",
    "RPS 突破": "RPS 是相对价格强度：寻找近半年涨幅排名靠前、价格仍接近区间高点的股票。",
}


STRATEGY_RULES = {
    "均线放量": ["昨日 MA5 < MA20，今日 MA5 > MA20。", "当日成交量 > 20 日均量 × 1.5（均量含当日）。"],
    "高窄旗形": ["近 40 日最高价 / 最低价 > 1.6。", "近 10 日最高价 / 最低价 < 1.15。", "近 10 日最低价 ≥ 近 40 日最高价 × 80%。", "当日成交量 < 前 20 日均量 × 0.6（不含当日）。"],
    "RPS 突破": ["120 个交易日涨幅在本地有效样本中的百分位 ≥ 90。", "收盘 ≥ 近 120 日最高价 × 90%（窗口含当日）。", "这是接近高位筛选，不要求创出新高；只取数据库最新交易日样本。"],
}

ACTIVE_STRATEGIES = ("均线放量", "高窄旗形", "RPS 突破")


@dataclass(frozen=True)
class MarketSummary:
    stock_count: int
    row_count: int
    first_date: str
    latest_date: str
    latest_stock_count: int


def load_market_summary(db_path: str) -> MarketSummary:
    """从行情数据库读取页面所需的数据覆盖摘要。"""
    with closing(sqlite3.connect(db_path)) as connection:
        stock_count, row_count, first_date, latest_date = connection.execute(
            "SELECT COUNT(DISTINCT symbol), COUNT(*), MIN(date), MAX(date) FROM stock_daily"
        ).fetchone()
        latest_stock_count = connection.execute(
            "SELECT COUNT(DISTINCT symbol) FROM stock_daily WHERE date = ?",
            (latest_date,),
        ).fetchone()[0]
    return MarketSummary(
        stock_count=stock_count,
        row_count=row_count,
        first_date=first_date or "—",
        latest_date=latest_date or "—",
        latest_stock_count=latest_stock_count,
    )


def render_dashboard(
    summary: MarketSummary,
    results: dict[str, list[str]],
    generated_at: str,
    catalog: dict | None = None,
    errors: dict | None = None,
    ages: dict | None = None,
    source: str = '本地后复权日线；非当前实际成交价格。',
    new_symbols: set | None = None,
) -> str:
    """将数据摘要和策略结果渲染为单文件 HTML。"""
    strategy_sections = []
    catalog, errors = catalog or {}, errors or {}
    ages = ages or {}
    results = exclude_st({name: symbols for name, symbols in results.items() if name in ACTIVE_STRATEGIES}, catalog)
    strategy_ids = {}
    for name, symbols in results.items():
        strategy_id = "strategy-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        strategy_ids[name] = strategy_id
        escaped_name = html.escape(name)
        if symbols:
            groups = []
            for board in ("主板", "创业板", "其他"):
                members = [s for s in symbols if stock_board(s, catalog) == board]
                if members:
                    links = ''.join(f'<a href="stocks/{html.escape(s)}.html">{html.escape(catalog.get(s, {}).get("name", "名称待更新"))}' + ('<small class="new-hit">今日新增</small>' if new_symbols is not None and s in new_symbols else '') + (f'<small class="age">已记录连续命中 {ages[s]} 天</small>' if s in ages else '') + '</a>' for s in members)
                    groups.append(f'<section class="board"><h3>{board}<small>{len(members)} 只</small></h3><div class="stock-links">{links}</div></section>')
            symbol_items = ''.join(groups)
        else:
            symbol_items = '<span class="empty">暂无命中</span>'
        if name in errors:
            symbol_items = f'<p class="error">{html.escape(errors[name])}</p>'
        rules = ''.join(f'<li>{html.escape(rule)}</li>' for rule in STRATEGY_RULES.get(name, []))
        strategy_sections.append(
            f'<article class="strategy" id="{strategy_id}" aria-labelledby="{strategy_id}-title">'
            f'<header><div class="strategy-heading"><h2 id="{strategy_id}-title">{escaped_name}</h2><p class="strategy-meaning">{html.escape(STRATEGY_MEANINGS.get(name, ""))}</p></div><b>{"—" if name in errors else len(symbols)}</b></header>'
            f'<div class="strategy-body"><aside class="rules"><h3>筛选规则 · 同时满足</h3><ul>{rules}</ul></aside><div class="symbols">{symbol_items}</div></div>'
            "</article>"
        )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <meta http-equiv="refresh" content="60">
  <link rel="icon" href="data:,">
  <title>主板与创业板三策略初选股</title>
<style>{Path(__file__).with_name('ui_theme.css').read_text(encoding='utf-8')}</style>
</head>
<body>
  <main class="shell">
    <div class="tape"><span>SEQUOIA—X / MARKET RESEARCH</span><strong>只读研究 · 不推送</strong></div>
    <section class="hero">
      <div><p class="eyebrow">A-SHARE / DAILY SELECTION</p><h1>主板与创业板三策略初选股</h1></div>
      <p>三个策略独立筛选，统一剔除 ST / *ST、科创板和北交所。<br>连续命中第 1～3 个交易日显示，第 4 天起隐藏。</p>
    </section>
    <div class="status" id="backfill-status">行情覆盖以本页生成时为准。后台回填结束后自动重新扫描，页面每 60 秒更新。</div>
    <section class="metrics" aria-label="行情数据状态">
      <div class="metric"><span>股票总数</span><strong>{summary.stock_count:,}</strong></div>
      <div class="metric"><span>日线记录</span><strong>{summary.row_count:,}</strong></div>
      <div class="metric"><span>数据起点</span><strong>{html.escape(summary.first_date)}</strong></div>
      <div class="metric"><span>最新交易日</span><strong>{html.escape(summary.latest_date)}</strong></div>
      <div class="metric"><span>最新覆盖</span><strong>{summary.latest_stock_count:,}</strong></div>
    </section>
    <div class="section-title"><div><h2>策略命中</h2><p>{'缺少前一交易日记录，无法比较今日新增。' if new_symbols is None else f'今日新增 {len(new_symbols)} 只：前一交易日三策略均未命中，本交易日首次进入。跨策略合并比较。'}</p></div><span>GENERATED {html.escape(generated_at)}</span></div>
    <nav class="strategy-nav" aria-label="策略快速跳转">{"".join(f'<a href="#{strategy_ids[name]}">{html.escape(name)}<span>{"—" if name in errors else len(results[name])}</span></a>' for name in results)}</nav>
    <section class="strategies">{"".join(strategy_sections)}</section>
    <footer>按股票跨策略合并计算连续命中交易日；同日刷新不加天数，中断后重新计数。天数仅依据已保存扫描记录，缺失历史不倒推；隐藏名单仍保留在历史记录中。仅展示数据库最新交易日有行情的股票。{html.escape(source)}</footer>
  </main>
  <script>fetch('status.json?t='+Date.now()).then(r=>r.ok?r.json():null).then(s=>{{if(s)document.getElementById('backfill-status').textContent=s.message;}}).catch(()=>{{}});
  setTimeout(()=>{{const url=new URL(location.href);url.searchParams.set('refresh',Date.now());location.replace(url);}},59000);</script>
</body>
</html>"""


def _to_ts_code(symbol: str) -> str:
    if symbol.startswith("92"):
        return f"{symbol}.BJ"
    if symbol.startswith(("6", "9")):
        return f"{symbol}.SH"
    if symbol.startswith(("4", "8")):
        return f"{symbol}.BJ"
    return f"{symbol}.SZ"


def load_kline(symbol: str, db_path: str, limit: int = 120) -> tuple[pd.DataFrame, str]:
    """优先读取 Tushare 不复权日线，接口不可用时回退本地 SQLite。"""
    token = os.getenv("TUSHARE_TOKEN", "").strip()
    if token:
        try:
            import tushare as ts

            end = date.today()
            start = end - timedelta(days=limit * 2)
            frame = ts.pro_api(token).daily(
                ts_code=_to_ts_code(symbol),
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
            )
            if frame is not None and not frame.empty:
                frame = frame.rename(columns={"trade_date": "date"})
                frame["date"] = pd.to_datetime(frame["date"], format="%Y%m%d").dt.strftime(
                    "%Y-%m-%d"
                )
                columns = ["date", "open", "high", "low", "close", "vol"]
                frame = frame[columns].rename(columns={"vol": "volume"})
                return frame.sort_values("date").tail(limit).reset_index(drop=True), (
                    "Tushare 日线（不复权）"
                )
        except Exception:
            pass

    with closing(sqlite3.connect(db_path)) as connection:
        frame = pd.read_sql(
            """
            SELECT date, open, high, low, close, volume
            FROM stock_daily WHERE symbol = ? ORDER BY date DESC LIMIT ?
            """,
            connection,
            params=(symbol, limit),
        )
    return frame.sort_values("date").reset_index(drop=True), "本地 SQLite 日线（后复权兜底）"


def render_stock_page(symbol: str, frame: pd.DataFrame, source: str, name: str | None = None, board: str = "", business: str = "", age: int | None = None, business_source: str = "Tushare 上市公司信息", signals: dict | None = None) -> str:
    """将日线数据渲染为无前端依赖的 SVG K 线详情页。"""
    from strategy_chart import render_strategy_chart
    safe_symbol = html.escape(name or symbol)
    safe_source = html.escape(source)
    if not frame.empty:
        frame = frame.dropna(subset=["open", "high", "low", "close", "volume"]).sort_values("date")
    chart = render_strategy_chart(frame, signals)
    period = f"{frame.tail(120).iloc[0]['date']} — {frame.iloc[-1]['date']}" if not frame.empty else "—"
    latest = f"{float(frame.iloc[-1]['close']):.2f}" if not frame.empty else "—"

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:"><title>{safe_symbol} K线 · Sequoia-X</title>
<style>{Path(__file__).with_name('ui_theme.css').read_text(encoding='utf-8')}</style></head><body><main class="shell">
<div class="tape"><a class="back" href="../index.html">← 返回扫描台</a></div>
<header class="head"><div><div class="eyebrow">{html.escape(board)} / 日 K 线</div><h1>{safe_symbol}<span class="stock-code">{html.escape(symbol)}</span></h1></div><div class="quote"><span>最新收盘</span><strong>{latest}</strong></div></header>
<p class="business">{html.escape(business or '主营业务资料暂未获取。')}<small>业务资料：{html.escape(business_source)} · {f'已记录连续命中 {age} 个交易日' if age is not None else '暂无命中历史'}（历史记录建立前的天数未知）</small></p>
<section class="chart-card">{chart}<div class="meta"><span>{safe_source}</span><span>{html.escape(period)}</span></div></section>
</main></body></html>"""


def collect_strategy_results(db_path: str, errors: dict | None = None, catalog: dict | None = None) -> dict[str, list[str]]:
    """运行本地与联网策略；策略相互隔离，且不调用通知模块。"""
    from sequoia_x.core.config import Settings
    from sequoia_x.data.engine import DataEngine
    from sequoia_x.strategy.high_tight_flag import HighTightFlagStrategy
    from sequoia_x.strategy.ma_volume import MaVolumeStrategy
    from sequoia_x.strategy.rps_breakout import RpsBreakoutStrategy

    settings = Settings(
        db_path=db_path,
        qq_bot_api_url="http://127.0.0.1",
        qq_target_id=0,
    )
    engine = DataEngine(settings)
    strategies = {
        "均线放量": MaVolumeStrategy(engine, settings),
        "高窄旗形": HighTightFlagStrategy(engine, settings),
        "RPS 突破": RpsBreakoutStrategy(engine, settings),
    }
    results: dict[str, list[str]] = {}
    errors = errors if errors is not None else {}
    for name, strategy in strategies.items():
        try:
            results[name] = strategy.run()
            if getattr(strategy, "last_error", None):
                errors[name] = strategy.last_error
        except Exception:
            results[name] = []
            errors[name] = "本次策略运行失败，等待下次更新重试。"
    return exclude_st(latest_results(db_path, results), catalog or {})


def latest_results(db_path, results):
    with closing(sqlite3.connect(db_path)) as connection:
        symbols = {r[0] for r in connection.execute('SELECT symbol FROM stock_daily WHERE date=(SELECT MAX(date) FROM stock_daily)')}
    return {name: [s for s in items if s in symbols] for name, items in results.items()}


def price_source(db_path):
    with closing(sqlite3.connect(db_path)) as connection:
        publication = None
        if connection.execute("SELECT 1 FROM sqlite_master WHERE name='market_data_publication'").fetchone():
            publication = connection.execute(
                'SELECT source,phase FROM market_data_publication WHERE date=(SELECT MAX(date) FROM stock_daily)'
            ).fetchone()
        prefix = f'{publication[0]} · {publication[1]}；' if publication else ''
        if connection.execute("SELECT 1 FROM sqlite_master WHERE name='tushare_anchor'").fetchone():
            anchor = connection.execute('SELECT MIN(date) FROM tushare_anchor').fetchone()[0]
            if anchor:
                return prefix + f'BaoStock 历史后复权 + 当日行情及Tushare复权因子；以 {anchor} 同日收盘校准价格尺度。未统一重算全部历史，与策略计算一致；非当前实际成交价格。'
    return prefix + '本地后复权日线（与策略计算一致；非当前实际成交价格）'


def exclude_st(results: dict[str, list[str]], catalog: dict) -> dict[str, list[str]]:
    """统一剔除风险警示、科创板和北交所股票。"""
    return {
        strategy: [symbol for symbol in symbols
                   if not re.match(r"^(?:S)?\*?ST", re.sub(r"\s+", "", catalog.get(symbol, {}).get("name", "")).upper())
                   and stock_board(symbol, catalog) not in ("科创板", "北交所")]
        for strategy, symbols in results.items()
    }


def stock_board(symbol: str, catalog: dict) -> str:
    market = catalog.get(symbol, {}).get("market", "")
    if market in ("主板", "创业板", "科创板", "北交所"):
        return market
    if symbol.startswith(("4", "8", "92")):
        return "北交所"
    if symbol.startswith(("300", "301")):
        return "创业板"
    if symbol.startswith(("688", "689")):
        return "科创板"
    if symbol.startswith(("000", "001", "002", "003", "600", "601", "603", "605")):
        return "主板"
    return "其他"


def load_catalog() -> dict:
    cache = Path("data/stock_catalog.json")
    try:
        import tushare as ts
        frame = ts.pro_api(os.environ["TUSHARE_TOKEN"]).stock_basic(list_status="L", fields="symbol,name,market")
        if frame is None or frame.empty:
            raise ValueError("empty catalog")
        catalog = {str(row.symbol): {"name": row.name, "market": row.market} for row in frame.itertuples(index=False)}
        atomic_write(cache, json.dumps(catalog, ensure_ascii=False))
        return catalog
    except Exception:
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        raise RuntimeError("无法获取股票名称，且无本地名称缓存；保留旧网页。") from None


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def business_sentence(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text or text.lower() in ("none", "nan"):
        return ""
    sentence = re.split(r"[。\n]", text)[0].strip("；; ")
    return sentence[:140].rstrip("，,；;") + ("……" if len(sentence) > 140 else "。")


def load_businesses(symbols: list[str] | None = None) -> dict:
    cache = Path("data/company_business.json")
    businesses = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    import tushare as ts
    pro = ts.pro_api(os.environ.get("TUSHARE_TOKEN", ""))
    for exchange in ("SSE", "SZSE", "BSE"):
        try:
            frame = pro.stock_company(exchange=exchange, fields="ts_code,main_business")
            for row in frame.itertuples(index=False):
                sentence = business_sentence(row.main_business)
                if sentence:
                    businesses[row.ts_code.split('.')[0]] = {"text": sentence, "source": "Tushare 上市公司信息"}
        except Exception:
            print(f"Company information unavailable: {exchange}; using cached records.")
    if symbols:
        from concurrent.futures import ThreadPoolExecutor
        import akshare as ak

        def fetch_profile(symbol):
            try:
                frame = ak.stock_profile_cninfo(symbol=symbol)
                sentence = business_sentence(frame.iloc[0]['主营业务'])
                return symbol, {"text": sentence, "source": "巨潮资讯 · 公司概况"} if sentence else None
            except Exception:
                return symbol, None

        missing = [s for s in symbols if s not in businesses]
        with ThreadPoolExecutor(max_workers=4) as pool:
            for symbol, profile in pool.map(fetch_profile, missing):
                if profile:
                    businesses[symbol] = profile
    atomic_write(cache, json.dumps(businesses, ensure_ascii=False))
    return businesses


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 Sequoia-X 本地只读仪表盘")
    parser.add_argument("--db", default="data/sequoia_v2.db")
    parser.add_argument("--output", default="site/index.html")
    parser.add_argument("--offline", action="store_true", help="使用已有命中记录和资料重建页面，不联网、不发送通知")
    args = parser.parse_args()

    summary = load_market_summary(args.db)
    catalog = json.loads(Path("data/stock_catalog.json").read_text(encoding="utf-8")) if args.offline else load_catalog()
    errors = {}
    history_path = Path(args.db).parent / "selection_history.json"
    results = json.loads(history_path.read_text(encoding="utf-8"))["snapshots"][summary.latest_date] if args.offline else collect_strategy_results(args.db, errors, catalog)
    results = exclude_st({name: symbols for name, symbols in results.items() if name in ACTIVE_STRATEGIES}, catalog)
    if errors:
        raise RuntimeError("策略未完整运行，本次保留上一版网页与历史记录。")
    with closing(sqlite3.connect(args.db)) as connection:
        trading_days = [r[0] for r in connection.execute("SELECT DISTINCT date FROM stock_daily ORDER BY date")]
    results, ages = update_history(Path(args.db).parent / "selection_history.json", summary.latest_date, results, trading_days, persist=not args.offline)
    businesses = json.loads(Path("data/company_business.json").read_text(encoding="utf-8")) if args.offline else load_businesses(sorted({s for items in results.values() for s in items}))
    snapshots = json.loads(history_path.read_text(encoding="utf-8"))["snapshots"]
    active_snapshots = {day: {name: items for name, items in selected.items() if name in ACTIVE_STRATEGIES} for day, selected in snapshots.items()}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    stock_dir = output.parent / "stocks"
    stock_dir.mkdir(parents=True, exist_ok=True)
    symbols = sorted({symbol for items in results.values() for symbol in items})
    for symbol in symbols:
        if len(symbol) != 6 or not symbol.isdigit():
            continue
        with closing(sqlite3.connect(args.db)) as connection:
            frame = pd.read_sql_query("SELECT date,open,high,low,close,volume FROM stock_daily WHERE symbol=? AND date<=? ORDER BY date", connection, params=(symbol, summary.latest_date))
        source = price_source(args.db)
        signals = {day: [name for name, items in selected.items() if symbol in items] for day, selected in active_snapshots.items()}
        profile = businesses.get(symbol, {})
        atomic_write(stock_dir / f"{symbol}.html", render_stock_page(symbol, frame, source, catalog.get(symbol, {}).get("name", "名称待更新"), stock_board(symbol, catalog), profile.get("text", ""), ages[symbol], profile.get("source", "暂无可用资料"), signals))
    atomic_write(output, render_dashboard(summary, results, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), catalog, errors, ages, source=price_source(args.db), new_symbols=new_hits(snapshots, summary.latest_date, trading_days, active_strategies=set(ACTIVE_STRATEGIES))))
    print(output.resolve())


# editorial_render_hook: preserve current scanner output in the responsive editorial page.
_render_dashboard_original = render_dashboard

def render_dashboard(*args, **kwargs):
    from server_renderer import render_editorial
    return render_editorial(_render_dashboard_original(*args, **kwargs))


if __name__ == "__main__":
    main()
