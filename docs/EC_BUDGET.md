# EC 预算登记

> 每个 `ec_impact=manual` 的工作项必须在此有对应条目（`gates/check_plan.py` 强制）。
> **成本数字来自 `wmshare.client` 的实测常量，不在此处另行估算。**
> 实际消耗以服务端回传的 `meta.metering["analysis.ec_cost"]` 为准。

## 1. 成本模型常量（来源：`wmshare/src/wmshare/client.py`）

| 常量 | 值 | 含义 |
|---|---|---|
| `EC_PER_ROW` | `(60, 75)` | 行数驱动类接口每行 EC |
| `KLINE_SERVER_CAP` | 1000 | `kline` 单次上限；实测 ≈67 EC/行 |
| `MONEYFLOW_SERVER_CAP` | 500 | 曾因 10000 行单笔 5.15M EC 事故而收紧 |
| `BONUS_SERVER_CAP` | 500 | 分红历史单次上限 |
| `CBOND_KLINE_CAP` / `CBOND_QUERY_CAP` | 1000 / 500 | 可转债 |
| `EC_SCREENER_BASE` | `(70, 1000)` | 轻列选股 |
| `EC_SCREENER_HEAVY` | `(40_000, 60_000)` | 重列（TTM 同比族） |
| 冷物化 | 可达 `600_000` | 重列首次全市场物化 |
| `NATIVE_FULL_MARKET_MIN` | 2000 | 达到此票数走全市场捷径 |

## 2. 实测参考（来自既有仓库记录，非本项目测量）

| 接口 | 量级 | 备注 |
|---|---|---|
| `kline.query_bars` | ≈67 EC/行 | 线性 |
| `kline.snapshot`（逐票） | ≈10,250 EC/票 | 首算 |
| `kline.snapshot_batch` | ≈58 EC/票 | 原生批量 |
| `moneyflow` 全历史单笔 | 5.15M EC | 事故案例，已加服务端上限 |
| `margin.universe` | ≈112 EC/行 | 全量 ≈450k |
| `valuation.daily_basic_multi` | ≈1,707 EC/标的 | 下限 |
| `dividend.decomp` | **501,577 EC** | 2 标的 × 3 年实测 |
| `dividend.rating` | memo 命中 ≈0 | 冷缓存返回 `ok=false`，不重算 |
| `screener.query`（轻列） | 70–1,000 EC | 与命中数无关 |
| `screener.query`（重列） | 40k–60k EC | 冷物化可达 600k |
| 逐票 eval 全市场 | ≈456k EC | 最贵路径，禁止 |

## 3. 本项目的成本纪律

### 3.1 三类归类（对应 `AutoLoadPolicy` 移植）

| 类别 | 触发 | 例子 |
|---|---|---|
| **AutoRun**（免费/本地/缓存） | 打开即跑，24h 内不重跑 | `info.profile`、`dividend.yield_ttm`、缓存命中的 `index.trend` |
| **Manual**（付费/重） | 显式点击 + 二次确认（显示 EC 区间） | 重列 `screener.query`、`income.decomp_one`、`margin.universe` 全量、`valuation.daily_basic` 长区间 |
| **NeedsSetup** | 先提示配置 | 无凭证、缺必填参数 |

### 3.2 总预算闸

单次聚合请求超过 `WMSHARE_WORKBENCH_MAX_EC`（默认 `200_000`，与 MCP 层同量级）
**直接拒绝且不发出任何请求**，返回 `action="fix_input"` 并建议拆分。

### 3.3 归因

用请求自带的 `meta.metering["analysis.ec_cost"]` 归因，
**不用共享 client 的 `last_ec_cost`**——该字段无锁，并发下会串账。

## 4. `Manual` 级操作登记（与 `PROGRESS.md` 的 `ec_impact=manual` 一一对应）

| 工作项 | 操作 | 预估区间 | 二次确认文案要点 |
|---|---|---|---|
| P1-12 | 预算闸拦截（单次聚合超上限） | 由 `cost_estimate` 决定 | 「本次预估 X–Y EC，超过单次上限 200,000，请拆分面板或缩小范围」 |
| P1-13 | 取消付费操作 | — | 「取消不收费用」必须显式写在确认弹窗里；取消后零请求 |
| P3-05 | 回测 | `backtest.run` 全历史 ≈400k EC | 「回测将读取 N 根 K 线，预估 X–Y EC」 |
| P4-02 | 重列选股 | 40k–60k，冷物化可达 600k | 「该条件含重列指标，首次物化可能消耗数十万 EC；建议先用轻列跑通」 |
| P4-05 | 深度归因 `income.decomp_one` | 实测 5 点跨度 15,814–721,953 EC；**年限与「该标的是否已物化」两个变量未分离**（原始数据见 `DEBT.md` D-32） | 「收益拆解按标的与年限计费（本次预估 X–Y EC，模型 measured）。**模型上界（20 万）低于实测尖刺（72 万）**，按上限预留余量」 |
| P4-11 | 拆解的价格/股息拆分 | 与 P4-05 同一次调用，不额外计费 | 恒等式 `价格 + 股息 == 总收益` 由后端保证；前端只渲染，不重算 |
| P4-13 | 切换拆解年限（3/5/10） | 改年限即换请求，成本可能差一个数量级；但**具体倍数未测准**（见 D-32） | 切换年限**重新走确认**，成本区间按新年限重算；默认 5 年而非最贵的 10 年 |

## 5. 取消语义（硬规则）

**用户在任何二次确认弹窗点「取消」，必须零网络请求发生。**
这条由测试强制：`test_ec_guard.py::test_cancel_makes_no_request` 断言请求计数为 0。

理由：财经工具里「点了确认才发现很贵」和「点了取消还在花钱」都会直接摧毁信任，
后者更严重。
