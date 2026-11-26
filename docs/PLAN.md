# 阶段计划

> 配套：`docs/TRACKING.md`（跟踪规范）、`docs/PROGRESS.md`（任务台账）、`docs/DEBT.md`（债务）。
> **每阶段可独立验收、可停。** 阶段标 `done` 的前置条件：该阶段所有工作项全 `done` 且
> `PROGRESS.md` 阶段验收记录已追加。

## 总览

| 阶段 | 主题 | 交付 | 状态 |
|---|---|---|---|
| P0 | 规范与骨架 | 三份规范 + 跟踪骨架 + 八份基线 + 七个门禁 | `done` |
| P1 | 数据面 | `client/hub` / `client/autoload` / `client/ec`（全离线单测） | `done` |
| P1U | 前端设计系统（可与 P1 并行） | 令牌实体、10 原子/图表组件（预览页未做） | `in_progress` |
| P2 | 平台与服务壳 | `platform/server.py` 单端口、`platform/store.py` 九表、`client/fetchers.py` 三实现、路由冒烟 + 静态托管 | `done` |
| P3 | 六个轻工具 | Sources · Watchlist · Markets · Economics · Backtesting · Dashboard | `done` |
| P4 | 三个重工具 | Screener（含策略库）· Equity Research（分区懒加载）· Portfolio（账本） | `done` |
| P5 | 设计系统与前端 | 令牌 + 10 原子/图表组件 + 11 工具页与导航（画布/命令面板未做） | `in_progress` |
| P6 | 质量闸 | 冒烟（真实模式 11/11；演示侧随 demo 移除撤下）、文档链接门禁；视觉回归暂缓（CI 无浏览器 + D-21） | `in_progress` |

**为什么把数据面提到前端之前**：门禁的价值在纯逻辑层立刻可验证——退避序列、
单飞、终值保留都能写成精确断言；而前端组件在没有真实数据面时只能渲染假数据，
测出来的「好看」不可信。先让数据层可以被精确测试，前端才有可信的输入。

---

## P0 · 规范与骨架（`done`）

**目标**：先立约束，再写代码。避免「先写后补规范」导致的规范与实现两张皮。

**交付**
- `docs/PROJECT_SPEC.md`、`docs/TRACKING.md`、`docs/DESIGN_SYSTEM.md`
- `docs/{PLAN,PROGRESS,DEBT,EC_BUDGET,ENVELOPE}.md`、`docs/ADR/{000-template,001-*}`
- `quality/baselines/*.json`（七份）
- `gates/check_{layers,sizes,tokens,envelope,plan}.py` + `tools/gen_component_index.py`
- `backend/workbench/core/envelope.py`（契约类型）
- `tests/test_gates_selftest.py`（证明门禁能正确判红，且该绿时也绿）

**验收标准**
- `make check` 一条命令跑完七个门禁，耗时 <30s，exit 0，零网络。
- `pytest -q tests/` 全绿。
- 每个门禁在注入违规样例时返回非零（`test_gates_selftest.py` 逐个证明）。

**退出条件**：全部门禁可跑、可红、可定位到具体文件行。

**P0 收口（2026-11-25 架构重构）**：审计发现第一版门禁有 15 处「声称校验但未实现」，
已全部修复并逐条配注入测试（`tests/test_gates_selftest.py` 从 16 增至 30 个用例）：

- `Makefile` 改真 make（原为 Python 脚本，`make check` 直接报错）
- `check_layers` 修层序反转（原本每条白名单边都被误判为反向）+ 相对 import + 深度 1 模块 + 横向别名
- `check_envelope` 改扫应用层 handler（原扫门禁目录，真实 handler 不受检）
- `check_tokens` 双主题逐块校验（原只全文找一次）
- `check_plan` 补重复 ID、阶段 done 一致性、`tests.json` 死基线
- 新增 `check_contract`（契约漂移 + 版本三元同步）、`check_wheel`（wheel 含 static）
- 布局改为 `backend/` + `frontend/`，详见 `docs/ADR/002`

