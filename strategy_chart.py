"""在同一后复权价格坐标中绘制均线、已记录信号与策略门槛。"""
import html
import json
from pathlib import Path
import pandas as pd

MA_COLORS = {5: '#cc7b16', 10: '#a448be', 20: '#2473cf', 60: '#168777'}
STRATEGY_COLORS = {'均线放量': '#ba6519', '海龟突破（联网）': '#187b89', '高窄旗形': '#9753ac', '涨停洗盘': '#bb4455', 'RPS 突破': '#5265b0'}


def chart_indicators(frame):
    frame = frame.sort_values('date').reset_index(drop=True).copy()
    for period in MA_COLORS:
        frame[f'MA{period}'] = frame.close.rolling(period).mean()
    frame['turtle'] = frame.high.shift(1).rolling(20).max()
    frame['rps_high'] = frame.high.rolling(120, min_periods=60).max()
    frame['rps_gate'] = frame.rps_high * .9
    frame['vol20'] = frame.volume.rolling(20).mean()
    return frame


def strategy_levels(frame, index, strategy):
    past = frame.iloc[:index + 1]
    if strategy == '海龟突破（联网）' and len(past) >= 21:
        return [('前20日突破线', past.high.iloc[-21:-1].max(), 20)]
    if strategy == '高窄旗形' and len(past) >= 40:
        return [('40日高点', past.high.tail(40).max(), 40), ('10日整理上沿', past.high.tail(10).max(), 10), ('10日整理下沿', past.low.tail(10).min(), 10), ('高位门槛（40日高点×80%）', past.high.tail(40).max() * .8, 10)]
    if strategy == '涨停洗盘' and len(past) >= 3:
        return [('昨收支撑', past.close.iloc[-2], 2)]
    if strategy == 'RPS 突破' and len(past) >= 120:
        high = past.high.tail(120).max()
        return [('120日高点', high, 120), ('RPS高位门槛（高点×90%）', high * .9, 120)]
    return []


