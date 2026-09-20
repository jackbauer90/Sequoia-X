"""收盘后增量取数、校验、扫描及发布；不导入或调用通知模块。"""
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile

from dashboard import atomic_write, load_market_summary
from sequoia_x.data.realtime_update import sync_realtime
from sequoia_x.data.tushare_update import client, trading_days, sync_tushare

SCHEDULE = '北京时间15:05腾讯实时首版（失败切东财），18:30 Tushare正式补全；覆盖不足时保留上一版；不发送QQ推送。'


def target_day(trading_days, now):
    cutoff = now.date() if (now.hour, now.minute) >= (15, 5) else now.date() - timedelta(days=1)
    return max(day for day in trading_days if day <= cutoff.isoformat())


def validate_coverage(actual, expected, count, previous_count):
    if actual != expected or count < max(1, previous_count * .98):
        raise RuntimeError('行情日期未到目标日或覆盖不足前次的98%，保留旧页面')


def update_phase(now):
    return 'tushare' if (now.hour, now.minute) >= (18, 30) else 'realtime'


def latest_closed_day(now):
    return target_day(trading_days(client(), (now.date() - timedelta(days=45)).isoformat(), now.date().isoformat()), now)


def update_once(root, status):
    data, site = root / 'data', root / 'site'
    now = datetime.now(ZoneInfo('Asia/Shanghai'))
    status('正在检查最新已收盘交易日；完成前继续展示上一版结果。')
    expected = latest_closed_day(now)
    previous = load_market_summary(str(data / 'sequoia_v2.db'))
    # 数据和命中历史在临时副本中更新，校验或生成失败不污染正式数据。
    (root / 'output').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='daily-', dir=root / 'output') as directory:
        stage = Path(directory)
        (stage / 'data').mkdir()
        for name in ('stock_catalog.json', 'company_business.json', 'selection_history.json'):
            shutil.copy2(data / name, stage / 'data' / name)
        staged_db = stage / 'data/sequoia_v2.db'
        with sqlite3.connect(data / 'sequoia_v2.db') as source, sqlite3.connect(staged_db) as destination:
            source.backup(destination)
        pro = client()
        phase = update_phase(now)
        if phase == 'realtime':
            realtime_source, added = sync_realtime(str(staged_db), pro, expected)
            published = expected
            current = load_market_summary(str(staged_db))
            validate_coverage(current.latest_date, published, current.latest_stock_count, previous.latest_stock_count)
            status(f'{realtime_source} 已形成{published}收盘首版，正在重跑三策略与生成K线。')
            result = subprocess.run([sys.executable, str(root / 'dashboard.py'), '--db', str(staged_db), '--output', str(stage / 'site/index.html')], cwd=stage, capture_output=True)
            if result.returncode:
                raise RuntimeError('策略扫描或网页生成失败')
        else:
            dates = [day for day in trading_days(pro, previous.latest_date, expected) if day > previous.latest_date] or [previous.latest_date]
            added = 0
            for day in dates:
                published, written = sync_tushare(str(staged_db), pro, day)
                if not written:
                    continue
                added += written
                current = load_market_summary(str(staged_db))
                validate_coverage(current.latest_date, published, current.latest_stock_count, previous.latest_stock_count)
                status(f'Tushare 已拉取正式行情至{published}，正在重跑三策略与生成K线。')
                # 按交易日补扫描快照，保证“今日新增”能与真正的前一交易日比较。
                result = subprocess.run([sys.executable, str(root / 'dashboard.py'), '--db', str(staged_db), '--output', str(stage / 'site/index.html')], cwd=stage, capture_output=True)
                if result.returncode:
                    raise RuntimeError('策略扫描或网页生成失败')
            if not added:
                status(f'Tushare 暂无可发布的新行情；当前仍为{previous.latest_date}，目标交易日{expected}。')
                return False
        # 先发布详情，首页最后替换；旧详情保留，已打开的链接仍可访问。
        (site / 'stocks').mkdir(exist_ok=True)
        for path in (stage / 'site/stocks').glob('*.html'):
            atomic_write(site / 'stocks' / path.name, path.read_text(encoding='utf-8'))
        shutil.copy2(data / 'sequoia_v2.db', data / 'sequoia_v2.previous.db')
        staged_db.replace(data / 'sequoia_v2.db')
        for path in (stage / 'data').glob('*.json'):
            path.replace(data / path.name)
        atomic_write(site / 'index.html', (stage / 'site/index.html').read_text(encoding='utf-8'))
        if phase == 'realtime':
            status(f'{realtime_source} 15:05首版更新完成：行情截至{published}，覆盖{current.latest_stock_count}只；18:30由Tushare正式补全。')
        else:
            pending = f'目标日{expected}尚未发布，等待后续补数据。' if published < expected else ''
            status(f'Tushare 18:30补全完成：行情截至{published}，当日覆盖{current.latest_stock_count}只，写入{added}条。{pending}更新现有股票池，覆盖数以页面统计为准。')
        print(f'phase={phase} published date={published} coverage={current.latest_stock_count} rows={added}', flush=True)
        return True


def main():
    root = Path(__file__).resolve().parent
    site = root / 'site'
    zone = ZoneInfo('Asia/Shanghai')

    def status(message):
        atomic_write(site / 'status.json', json.dumps({'message': message + ' ' + SCHEDULE, 'updated_at': datetime.now(zone).isoformat()}, ensure_ascii=False))

    try:
        update_once(root, status)
    except Exception as error:
        status('本次更新失败，仍展示上一版结果；请查看行情日期。后续定时任务会重试。')
        print(f'update_failed: {type(error).__name__}', file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