---

## P1 · 数据面（`done`）

**目标**：补 `CachedFetcher` 的四处缺口（per-topic 策略 / 退避 / 单飞 / 终值保留），
并移植对标物的**成本感知加载**与**新鲜度判决**。这是整个工作台的地基：
所有工具页都从 `hub.get_or_fetch()` 取数，不允许旁路。

### P1.1 `backend/workbench/client/hub/policy.py` — 主题策略

| 项 | 内容 |
|---|---|
| 交付 | `TopicPolicy(ttl_s, min_interval_s, refresh_timeout_s, stale_after_s, push_only, drop_on_idle)`；`DEFAULT_POLICIES` 按主题族给默认值 |
| 阈值来源 | `../airflow/data_monitor/stats_config.py` 的 119 条 `StatsCheck`（`staleness_days`/`warn_days`）AST 解析；**不硬编码新数字** |
| 降级 | 兄弟仓缺失 → 显式 SKIP + 内置兜底表，服务仍可启动，UI 标「新鲜度检查不可用」 |
| 验收 | `policy_for("market:quote:600519")` 返回 `ttl_s ≤ 60`；`policy_for("board:concept_list")` 返回 `ttl_s ≥ 604800`（周更）；解析失败时返回兜底策略且 `source=="fallback"` |

### P1.2 `backend/workbench/client/hub/backoff.py` — 错误分级与退避

| 项 | 内容 |
|---|---|
| 交付 | `classify(exc) -> RetryDecision{retryable, delay_s, terminal, action}` |
| 序列 | `2 / 5 / 15 / 60 / 300` 秒，±10% 抖动 |
| **关键** | `QuotaError` **终态**（`retryable=False`，`action="topup"`）；且因它是 `LimitError` 子类，**必须优先判** |
| 分级 | `rate_limited`→按 `retry_after`；`ip_rate_limited`/`pool_unavailable`→长退避（≥60s）；`TransportError`/`ServerError`→可重试；`UsageError`/`AuthError`/`DataError`/`CatalogError`→不重试 |
| 验收 | 连续 5 次失败产生 `[2,5,15,60,300]`（±10% 容差）；第 6 次保持 300s；`QuotaError` 首次即 `terminal`；`LimitError(code="limit")` 不重试 |

### P1.3 `backend/workbench/client/hub/hub.py` — 单飞 + 终值 + 淘汰

| 项 | 内容 |
|---|---|
| 交付 | `get_or_fetch(topic, producer, *, force=False)`；`subscribe/unsubscribe(owner)`；`peek`/`peek_raw`；`tick(now)` |
| 单飞 | 同 key 并发请求合并为**一次**取数（`threading.Event` + 结果广播） |
| 终值 | 异常时保留 `last_known_good`，返回 `Entry{value, as_of, fetched_at, error, freshness}` |
| 淘汰 | `drop_on_idle`：无订阅者 + 超期即清（防无界主题撑爆内存） |
| 注入 | `now` 与 `sleep` 可注入，**测试零真实等待** |
| 验收 | 10 并发同 key → 上游被调用 **1** 次；异常后 `peek_raw()` 仍返回旧值且 `freshness=="stale"`；`drop_on_idle` 在最后订阅者离开 + 超期后清态；`ttl` 内第二次调用不触发上游 |

### P1.4 `backend/workbench/client/hub/freshness.py` — 三档判决

| 项 | 内容 |
|---|---|
| 交付 | `judge(as_of, policy, now) -> (freshness, warning)` |
| 三档 | 期龄 ≤ `warn` → `fresh`；> `warn` 且 ≤ `staleness` → `stale`；> `staleness` → `expired`；无真值 → `unknown` |
| 文案 | `"资产负债表 数据期龄 128 天，超过预警阈值 90 天"`（可读中文，含具体数字） |
| 验收 | `staleness_days=120, warn_days=90` 且期龄 128 → `expired` 且 `warnings` 非空；期龄 95 → `stale`；期龄 10 → `fresh`；无配置 → `unknown` 且不抛异常 |

