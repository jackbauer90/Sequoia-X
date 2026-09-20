# Sequoia-X: 王者回归 | The King Returns

> A 股量化选股系统 V2 | A-Share Quantitative Stock Selection System V2

---

## 简介 | Introduction

Sequoia-X V2 是面向 A 股市场的量化选股系统，基于现代 Python 工程化标准从零重构。
系统以 OOP 架构、向量化计算和增量数据更新为核心设计原则，每日收盘后自动选股并通过 OneBot 11 推送至 QQ。

数据层使用 [baostock](http://baostock.com)（免费、无需注册、无限流）拉取历史及增量日 K 数据（后复权），
存储于本地 SQLite，彻底规避东方财富反爬问题。

---

## 两种运行模式

```bash
python main.py               # 日常模式：8进程增量补数据 + 跑策略 + QQ 推送（2~3分钟）
python main.py --backfill     # 回填模式：全市场历史K线一次性灌入（约12分钟）
```

---

## 内置策略 | Strategies

| 策略 | 说明 |
|---|---|
| **MaVolume** | 均线+放量突破 |
| **HighTightFlag** | 高而窄的旗形整理突破 |
| **RpsBreakout** | 欧奈尔 RPS 相对强度突破 |

---

## 快速开始 | Quick Start

### 环境要求

- Python >= 3.10

### 1. 安装依赖

```bash
# 推荐使用 uv（快速包管理器）
uv sync

# 或者 pip
pip install .
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填写 OneBot API 地址及 QQ 群号或接收人的 QQ 号
```

QQ 推送依赖一个已登录并启用 HTTP API 的 OneBot 11 兼容机器人。群聊配置示例：

```dotenv
QQ_BOT_API_URL=http://127.0.0.1:3000
QQ_TARGET_TYPE=group
QQ_TARGET_ID=123456789
QQ_BOT_ACCESS_TOKEN=
```

如需私聊，将 `QQ_TARGET_TYPE` 改为 `private`，并把 `QQ_TARGET_ID` 改为接收人的 QQ 号。
若 OneBot 端启用了 access token，请同步填写 `QQ_BOT_ACCESS_TOKEN`。

### 3. 首次回填历史数据

```bash
python main.py --backfill
```

约 12 分钟完成 ~5200 只 A 股历史后复权日 K 数据回填。

### 4. 日常运行

```bash
python main.py
```

### 5. 本地只读网页

生成只读取本地行情、不会发送通知的仪表盘，然后启动本地服务：

```bash
python dashboard.py
python -m http.server 8765 --bind 127.0.0.1 --directory site
```

浏览器访问 `http://127.0.0.1:8765/`。海龟与公告策略依赖在线数据，不在本地页面运行。

建议配合 crontab 每个交易日收盘后自动执行：

```cron
15 19 * * 1-5 cd /root/Sequoia-X && .venv/bin/python main.py >> log.txt 2>&1
```

---

## 目录结构 | Project Structure

```
Sequoia-X/
├── main.py                      # 入口：argparse 分发日常/回填模式
├── pyproject.toml               # 依赖声明 + ruff/pytest 配置
├── .env.example                 # 环境变量模板
├── data/                        # SQLite 数据库（运行时生成，不入 git）
├── sequoia_x/
│   ├── core/
│   │   ├── config.py            # Pydantic-settings 配置管理
│   │   └── logger.py            # rich 结构化日志
│   ├── data/
│   │   └── engine.py            # 数据引擎（baostock 回填 + 增量同步 + SQLite）
│   ├── strategy/
│   │   ├── base.py              # 策略抽象基类
│   │   ├── turtle_trade.py      # 海龟交易策略
│   │   ├── ma_volume.py         # 均线放量策略
│   │   ├── high_tight_flag.py   # 高窄旗形策略
│   │   ├── limit_up_shakeout.py # 涨停洗盘策略
│   │   └── rps_breakout.py      # RPS 突破策略
│   └── notify/
│       └── qq.py                # QQ OneBot 11 推送
└── tests/                       # 属性测试（hypothesis）
```

---

## 数据说明

- **数据源**：[baostock](http://baostock.com)（免费、无需注册、无限流）
- **复权方式**：后复权（hfq）— 历史价格不变，适合增量存储，避免除权导致数据错乱
- **存储**：本地 SQLite（`data/sequoia_v2.db`），可直接拷贝到其他机器使用
- **日常增量**：8 进程并行通过 baostock 拉取，2~3 分钟完成全市场更新

---

## 本地扫描台

运行 `.venv\Scripts\python.exe dashboard.py` 生成 `site/index.html`，通过本地 HTTP 服务查看。
股票名称与上市板块来自 Tushare `stock_basic`，缓存到 `data/stock_catalog.json`。
K 线读取与策略一致的本地后复权日线，详情显示实际来源和价格口径；不混用不复权 K 线。
`TUSHARE_TOKEN` 从进程环境读取，不保存到网页或源码。扫描台不调用通知模块。

扫描台保留均线放量、高窄旗形、RPS 突破三个策略，统一剔除 ST/*ST、科创板和北交所，只输出主板与创业板股票。原有五策略历史记录保留，但不参与新命中及连续命中计算。
已移除定增公告及趋势跌停策略的运行入口。
详情页在名称旁显示代码，并优先显示 Tushare `stock_company.main_business` 的首句摘要；
该接口缺失时使用巨潮资讯公司概况的“主营业务”，页面注明实际来源。
资料保存在 `data/company_business.json`，缺失时明确提示，不自动编造。

`data/selection_history.json` 按行情交易日保存完整命中（包含已隐藏股票）。
股票在任意一个保留策略命中即计为当日命中，跨策略合并计数；连续第 1～3 个交易日展示，
第 4 天起隐藏。重复扫描同一交易日覆盖当日记录，不增加天数；非交易日不计数。
缺失扫描记录或未命中则中断连续计数，再次命中从 1 开始。
首次启用前没有历史扫描记录，所以“已记录连续命中”不能视作历史真实首次触发日。
策略整体执行失败时保留上一版网页和历史，避免将失败误记为未命中。

Windows 自动收尾必须使用 **PowerShell 7（pwsh）**：

```powershell
pwsh -NoProfile -File .\refresh_after_backfill.ps1 -BackfillProcessId <实际回填进程ID>
```

脚本等待指定进程结束后重新生成网页，失败最多重试三次。`site/status.json` 显示收尾状态，
`output/dashboard-final.log` 保存生成日志。首页每 60 秒刷新；仅在详情页全部写入后发布新首页。
回填进程退出不代表所有股票成功，实际覆盖以页面统计和回填日志为准。

## 许可证 | License

MIT
# 腾讯云投资工具箱部署

三策略扫描台使用独立目录 `/opt/sequoia-x`，网页从其中 `site/` 提供。工具箱路由 `/sequoia-five/` 为兼容现有入口继续保留，沿用现有门卫校验，不新增公开端口，不修改二次探底定时器。

服务器已配置 `sequoia-dashboard.timer`：周一至周五北京时间15:05使用腾讯实时行情生成收盘首版，腾讯失败时切换东方财富；18:30使用Tushare正式日线补全并覆盖校准。程序查询交易日历，非交易日只检查最近已收盘交易日。任一来源的交易日、复权因子或覆盖率不足前次98%时保留上一版。任务在服务器执行，无需本地电脑开机，不发送QQ推送。

`daily_update.py` 在15:05将腾讯/东财实时 OHLC、成交量和成交额与Tushare盘前发布的当日 `adj_factor` 组合，18:30再使用Tushare `daily`、`adj_factor` 和 `daily_basic` 覆盖同一交易日。以切换时数据库最新交易日的重叠收盘价建立固定复权锚点，后续价格为原始 OHLC × Tushare 因子 × 固定比例；保留 BaoStock 历史，不代表已统一重算全历史。无重叠锚点的旧股票暂不接续，最新日无行情的不进入当日命中。实时首版暂沿用前一交易日流通市值排序，18:30更新为当日Tushare流通市值。网页与状态文件标明实际数据源和首版/正式补全阶段。

当日实时接口为空、日期陈旧、覆盖不足前次98%或复权因子不完整时不发布。18:30补数据会重新拉取当天正式日线并允许修订。逐交易日补扫描快照，再在临时副本完成页面生成后发布；失败保留旧版。上一版数据库保存在 `data/sequoia_v2.previous.db`，98%是发布门槛，不代表全市场完整覆盖。

“今日新增”按股票代码跨当前三策略合并，与前一交易日当前三策略的原始命中比较；仅换策略不算新增，缺少前一交易日快照时不误标。今日指页面行情交易日，不是浏览器打开日期。重复扫描同日不改变比较基准。

手动完整更新：`sudo systemctl start sequoia-dashboard.service`。查看状态：`systemctl status sequoia-dashboard.timer sequoia-dashboard.service`。只重建已有快照：在部署目录执行 `.venv/bin/python dashboard.py --offline`，不会取数或推送。不得为了更新网页直接执行带通知的 `main.py`。

详情页显示 MA5/10/20/60 和已保存命中日的策略门槛。价格统一使用与选股相同的后复权口径，不是当前实际成交价格；MA10/60仅供参考。均线在完整历史上计算后截取最近120日，不回推未保存的历史信号。