def render_strategy_chart(frame, signals=None):
    signals = signals or {}
    if frame.empty:
        return '<p>暂无可用行情，无法绘制策略标记。</p>'
    full = chart_indicators(frame)
    start = max(0, len(full) - 120)
    visible = full.iloc[start:]
    index_by_date = {str(row.date): i for i, row in enumerate(full.itertuples())}
    markers = [(index_by_date[day], strategy) for day, names in signals.items() if day in index_by_date for strategy in names if index_by_date[day] >= start]
    # 每个策略只绘制最近一次记录对应的门槛，所有已记录信号日保留圆点。
    latest = {strategy: max(i for i, s in markers if s == strategy) for _, strategy in markers}
    levels = [(strategy, index, label, float(value), period) for strategy, index in latest.items() for label, value, period in strategy_levels(full, index, strategy)]
    extent = list(visible.low) + list(visible.high)
    for period in MA_COLORS:
        extent += visible[f'MA{period}'].dropna().tolist()
    extent += [value for _, _, _, value, _ in levels]
    bottom, top = min(extent), max(extent)
    padding = (top - bottom or 1) * .08
    bottom, top = bottom - padding, top + padding
    x = lambda i: 64 + (i - start + .5) * 900 / len(visible)
    y = lambda value: 350 - (value - bottom) / (top - bottom) * 300
    max_vol = max(float(visible.volume.max()), 1)
    vy = lambda value: 495 - value / max_vol * 95
    width = min(12, 900 / len(visible) * .6)
    parts = []
    for step in range(5):
        price = bottom + (top-bottom)*step/4
        parts.append(f'<line x1="64" x2="964" y1="{y(price):.2f}" y2="{y(price):.2f}" stroke="#dce4eb"/><text x="8" y="{y(price)+4:.2f}" fill="#587082" font-size="11">{price:.2f}</text>')
    for i in range(start, len(full)):
        row = full.iloc[i]
        color = '#c73b32' if row.close >= row.open else '#168078'
        tip = html.escape(f'{row.date} 开 {row.open:.2f} 高 {row.high:.2f} 低 {row.low:.2f} 收 {row.close:.2f} 成交量 {row.volume:,.0f} 股')
        parts.append(f'<g><title>{tip}</title><line x1="{x(i):.2f}" x2="{x(i):.2f}" y1="{y(row.high):.2f}" y2="{y(row.low):.2f}" stroke="{color}"/><rect class="candle-body" x="{x(i)-width/2:.2f}" y="{min(y(row.open),y(row.close)):.2f}" width="{width:.2f}" height="{max(1.5,abs(y(row.open)-y(row.close))):.2f}" fill="{color}"/><rect class="volume-bar" x="{x(i)-width/2:.2f}" y="{vy(row.volume):.2f}" width="{width:.2f}" height="{495-vy(row.volume):.2f}" fill="{color}" opacity=".4"/></g>')
    legend = []
    for period, color in MA_COLORS.items():
        points = ' '.join(f'{x(i):.2f},{y(full.iloc[i][f"MA{period}"]):.2f}' for i in range(start,len(full)) if pd.notna(full.iloc[i][f'MA{period}']))
        if points:
            parts.append(f'<polyline class="ma-line" data-period="{period}" points="{points}" fill="none" stroke="{color}" stroke-width="1.8"><title>MA{period}</title></polyline>')
            legend.append(f'<span style="color:{color}">━ MA{period} {full.iloc[-1][f"MA{period}"]:.2f}</span>')
    volume_points = ' '.join(f'{x(i):.2f},{vy(full.iloc[i].vol20):.2f}' for i in range(start,len(full)) if pd.notna(full.iloc[i].vol20))
    parts.append(f'<polyline points="{volume_points}" fill="none" stroke="#687b91" stroke-width="1.4" stroke-dasharray="3 2"><title>20日均量（含当日）</title></polyline>')
    descriptions = []
    for strategy, index, label, value, period in levels:
        color = STRATEGY_COLORS.get(strategy, '#5265b0')
        caption = f'{strategy} · {label} {value:.2f}（{full.iloc[index].date}）'
        parts.append(f'<line class="strategy-level" x1="{x(max(start,index-period+1)):.2f}" x2="{x(index):.2f}" y1="{y(value):.2f}" y2="{y(value):.2f}" stroke="{color}" stroke-width="1.5" stroke-dasharray="6 4"><title>{html.escape(caption)}</title></line>')
        descriptions.append(f'<li style="color:{color}">{html.escape(caption)}</li>')
    for index, strategy in markers:
        row = full.iloc[index]
        color = STRATEGY_COLORS.get(strategy, '#5265b0')
        title = f'{row.date} · {strategy} · 已记录命中 · 收盘 {row.close:.2f}'
        parts.append(f'<circle class="signal-point" data-date="{row.date}" cx="{x(index):.2f}" cy="{y(row.close):.2f}" r="6" fill="white" stroke="{color}" stroke-width="2.5"><title>{html.escape(title)}</title></circle>')
        if index == latest[strategy]:
            evidence = ''
            if strategy == '均线放量':
                prev = full.iloc[index-1] if index else row
                evidence = f'；昨日 MA5/MA20 {prev.MA5:.2f}/{prev.MA20:.2f} → 当日 {row.MA5:.2f}/{row.MA20:.2f}；成交量/20日均量 {row.volume/row.vol20:.2f} 倍'
            elif strategy == '涨停洗盘' and index:
                evidence = f'；今日最低 {row.low:.2f}；成交量/昨日 {row.volume/full.iloc[index-1].volume:.2f} 倍'
            elif strategy == '高窄旗形' and index >= 20:
                evidence = f'；成交量/前20日均量 {row.volume/full.volume.iloc[index-20:index].mean():.2f} 倍'
            descriptions.append(f'<li>{html.escape(title + evidence)}</li>')
    for index, anchor in [(start,'start'),((start+len(full)-1)//2,'middle'),(len(full)-1,'end')]:
        parts.append(f'<text x="{x(index):.2f}" y="525" text-anchor="{anchor}" fill="#587082" font-size="11">{full.iloc[index].date}</text>')
    candles = html.escape(json.dumps(visible[['date', 'open', 'high', 'low', 'close']].to_dict('records'), ensure_ascii=False), quote=True)
    overlay = '<g class="chart-crosshair" visibility="hidden" pointer-events="none"><line class="crosshair-horizontal" x1="64" x2="964" stroke="#173f5f" stroke-dasharray="5 4"/><line class="crosshair-vertical" y1="50" y2="495" stroke="#74889a" stroke-dasharray="3 4"/><text class="crosshair-price" x="960" text-anchor="end" fill="#173f5f" font-size="13" stroke="#f9fbfc" stroke-width="3" paint-order="stroke"></text></g>'
    script = Path(__file__).with_name('chart_interaction.js').read_text(encoding='utf-8')
    return '<div class="interactive-chart"><div class="chart-legend">' + '　'.join(legend) + '</div><div class="chart-inspect" style="min-height:56px;padding:10px 12px;margin-top:12px;background:#e9f0f6;color:#173f5f;font:13px/1.8 Consolas,Microsoft YaHei,sans-serif">鼠标移入K线查看日期及开高低收；手机按住划动查看。价格为后复权口径。</div><div class="chart-scroll"><svg data-candles="' + candles + f'" data-minimum="{bottom}" data-maximum="{top}" viewBox="0 0 1000 540" role="img" aria-label="日K线、均线与策略信号">' + ''.join(parts) + overlay + '</svg></div><label class="chart-pan"><span>较早</span><input type="range" min="0" max="100" value="100" aria-label="浏览K线历史区间"><span>最新</span></label></div><script>' + script + '</script><p class="chart-note">跟随鼠标的横向虚线表示所指价位；实线：收盘均线；固定虚线：策略价位 / 20日均量；圆点：已保存记录中的命中日（悬停可读数）。成交量单位：股。MA10、MA60为观察参考；除均线放量外，其余策略不以均线为筛选条件。手机图内划动查看价格，下方滑条浏览历史；在图外上下滚动页面。</p><ul class="chart-evidence">' + ''.join(descriptions) + '</ul>'