### P1.5 `client/autoload/` — 成本感知加载（对标物最高价值移植）

| 项 | 内容 |
|---|---|
| 交付 | `signature.py`（SHA-1 前 16 hex，canonical compact JSON + 排序键）、`policy.py`（`AutoRun`/`Manual`/`NeedsSetup` 三档 + `kAlwaysRefresh=0`/`kNeverRefresh=-1`/默认 24h）、`queue.py`（优先级 + FIFO；LRU 淘汰**保 pinned 与 Manual 结果**） |
| 三不变量 | ① 每次访问最多一次自动尝试；② 输入变了**不静默重跑**（显示「结果来自旧条件」）；③ 用户付过费的（Manual）结果**永不丢弃** |
| 验收 | `signature({a:1,b:2}) == signature({b:2,a:1})`；`max_age=0` 恒重跑、`-1` 永不重跑、`86400` 边界正确；同输入二次访问只跑一次；输入变更后 `state=="inputs_changed"` 且不触发取数；LRU 淘汰时 pinned 与 Manual 条目仍在 |

### P1.6 `client/ec/` — 预算闸与归因

| 项 | 内容 |
|---|---|
| 交付 | `guard.py`（`cost_estimate` 前置 + 总预算闸 `WMSHARE_WORKBENCH_MAX_EC=200_000`）、`ledger.py`（按请求归因） |
| **硬规则** | 预算闸触发时**零请求**；取消时**零请求**；无成本模型时 `ec` 写 `null` 不写 `0` |
| 归因 | 用 `meta.metering["analysis.ec_cost"]`，**不用共享 client 的 `last_ec_cost`**（无锁会串账） |
| 验收 | `ec_pred_hi > 200_000` 时 `guard` 返回 `action="fix_input"` 且上游调用计数 **0**；`cost_estimate` 返回 `None` 时信封 `ec.pred_lo is None`；归因取每请求自带值，两并发请求互不串 |

### P1 退出条件

- 六个子模块全绿，`tests/` 新增用例 ≥ 30 个，**全部离线零网络**。
- `baselines/tests.json` 的 `hub`/`autoload`/`ec` 下限上调到实际值。
- 无任何真实 `wmshare.Client` 被构造（`check_plan` + 测试审查双重确认）。

---

## P2 · 平台与服务壳（`done`）

**目标**：把数据面接到 HTTP，但**不实现业务工具**——用两个假工具验证路由与信封管道。

| 项 | 内容 | 验收 |
|---|---|---|
| P2.1 `platform/store.py` | SQLite 九表（4 照搬 + 5 新增），`check_same_thread=False` + 锁，`0600` | 并发 20 写无 `database is locked`；表结构与 `docs/` 一致 |
| P2.2 `platform/credentials.py` | 优先级 本库 > env > `~/.wmshare/credentials.env` | 三级优先级各有用例；库权限 `0600` |
| P2.3 `client/fetchers.py` | `Fetcher` 协议 + `WmshareFetcher` + `FakeFetcher` | `FakeFetcher` 覆盖全部工具所需；无凭证时不构造真实 client |
| P2.4 `server.py` | `ThreadingHTTPServer` @ `127.0.0.1`，`TOOLS`+`HANDLERS`，统一信封 | 未知 slug → 404 且错误可读；绑定地址断言 `127.0.0.1` |
| P2.5 路由冒烟 | `/api/{appinfo,tools,health,env}` | 四个端点 200；`/api/health` 含 hub/db/wmshare 三态 |
| P2.6 ~~演示模式~~（2026-11-27 移除，原验收为 `--demo` 可跑） | 未接入态：`missing` 给原因与接入指引 | appinfo 返回 `auth_mode:"missing"` + `reason`；取数以可分类异常失败 |

**退出条件**：`python run.py` 起得来，四个端点可用；未装 wmshare 时全部工具给接入指引（不返回任何内置假数据——demo 模式已移除）。

---

## P3 · 六个轻工具（`done`）

**顺序**：Sources → Watchlist → Markets → Economics → Backtesting → Dashboard
（先做能验证基础设施的，再做依赖最多的驾驶舱）

**每个工具的固定交付**：`handler.py` + 五态 + 成本前置 + 离线测试（形状夹具） + 路由冒烟。

| 工具 | 主要门面 | 关键验收 |
|---|---|---|
| Sources | 无（读本地） | 显示 119 条数据集新鲜度分布；Key 热切探针验证后清缓存 |
| Watchlist | `kline.batch_live` | **批量请求数 == 1**（断言） |
| Markets | `kline.snapshot(list)` | 数值列排序键独立于显示文本 |
| Economics | `macro`/`us_macro`/`fx` | 收益率曲线可渲染；指标选择器来自离线目录 |
| Backtesting | `backtest.run` | 权益曲线 + 成交明细 + 8 数字摘要；标 `Manual` |
| Dashboard | `index.valuation`/`moneyflow.board`/`screener.index_breadth_summary` | **不发任何 `Manual` 级调用**（断言） |

---

## P4 · 三个重工具（`done`）

| 工具 | 关键验收 |
|---|---|
| Screener | 表达式拦住 `and`/`or`/`not`；重列 `ec_pred_hi > 40000` 二次确认且取消零请求；策略可存可重跑 |
| Equity Research | 分区懒加载（打开只拉 Overview）；六分区（概览/估值/三表/分红/预告/拆解）全实测；`income.decomp_one` 默认不可见 + 二次确认 + **按年限给成本区间**（默认 5 年而非最贵的 10 年） |
| Portfolio | 五种批次法结果互不相同；价格 PnL + 汇率 PnL == 总 PnL；缺汇率不被 1.0 顶替；合计标 `valued/total` |

---

## P5 · 设计系统与前端（`in_progress`）

| 项 | 内容 |
|---|---|
| P5.1 | `tokens.css` 双主题全量令牌 + 色盲变体 + `prefers-reduced-motion` |
| P5.2 | 15 个 UI 原子 + 5 个表格组件 + 12 类图表（每个五态、双主题、无硬编码色值） |
| P5.3 | 组件预览页（双主题 + 五态可切换） |
| P5.4 | 12 列网格画布 + 模板 + 拖拽 + 布局保存/加载 |
| P5.5 | 命令面板 + 键盘映射 + 符号联动 |

**验收**：`npm run typecheck && npm run build` 通过；`check_tokens` 零告警；对比度双主题各 ≥4.5:1；KpiStrip 7 瓦片容 5 列 → `4+3`。

---

## P6 · 质量闸（`in_progress`）

**交付**：视觉回归基线（9 工具 × 2 主题）、性能预算、真实模式冒烟、文档收口。

**验收**
- 截图基线下沉 `quality/screenshots/`。
- 未接入态全部工具给接入指引，页顶明示原因；运行时不返回任何内置假数据。
- `make check` + `npm run typecheck` + `pytest` 全绿。
- README ≤330 行；所有文档链接可解析。

**退出条件**：可持续交付状态。

---

## 依赖关系

```
P0 ✅
 └─ P1 数据面（hub/autoload/ec/freshness）
     └─ P2 服务壳（server/store/fetchers）
         ├─ P3 六个轻工具
         └─ P4 三个重工具
             └─ P5 前端（需要真实数据面才可信）
                 └─ P6 质量闸
```

**P1 与 P5 可并行**：P5 的令牌与原子组件不依赖数据面。
但如果只有一份精力，**P1 优先**——理由见阶段总览的说明。
