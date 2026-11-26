# 任务台账

> 规范见 `docs/TRACKING.md`。字段：`id` · `type` · `scope` · `status` · `acceptance` · `evidence` · `ec_impact` · `updated`
> **台账不许手改统计数字**——统计行由 `gates/check_plan.py` 校验，与表格行数不一致即失败。

## P0 · 规范与骨架

| id | type | scope | status | acceptance | evidence | ec_impact | updated |
|---|---|---|---|---|---|---|---|
| P0-01 | docs | docs | done | 三份规范文件存在且各含「可机械验证」条款标注 | `docs/PROJECT_SPEC.md` · `docs/TRACKING.md` · `docs/DESIGN_SYSTEM.md` | none | 2026-11-25 |
| P0-02 | docs | docs | done | 跟踪骨架 6 文件存在，`DEBT.md` 含 D-01..D-04 且每条有 trigger/owner | `docs/DEBT.md` | none | 2026-11-25 |
| P0-03 | feat | quality | done | 七份基线文件均合法 JSON 且被对应门禁实际读取 | `quality/baselines/` | none | 2026-11-25 |
| P0-04 | feat | quality | done | `check_layers` 在新增跨层 import 时返回非零 | `tests/test_gates_selftest.py::test_layers_detects_violation` | none | 2026-11-25 |
| P0-05 | feat | quality | done | `check_sizes` 在文件超行数预算时返回非零 | `tests/test_gates_selftest.py::test_sizes_detects_violation` | none | 2026-11-25 |
| P0-06 | feat | quality | done | `check_tokens` 在组件内出现裸 hex 时返回非零 | `tests/test_gates_selftest.py::test_tokens_detects_violation` | none | 2026-11-25 |
| P0-07 | feat | quality | done | `check_envelope` 在 `ok=False` 但 `data` 非空时返回非零 | `tests/test_gates_selftest.py::test_envelope_detects_violation` | none | 2026-11-25 |
| P0-08 | feat | quality | done | `check_plan` 在 `done` 缺 evidence / TODO 缺 id 时返回非零 | `tests/test_gates_selftest.py::test_plan_detects_violation` | none | 2026-11-25 |
| P0-09 | feat | quality | done | `gen_component_index --check` 能检出孤儿组件 | `tests/test_gates_selftest.py::test_components_detects_orphan` | none | 2026-11-25 |
| P0-10 | feat | core | done | `core/envelope.py` 字段集与 `baselines/envelope.json` 完全一致 | `tests/test_gates_selftest.py::test_envelope_contract_matches_baseline` | none | 2026-11-25 |
| P0-11 | feat | platform | done | `make check` 跑完七个门禁 exit 0，且 `pytest -q tests/` 全绿 | `Makefile` · `tests/test_gates_selftest.py::test_all_gates_pass_on_clean_repo` | none | 2026-11-25 |
| P0-12 | refactor | arch | done | `Makefile` 能被 make 解析且 `make check` 跑通（旧版零 target） | `tests/test_gates_selftest.py::test_makefile_is_real_make` | none | 2026-11-25 |
| P0-13 | refactor | arch | done | 布局迁移 `tools/→gates/`、`src/workbench/→backend/workbench/`、`web/→frontend/` | `docs/ADR/002-backend-frontend-colocated.md` | none | 2026-11-25 |
| P0-14 | fix | arch | done | 白名单边（client→core）必须绿，core→client 必须红（旧版层序反转全误判） | `tests/test_gates_selftest.py::test_layers_allows_whitelisted_downward_edge` | none | 2026-11-25 |
| P0-15 | fix | arch | done | 相对 import `from ..client import x` 必须红（旧版全跳过） | `tests/test_gates_selftest.py::test_layers_detects_relative_import` | none | 2026-11-25 |
| P0-16 | fix | arch | done | 深度 1 的 `server.py` 参与分层校验 | `tests/test_gates_selftest.py::test_layers_detects_depth1_entry_module` | none | 2026-11-25 |
| P0-17 | fix | arch | done | 工具横向 import 必须红（旧版别名映射后仍按字面量匹配） | `tests/test_gates_selftest.py::test_layers_detects_tool_cross_import` | none | 2026-11-25 |
| P0-18 | fix | arch | done | `check_envelope` 扫应用层 handler 而非门禁目录 | `tests/test_gates_selftest.py::test_envelope_detects_unknown_field` | none | 2026-11-25 |
| P0-19 | fix | arch | done | 基线隐性松弛告警（高出 >10% 即 warn） | `tests/test_gates_selftest.py::test_sizes_detects_slack_in_baseline` | none | 2026-11-25 |
| P0-20 | fix | arch | done | `tool_handler` 上限被读取（旧版配置项零消费者） | `tests/test_gates_selftest.py::test_sizes_detects_tool_handler_cap` | none | 2026-11-25 |
| P0-21 | fix | arch | done | 双主题逐块校验：只写 `:root` 必须红 | `tests/test_gates_selftest.py::test_tokens_requires_both_themes` | none | 2026-11-25 |
| P0-22 | fix | arch | done | 台账重复 ID 必须红（P1-01 曾出现两次） | `tests/test_gates_selftest.py::test_plan_detects_duplicate_id` | none | 2026-11-25 |
| P0-23 | fix | arch | done | 阶段标 done 但仍有未完成项必须红（TRACKING §5 规则 2 旧版未实现） | `tests/test_gates_selftest.py::test_plan_detects_stage_done_with_pending` | none | 2026-11-25 |
| P0-24 | fix | arch | done | `tests.json` 死基线补上消费者 | `gates/check_plan.py::check_test_baseline` | none | 2026-11-25 |
| P0-25 | feat | arch | done | 契约生成 + 漂移门禁：手改 `contract.ts` 必须红 | `tests/test_gates_selftest.py::test_contract_detects_drift` | none | 2026-11-25 |
| P0-26 | feat | arch | done | 版本三元同步门禁：三处版本不一致必须红 | `tests/test_gates_selftest.py::test_contract_detects_version_drift` | none | 2026-11-25 |
| P0-27 | feat | arch | done | `run.py` 存在且 `--version` 可用（旧版被引用但文件缺失） | `tests/test_gates_selftest.py::test_run_py_exists_and_importable` | none | 2026-11-25 |
| P0-28 | feat | arch | done | `check_wheel` 断言 wheel 内含 `static/index.html` 且无 `node_modules` | `gates/check_wheel.py` | none | 2026-11-25 |
| P0-29 | docs | arch | done | `docs/ARCHITECTURE.md` + `ADR/002` 落盘，规范假承诺逐条修正 | `docs/ARCHITECTURE.md` · `docs/ADR/002-backend-frontend-colocated.md` | none | 2026-11-25 |

## P1U · 前端设计系统（P1 期间可并行）

> 该段原误编为 P1（与「数据面」段 ID 冲突），后改 P5（又与「画布与图表」冲突）。
> 最终用 `P1U` 前缀：它属于 P1 阶段但可并行推进，不占用 P5 编号。

| id | type | scope | status | acceptance | evidence | ec_impact | updated |
|---|---|---|---|---|---|---|---|
| P1U-01 | feat | ui | proposed | `frontend/src/styles/tokens.css` 含双主题全量令牌，`check_tokens` 零告警 | — | none | 2026-11-25 |
| P1U-02 | feat | ui | proposed | 15 个原子组件双主题渲染，各自五态可切换 | — | none | 2026-11-25 |
| P1U-03 | feat | ui | proposed | 5 个表格组件：`1.2万` 排序键为 `12000` | — | none | 2026-11-25 |
| P1U-04 | feat | ui | proposed | 组件预览页双主题 + 色盲变体可切换 | — | none | 2026-11-25 |

## P1 · 数据面

| id | type | scope | status | acceptance | evidence | ec_impact | updated |
|---|---|---|---|---|---|---|---|
| P1-01 | feat | hub | done | `policy_for("market:quote:600519").ttl_s ≤ 60`；`policy_for("board:concept_list").ttl_s ≥ 604800`；兄弟仓缺失时返回兜底策略且 `source=="fallback"` | `tests/test_hub.py::test_quote_policy_is_short` | none | 2026-11-25 |
| P1-02 | feat | hub | done | 连续 5 次失败产生 `[2,5,15,60,300]`（±10% 容差），第 6 次保持 300s | `tests/test_hub.py::test_retry_delay_sequence` | none | 2026-11-25 |
| P1-03 | feat | hub | done | `QuotaError` 首次即 `terminal`（`retryable=False, action="topup"`）；`LimitError(code="limit")` 不重试 | `tests/test_hub.py::test_quota_error_is_terminal_and_checked_before_limit` | none | 2026-11-25 |
| P1-04 | feat | hub | done | 同 key 并发 10 请求，上游被调用 **1** 次 | `tests/test_hub.py::test_single_flight_merges_concurrent_requests` | none | 2026-11-25 |
| P1-05 | feat | hub | done | 异常后 `peek_raw()` 仍返回旧值且 `freshness=="stale"` | `tests/test_hub.py::test_last_known_good_survives_error` | none | 2026-11-25 |
| P1-06 | feat | hub | done | `drop_on_idle` 在最后订阅者离开 + 超期后清态 | `tests/test_hub.py::test_drop_on_idle_clears_after_last_subscriber` | none | 2026-11-25 |
| P1-07 | feat | hub | done | `staleness_days=120, warn_days=90` 期龄 128 → `expired` 且 `warnings` 非空；期龄 95 → `stale`；期龄 10 → `fresh` | `tests/test_hub.py::test_freshness_three_tiers` | none | 2026-11-25 |
| P1-08 | feat | autoload | done | `signature({a:1,b:2}) == signature({b:2,a:1})`（键序不敏感） | `tests/test_autoload_ec.py::test_signature_is_key_order_insensitive` | none | 2026-11-25 |
| P1-09 | feat | autoload | done | `max_age=0` 恒重跑、`-1` 永不重跑、`86400` 边界正确 | `tests/test_autoload_ec.py::test_max_age_boundary` | none | 2026-11-25 |
| P1-10 | feat | autoload | done | 同输入二次访问只跑一次；输入变更后 `state=="inputs_changed"` 且不触发取数 | `tests/test_autoload_ec.py::test_inputs_changed_does_not_rerun` | none | 2026-11-25 |
| P1-11 | feat | autoload | done | LRU 淘汰时 pinned 与 Manual 条目仍在 | `tests/test_hub.py::test_expensive_entry_never_evicted` | none | 2026-11-25 |
| P1-12 | feat | ec | done | `ec_pred_hi > 200_000` 时 guard 返回 `action="fix_input"` 且上游调用计数 **0** | `tests/test_autoload_ec.py::test_guard_makes_zero_requests_when_over_budget` | manual | 2026-11-25 |
| P1-13 | feat | ec | done | 取消时上游调用计数 **0** | `tests/test_autoload_ec.py::test_guard_makes_zero_requests_when_not_confirmed` | manual | 2026-11-25 |
| P1-14 | feat | ec | done | `cost_estimate` 返回 `None` 时信封 `ec.pred_lo is None`（不是 0） | `tests/test_autoload_ec.py::test_estimate_returns_none_when_no_client` | none | 2026-11-25 |
| P1-15 | feat | ec | done | 两并发请求的 EC 归因互不串（各用自带 `meta.metering`） | `tests/test_autoload_ec.py::test_attribute_uses_response_metering` | none | 2026-11-25 |

## P2 · 平台与服务壳

| id | type | scope | status | acceptance | evidence | ec_impact | updated |
|---|---|---|---|---|---|---|---|
| P2-01 | feat | platform | done | 并发 20 写 SQLite 无 `database is locked`；九张表结构与文档一致 | `tests/test_platform.py::test_store_concurrent_writes_no_lock_error` | none | 2026-11-25 |
| P2-02 | feat | platform | done | 凭证三级优先级（本库 > env > 文件）各有用例；库文件权限 `0600` | `tests/test_platform.py::test_credentials_priority_store_beats_env` | none | 2026-11-25 |
| P2-03 | feat | platform | done | 无凭证时 `FakeFetcher` 生效，且不构造真实 `Client`（断言） | `tests/test_platform.py::test_build_fetcher_uses_fake_without_credentials` | none | 2026-11-25 |
| P2-04 | feat | platform | done | 未知 slug → 404 且错误可读；服务绑定地址为 `127.0.0.1`（断言） | `tests/test_platform.py::test_server_rejects_non_loopback_host` | none | 2026-11-25 |
| P2-05 | feat | platform | done | `/api/{appinfo,tools,health}` 均 200；`/api/health` 含 hub/db/wmshare 三态 | `tests/test_platform.py::test_server_health_has_three_states` | none | 2026-11-25 |
| P2-06 | feat | platform | done | `--demo` 无凭证可起；`/api/appinfo` 返回 `demo:true` 且 `as_of` 为快照日 | `tests/test_platform.py::test_server_appinfo_demo_flag` | none | 2026-11-25 |

## P3 · 六个轻工具

| id | type | scope | status | acceptance | evidence | ec_impact | updated |
|---|---|---|---|---|---|---|---|
| P3-01 | feat | tool:sources | done | 显示 119 条数据集新鲜度分布 | `tests/test_tools.py::TestRegistry` + 实跑 sources count=119 | none | 2026-11-25 |
| P3-02 | feat | tool:watchlist | done | 批量行情请求数 == 1 | `tests/test_tools.py::TestWatchlist::test_single_batch_request` | auto | 2026-11-25 |
| P3-03 | feat | tool:markets | done | 表格数值列排序键独立于显示文本 | `WatchlistView.vue` 按原始数值排序 | auto | 2026-11-25 |
| P3-04 | feat | tool:economics | done | 收益率曲线与指标选择器可用 | `tests/test_tools.py::TestEconomics`（6 期限不插值） | auto | 2026-11-25 |
| P3-05 | feat | tool:backtest | done | 权益曲线 + 成交明细 + 8 数字摘要 | `tests/test_tools.py::TestBacktest`（区间必填 + 8 labels） | manual | 2026-11-25 |
| P3-06 | feat | tool:dashboard | done | 不发任何 `Manual` 级调用（断言） | `tests/test_tools.py::TestDashboard::test_no_manual_calls` | auto | 2026-11-25 |

## P4 · 三个重工具

| id | type | scope | status | acceptance | evidence | ec_impact | updated |
|---|---|---|---|---|---|---|---|
| P4-01 | feat | tool:screener | done | 表达式拦住 `and`/`or`/`not` | `tests/test_tools.py::TestScreener::test_rejects_python_boolean_words` | auto | 2026-11-25 |
| P4-02 | feat | tool:screener | done | 重列超预算时二次确认；取消零请求 | `tests/test_tools.py::test_zero_request_when_over_budget` | manual | 2026-11-25 |
| P4-03 | feat | tool:screener | done | 策略可存可重跑，结果可对比 | `tests/test_tools.py::test_save_and_list` | none | 2026-11-25 |
| P4-04 | feat | tool:equity | done | 分区懒加载：打开只拉概览 | `tests/test_tools.py::TestEquity::test_default_section_is_overview` | auto | 2026-11-25 |
| P4-05 | feat | tool:equity | done | `decomp` 默认不可见且二次确认 | `tests/test_tools.py::test_expenses_section_requires_confirm` | manual | 2026-11-25 |
| P4-06 | feat | tool:portfolio | done | 五种批次法结果互不相同 | `tests/test_ledger.py::test_five_methods_differ` | none | 2026-11-25 |
| P4-07 | feat | tool:portfolio | done | 价格 PnL + 汇率 PnL == 总 PnL | `tests/test_ledger.py::test_price_fx_split_sums` | none | 2026-11-25 |
| P4-08 | feat | tool:portfolio | done | 缺汇率不被 1.0 顶替；合计标 `valued/total` | `tests/test_ledger.py::test_missing_fx_never_one` | none | 2026-11-25 |
| P4-09 | feat | tool:equity | done | 预告三块全显示（含空块）；上游 0 归 `None` 不显示「0 元」 | `TestForecastSection::test_zero_becomes_none_not_zero` | none | 2026-11-25 |
| P4-10 | feat | tool:equity | done | 「最新预告」过期要标出（茅台达 694 天） | `TestForecastSection::test_stale_forecast_is_flagged` | none | 2026-11-25 |
| P4-11 | feat | tool:equity | done | 拆解：价格 + 股息 == 总收益（恒等式） | `TestDecompSection::test_sum_identity_holds` | manual | 2026-11-25 |
| P4-12 | feat | tool:equity | done | 拆解 `ok=false` 如实显示原因，不抛成失败 | `TestDecompSection::test_ok_false_is_shown_not_raised` | none | 2026-11-25 |
| P4-13 | feat | tool:equity | done | 确认框按本次年限给成本区间；默认 5 年非 10 年 | `TestDecompSection::test_default_years_is_five_not_ten` | manual | 2026-11-25 |
| P4-14 | fix | tools | done | 形状归一只有一份实现（`_shared.as_records`），并有防复发断言 | `TestShapeNormalization::test_no_tool_reimplements_normalization` | none | 2026-11-25 |
| P4-15 | feat | tool:watchlist | done | 自选可增删且**零取数**，写入后行情表读的是库里的清单 | `TestWatchlistWrite::test_write_makes_zero_upstream_requests` | none | 2026-11-25 |
| P4-16 | feat | tool:portfolio | done | 持仓档案 save/list/**load** 往返（load 是补上的缺口） | `TestPortfolioArchive::test_save_then_load_roundtrip` | none | 2026-11-25 |
| P4-17 | fix | docs | done | 台账准确性：README 用例数、DEBT 列错位、D-32 成本归因、§7 承诺 | `tests/test_gates_selftest.py::test_all_gates_pass_on_clean_repo` | none | 2026-11-25 |
| P4-18 | feat | ui | done | 第 3 类图表 `KLineChart`（蜡烛+量副图+买卖点；双主题/红涨绿跌/null 不补 0，D-16 首次偿还） | `frontend/src/components/ui/KLineChart.vue` | none | 2026-11-25 |
| P4-19 | feat | tool:equity | done | 个股研究新增「行情走势」分区（概览之后、估值之前；days 钳 20–500，as_of 取最新一根） | `TestEquity::test_bars_section` | 213 EC/5 根实测（≈按行计价） | 2026-11-25 |
| P4-20 | feat | tool:backtest | done | 买卖点标在价格 K 线上（另一次 `kline.bars` 区间取数并在 meta 披露；失败降级为仅净值） | `TestBacktest::test_price_bars_added_and_disclosed` | +1 请求/次（区间日 K） | 2026-11-25 |
| P4-21 | fix | ui | done | 图表双主题真实生效：主题做进响应式 `themeState`，三类图表 watch 重渲染（此前切主题残留旧色） | `frontend/src/styles/themeState.ts` | none | 2026-11-25 |
| P4-22 | fix | client | done | 演示 K 线顺序与真实同向（新→旧，D-27 整改）；`normalize_bars` 共享归一只有一份 | `tests/test_demo_data.py::test_bars_descending_like_real` | none | 2026-11-25 |
| P4-23 | feat | tools | done | 块级数据截止时间：自选/持仓/拆解的信封 as_of 改为上游数据事实（此前真实模式恒空）；持仓给定价日区间 | `TestWatchlist::test_rows_carry_kline_date_and_as_of_is_max` | none | 2026-11-25 |
| P4-24 | feat | ui | done | AsOfChip 块级徽标 + 页级收敛规则（块日期==页级不重复渲染）；无日期的块如实「截至未知」 | `frontend/src/components/ui/AsOfChip.vue` | none | 2026-11-25 |
| P4-25 | fix | client | done | 回测信封 as_of 改为数据实际末日（原用请求 end 参数）；驾驶舱 indices_as_of（季频不提升页级）；演示 index.valuation series 修正为日期升序（D-27） | `TestBacktest::test_as_of_is_data_last_date_not_requested_end` | none | 2026-11-25 |
| P4-26 | feat | tool:equity | done | 财报四表全面改走 `statements.*` 公开门面（脱离内部命名空间），`period` 年报/季报全线透传（季报=累计档 Q1..Q4，期次键 YYYY-Qn） | `TestStatementDomainMapping::test_handler_sends_facade_with_period` | none | 2026-11-25 |
| P4-27 | fix | tool:screener | done | **选股真实模式恒空修复**：真实返回是统一信封（`data.count`/`data.rows`-DataFrame），handler 曾读顶层 `rows`；demo 改嵌套同形（D-25/D-27） | `TestScreener::test_nested_envelope_shape_extracts_rows` | none | 2026-11-25 |
| P4-28 | feat | tool:equity | done | 拆解去确认直接加载（用户拍板，成本提示一并移除；确认机制保留给未来分区） | `TestDecompSection::test_loads_directly_without_confirm` | none | 2026-11-25 |
| P4-29 | feat | ui | done | 自选行代码跳转个股研究（`#/equity?sym=` hash 查询参数；readHash 剥查询段） | 浏览器实测（000001 直达平安银行） | none | 2026-11-25 |
| P4-30 | feat | tool:markets | done | 「最新交易日」推断口径（沪深300最新K线日，失败降级；信封 as_of 不冒充数据截止） | `TestMarkets::test_trading_day_from_index_last_bar` | +1 请求/次（n=1） | 2026-11-25 |
| P4-31 | fix | tool:dashboard | done | **估值换周频源**：PE/PB 走 `cli.index.trend`（末行=最新交易日，此前 `indices.valuation` 是季度末采样、页上恒「截至 9-30」）；dv 保留季度口径单独给 `dv_as_of`；cyb 两路皆无数据如实缺失告警 | `TestDashboard::test_pe_pb_from_trend_latest_point` | 每指数 +1 trend 请求（AUTO） | 2026-11-25 |
| P4-32 | feat | tool:dashboard | done | 页级「最新交易日」推断（同行情页口径，失败降级；不冒充信封 as_of）+ 删块级重复 chip（收敛规则） | `TestDashboard::test_trading_day_present_and_degrades` | +1 请求/次（n=1） | 2026-11-25 |
| P4-33 | fix | tool:watchlist | done | **名称/5日/20日/量比真实恒空修复**：列换 `kline.snapshot` 批量（23 字段），live_many 降为日期伴取（快照批量路由不物化 kline_date，合同原文）；名称缺失回落「—」不冒充代码；demo 同形整改（D-27） | `TestWatchlist::test_rows_carry_name_and_window_metrics` | 1→2 请求/次 | 2026-11-25 |
| P4-34 | feat | tool:portfolio | done | 持仓行表补名称列 + 代码行跳转个股研究：name 从定价批量快照免费透出（23 字段自带，零额外请求）；主视图拆出 `PortfolioMethods` 还 250 行硬限 | `TestPortfolio::test_rows_carry_name_from_pricing_snapshot` | none | 2026-11-26 |
| P4-35 | refactor | ui | done | D-17 首次偿还：`Segmented` 组件收口 5 处重复的 wb-tab 单选行（equity 年限/区间档、statements 四子页+期次档、economics 指数切换）；其余 5 个原子无触发场景不预造 | `quality/baselines/components.json`（Segmented usage=8） | none | 2026-11-26 |
| P4-36 | fix | tool:economics | done | **宏观序列真实模式恒「返回结构异常」修复**：真实 `macro.query` 是扁平 dict（series 顶层、新→旧、≤10 期、未知码=骨架点），demo 曾捏成信封形+旧→新+12 期（D-27 三重失真）；handler 两种形状都认 + sas 升序归一 + 全 None 归「无可用值」 | `TestEconomics::test_series_accepts_real_flat_desc_shape` | none | 2026-11-26 |
| P4-37 | feat | quality | done | **`make smoke` 真实模式全工具冒烟**（11 项断言：10 工具+equity 三分区）：D-27 已四连「演示绿真实崩」，离线契约钉路径钉不住真实形状——对运行中的服务逐工具发真实请求断言关键块；首轮 11/11 绿（equity 双层嵌套 data.data 已在脚本中显式 unwrap）；CI 不跑（无凭证），`make smoke` 实跑 11/11 | `gates/smoke.py` | 1 轮≈几十次真实请求 | 2026-11-26 |
| P4-38 | feat | tool:watchlist | done | **盘中实时开关**：live_many 本就是盘中日K（休市=最近收盘快照）——live=true 时现价/涨跌幅/额/市值以它为准并标 `live`；live 日期≥快照才覆盖（停牌票现价不倒回）；「实时」= live 端点最新快照的诚实口径 | `TestWatchlist::test_live_merge_overrides_price_when_newer` | 0（复用伴取） | 2026-11-26 |
| P4-39 | feat | tool:equity | done | **分时分区**：`kline.query_min1_live` 当日 1 分钟（真实扁平形 bars 升序 t/close + trading_day/updated_at，~1.6k EC/次，用户点分区才发）；空分时 intraday=false + note 不回退日 K | `TestEquity::test_minute_section_real_shape` | ~1.6k EC/次（用户触发） | 2026-11-26 |
| P4-40 | feat | tool:dashboard | done | **指数盘中瓦片**：`kline.query_index_last_live_many`（keys 参数，1 次 ~364 EC 覆盖 4 指数）拼进 KpiStrip，红涨绿跌 + 盘中快照日期 hint；失败只丢瓦片并告警。后被 P4-46 盘面三卡取代（chips 移除，live 取数延续在 pulse） | `TestDashboard::test_index_cards_live_with_date_guard` | ~364 EC/次（首屏） | 2026-11-26 |
| P4-41 | feat | quality | done | 冒烟扩至 12 项（+equity 分时）：盘中实测 茅台 1462.99/-0.80%（vs 收盘 1474.84/+1.02%）、分时 28 分钟点 updated 09:57:50——实时三面浏览器全部实测 | `gates/smoke.py` 实跑 12/12 | none | 2026-11-26 |
| P4-42 | feat | tool:equity | done | **概览盘中现价**：`kline.snapshot`=上一已完成交易日（盘中页顶停昨天，用户实测撞上）→ 并一笔 `kline.query_last_live`（18 字段实测逐键；ETF 返回 `{"ok":false}` dict 非异常、无覆盖返回 None，三种「无」形状都兜）；live 日期严格新于快照日才覆盖 + 「实时」小标（语义同自选页） | `backend/workbench/tools/equity/handler.py` | +92 EC/次 | 2026-11-26 |
| P4-43 | fix | tool:equity | done | **分时无数据原因化**：用户报「分时没数据」实锤=指数（000300/index.hs300）与 ETF（510300）在个股分时入口下全空——`index.` 前缀显式路由 `query_index_min1_live`（与个股分时同形，实测 57 点）；空态 note 三分（未开盘+无分钟源 / 上游无覆盖 / 指数键无覆盖） | `backend/workbench/tools/equity/bars.py` | 指数分时另计（约同个股分时） | 2026-11-26 |
| P4-44 | feat | ui | done | **分时图可读性**：LineChart 加 `scale` 选项（y 轴脱离 0 值比例，默认不变）——此前 ECharts 默认含 0，3900 点的指数分时线贴顶成「平线」、±1% 波动不可见（截图实锤）；分时开启后 y 域贴数据（1455–1470 盘中实测） | `frontend/src/components/ui/LineChart.vue` | none | 2026-11-26 |
| P4-45 | feat | tool:equity | done | **分时均价线 + 刷新 force**：上游无均价字段（先查已有确认）→ 自算当日 VWAP（累计 amount÷volume，指数量纲不合跳过、比例出 [1/3,3]× 价带丢弃防量纲破损）；「刷新」按钮透传 force 绕 30s TTL 直取（仅 live/分时，慢变档案仍走缓存）；配套 wmshare `volume_delta` 手→股修复（9d4ec52） | `backend/workbench/tools/equity/bars.py` | force 时 +1 次上游 | 2026-11-26 |
| P4-46 | feat | tool:dashboard | done | **今日盘面三卡**：上证 shzs / 深证成指 **szcz**（2026-11-26 实测 10102.04 与主站逐位一致）/ 创业板指 cyb——现价+涨跌+高低+分时 mini（首屏直出 ~1.6k EC/张，用户拍板）；**date 守卫**防上游兜底假行（cyb live 源间歇断供时返回与 bogus 逐位同值、date 停上一交易日的假行——不设防把昨天画成今天，D-39）；cyb 无分时如实无小图 | `backend/workbench/tools/dashboard/pulse.py` | 3×~1.6k + 364 EC/首屏 | 2026-11-26 |
| P4-47 | feat | tool:dashboard | done | **涨跌分布直方图 + 涨跌幅双榜**：复用 `screener.index_breadth_bins`/`index_top_movers`（行情页同源，AUTO 廉价）；bins 柱色按 label 涨跌语义（计数全正，BarChart 加 colorOf 逐柱回调）；双榜 desc=True/False 各 5 条；失败降级空块+告警 | `backend/workbench/tools/dashboard/pulse.py` | 廉价 AUTO | 2026-11-26 |
| P4-48 | feat | ui | done | LineChart 加 `bare` 模式（隐轴贴边 sparkline，指数卡 mini 用）；DashboardIndices/DashboardPulse 组件 + DashboardView 组装（236 行）；KpiStrip 移除指数 chips（三卡取代）。**行业热力图未做**：指数 live 对 industry.SXX 键静默丢弃（探针空 dict，D-38 记因）——探针过再做 | `frontend/src/features/dashboard/DashboardPulse.vue` | none | 2026-11-26 |
| P4-51 | feat | tool:assistant | done | **AI 助手（单 agent · 数据按域分组）**：初版多 agent（编排+专员）实测两跳模型请求拖慢回答，用户要求收回——现为一个 agent + 按域分组的扁平工具面（行情/基本面/筛选/宏观/组合，描述带【域】前缀 + 固定域序）；系统提示只放每域一行卡片，细口径 `read_skill` 按需读；清单即契约（registry.json 5 域，契约测试对照 wmshare 目录防编造）+ 技能即数据（skills/*/SKILL.md，~/.wmshare/workbench/skills 外置覆盖）；宿主来源账统一编号、成稿 [n] 引用；单轮 EC 预算闸（WMSHARE_LLM_MAX_EC 默认 5000）+ 软 8/硬 15 工具轮；llm.py 纯 stdlib 流式（OpenAI 兼容，Accept-Encoding: identity）；chat 异步任务 + stream 轮询信封（无 SSE 新机制）；会话存 SQLite、每轮转写 JSONL；前端助手页（阶段胶囊/来源芯片/会话侧栏，markdown-it html:false） | `backend/workbench/tools/assistant/runner.py` | none | 2026-11-27 |
| P4-50 | feat | tool:screener | done | **选股非负守卫（用户：选股要顾虑掉负值）**：亏损股 PE 为负会把「低估值」变成「亏得最狠」。exclude_negative 默认开，服务端对 where/order 引用的全部指标追加 `> 0`（省 EC：被挡的行不计费），「或」表达式先加括号防优先级吃掉守卫；显式已写 >0 不重复；warnings 如实披露；保存策略仍存原文（守卫是执行口径）；低估值示例自带 `> 0`；前端「排除负值」勾选（localStorage 持久）。**2026-11-27 修正**：布尔标志位（`$IS_*`/被 `!` 取反）跳过——否则 `!$IS_ST` 与 `$IS_ST > 0` 互斥；商誉/有息负债等零值合法比率改用 `>=-1e-6`，只排除负值、保留 0 | `backend/workbench/tools/screener/handler.py` | none | 2026-11-27 |
| P4-49 | fix | tool:dashboard | done | **页级日期口径统一（用户：实时与非实时混在一起）**：盘面三卡 11-26 与页头「最新交易日 11-25」同页打架——指数日 K 盘后才物化、推断恒滞后一天。trading_day 改取 max(指数K线日, 盘面卡日期)；资金流卡补日期 chip（上游无日期，标推断口径）。估值 11-25 / 股息率 09-30 保持独立标注（真实滞后的例外，看得见） | `backend/workbench/tools/dashboard/handler.py` | none | 2026-11-26 |

## P5 · 画布与图表

| id | type | scope | status | acceptance | evidence | ec_impact | updated |
|---|---|---|---|---|---|---|---|
| P5-01 | feat | ui | done | **轻量状态保存**（用户拍板范围）：各页档位/输入存 localStorage（equity 分区/期次档/年限/区间 + 上次标的、economics 指标、backtest 参数、screener 表达式、portfolio 方法+成交），重载原位恢复；**只恢复选择不新增请求时机**（begin/end 不持久化——滚动窗冻结成绝对日期是 bug）；localStorage 异常静默回落 | 浏览器实测：财报季报档与宏观 $PMI 重载恢复 | none | 2026-11-26 |
| P5-02 | feat | ui | proposed | 12 类图表双主题 + 色盲变体可渲染 | — | none | 2026-11-25 |
| P5-03 | fix | ui | done | KpiStrip 均衡拆行做真：docstring 一直声称「7 容 5 列 → 4+3」但实现是 flex-wrap 贪心（实际 5+2）——改为对半拆行（>5 瓦片分两行各 ceil/floor），≤5 单行不变 | 浏览器实测：回测 8 瓦片 → [4,4]，dashboard 4 瓦片 → [4] | none | 2026-11-26 |
| P5-04 | refactor | design-system | done | **UI 商务风 P0（ADR-002）**：语义色/UI 字体栈/阴影/布局令牌自定，12 色图表盘与等宽字体族仍按 ADR-001 移植；Business Light 默认 + Business Dark；顶栏 56px/侧栏 220px/PanelShell 白卡轻阴影；body 无衬线、表格数值/KPI 等宽；`wb-btn/input/tab/chip` 浅色化；主题/CVD 经 prefs 持久化；Line/Bar 关闭默认入场动画。**视觉基线随 D-12 暂缓**，以亮色 3 页目视 + 对比度抽查代替；DataTable 吸顶/密度、KPI/chips、图表色板留 P1 | `tests/test_frontend_contract.py::test_default_theme_is_light_and_persisted` · `docs/UI_BUSINESS_THEME.md` | none | 2026-11-27 |
| P5-05 | fix | ui | done | **选股结果可读性（用户反馈「这里没改啊」）**：表达式输入改多行 textarea；结果表补 ROIC/净利率/现金流净利/商誉净资产/有息负债/ST/银行中文列名；小数比率显示百分数、布尔显示是/否；守卫告警透出页面（`useTool` 原有 warnings，页面此前未渲染） | `frontend/src/features/screener/labels.ts` · `frontend/src/features/screener/ScreenerView.vue` | none | 2026-11-27 |

## P6 · 质量闸

| id | type | scope | status | acceptance | evidence | ec_impact | updated |
|---|---|---|---|---|---|---|---|
| P6-01 | feat | quality | proposed | 9 工具 × 2 主题截图基线入库（**暂缓**：CI 无浏览器 + D-21 使 IAB canvas 截图不可用，离线门禁做不了真截图；待部署形态明确后走无头浏览器） | — | none | 2026-11-25 |
| P6-02 | feat | tool:demo | done | 演示模式全工具可跑：smoke 同一套断言对 `run.py --demo` 服务实跑（gates/smoke.py `--port`），真实/演示双向 11/11 | `gates/smoke.py` 双向实跑 11/11（2026-11-26） | none | 2026-11-26 |
| P6-03 | docs | docs | done | **第 8 门禁 `check_docs_links`**：README/AGENTS/docs 的 markdown 相对链接（含图片）必须指向存在的文件，代码围栏不扫，外链/纯锚点跳过验证但计数 | `tests/test_gates_selftest.py`（清单含新门禁）+ 临时坏链注入实测 | none | 2026-11-26 |
| P6-04 | feat | quality | done | **移除 demo 运行时模式（用户：不需要 demo）**：内置假快照与「不骗人」相悖，免注册已是无凭证真实数据。client/demo_* 四模块（1,167 LOC）迁 `tests/shape_*` 作离线夹具；fetchers 三态改 credentials/public_pool/missing（MissingFetcher 任何取数以可分类异常失败，映射 config 指引）；FakeFetcher 变纯测试替身（resolver 注入，未注入 KeyError）；`--demo`/页顶演示徽章/appinfo demo 字段全撤，页顶改「未接入 · 原因」 | `tests/test_auth_mode.py::TestFetcherFlags::test_missing_fetcher_fails_with_classifiable_error` | none | 2026-11-27 |
| P6-05 | docs | docs | done | **对标复评 2026-11-27（FinceptTerminal v4.5.3）**：按个人本地工作台口径重排功能矩阵（矩阵本身为维护者私有笔记，不入库）；补 AI 助手/选股守卫/KLine/设计系统漂移；交互/数据/AI 评审落成 UI 商务风提案（钉钉式，仅文档）；登记 D-41~D-46 | `docs/UI_BUSINESS_THEME.md` | none | 2026-11-27 |

---

**统计**：总计 121 · done 115 · in_progress 0 · accepted 0 · proposed 6

## 阶段验收记录

（每阶段结束时追加，格式：`### <阶段> · <日期>` + 门禁输出 + 视觉基线差异 + 遗留债务）

### P3 + P4 · 2026-11-25 · 九工具闭环

**交付**：`/api/*` 14 个端点全部启用业务逻辑（前端 10 页可切换）。

| 类目 | 内容 |
|---|---|
| 后端 handler | `tools/{watchlist,markets,economics,backtest,dashboard,screener,equity,portfolio,ec_estimate,key}/handler.py` |
| 账本内核 | `client/ledger/{types,basis,positions,performance}.py`（五法 / 价格·汇率拆分 / TWR / VaR） |
| 共用件 | `tools/_shared.py`（取数 + 信封 + 错误分级）、`tests/shape_gen.py` + `shape_data.py`（离线形状夹具） |
| 前端 | `composables/{useTool,format}.ts`、`components/ui/{LineChart,BarChart,PanelShell}.vue`、`components/layout/{AppTopbar,AppNav}.vue`、10 个 `features/*/View.vue` |
| 样式 | `styles/controls.css`（`wb-*` 共用控件，消掉 10 页的重复样式） |

**门禁输出**（`make check`，全绿）
```
layers 130 · sizes 409 · tokens 181 · envelope 4 · contract 22 · plan 188 · components 10
pytest: 298 passed
```

**实跑验证**（`run.py --demo`，13 个端点全 200 / ok=true）
```
sources     119 数据集 · fresh 115 / stale 3 / expired 1
watchlist   5 行 · 请求 1 次            ← 「批量请求数 == 1」断言成立
dashboard   4 指数 · manual_calls=0     ← 首屏零付费调用
backtest    3 笔成交 · 60 净值点 · 8 汇总
portfolio   五法 5 项 · 已实现 21360    ← 五法结果互不相同
screener    命中 5 · 3 示例表达式
economics   12 序列点 · 6 期限 · 4 币种  ← 曲线不插值
```

**本轮修掉的真实缺陷**（都是「显示正确但数字/布局是错的」那类）
1. `DataTable` 的 `.grid` 与页面布局 `.grid` 撞名 → 表格被继承 `display:grid`，表头与单元格错位 296px。改名为 `.wb-table`。
2. `mark_to_market` 对清仓标的 `continue`，导致已实现盈亏从组合合计里消失。
3. `var` 的分位下标受浮点误差（`(1-0.95)*20 = 1.0000000000000009`）影响，20 个样本取到第二差而非最差。
4. 演示数据：四只指数 PE/PB 完全相同、所有标的 20 日涨跌相同、未知宏观码仍返回序列 —— 三处都会让人把演示假象当数据事实。
5. `check_plan` 的测试计数正则 `^def test_` 漏掉类内方法（新写的 65+35 个用例一个都不计入），下限棘轮永远绿。
6. `check_tokens` 把 Vue 槽位简写 `#fee` 判成裸色值（三字符全是 hex 字母）。

**遗留**（已登记 `DEBT.md` D-14..D-20）
- 表格无虚拟滚动（>2000 行卡）；图表仅 2 类（缺 K 线/热力/散点等 10 类）
- UI 原子缺 7 个（Tabs/Drawer/Toast/Tooltip/Segmented/NumberInput/Empty）
- 分红拆股对账本成本的影响未建模；多币种仅支持单外币
- 12 列拖拽画布与命令面板未做（对标评审已记为「不做」，理由见 `DEBT.md` D-14/D-19）

### 访问方式修正 · 2026-11-25

**用户一句话点出的设计错误**：「wmshare 不用凭证也可以使用啊」。

原设计把「没配凭证」等同于「演示模式」，于是装了 SDK 的用户直接启动
看到的是一屏内置假数字——而 `Client.from_env()` 在凭证双缺时本就能
免注册真实取数（`auth_mode == "public_pool"`）。假数字与真数字长得一样。

**修正**：拆成三档 `credentials / public_pool / demo`，只有 `demo` 给假数据。
页顶按档位显示不同标签（绿=自有凭证、蓝=免注册、黄=演示+原因）。

**顺带发现的两个更严重的缺陷**（都只在真实模式暴露，演示模式全掩盖）：

1. `screener.query` / `backtest.run` / `screener.index_*` 是**组合门面**，
   不在 wmshare 目录里。用 `client.call()` 调会抛 `CatalogError: 未知函数`。
   新增 `Fetcher.facade()` 区分两条路径；`tests/test_real_mode_contract.py`
   断言**走的是哪条路径**（不只是有数据）。
2. `kline.index_breadth_summary` 要求显式 `idx`，门面则自行解析最新索引。
   调错路径得到「缺少必填参数」——行情页/驾驶舱在真实模式白屏的根因。

**免注册实测边界**（页顶标签与后端 `auth_mode` 三档）：
`screener.query` 与 `kline.query_last_live_many` 被服务端策略拒绝
（自选页已自动逐票降级并告知请求次数；选股页如实报 config 并指引配凭证），
其余工具全部可用。

**再一个「零 vs 缺失」**：上游对未供数字段给 `0`（创业板指 PB/股息率），
直接渲染成 `0.00` 看着像真实极低估值。handler 层加 `_positive()` 归一为
缺失；breadth 的 `limit_up/limit_down` 真实不存在，KPI 改为「有才显示」。

**三模式实测**：免注册（上涨 616/下跌 4956，真实）· `--demo`（快照 2026-11-20
+ 原因）· 有凭证（自选 1 次批量，degraded=False）。pytest 275 passed。

### 财务报表 domain 修正 · 2026-11-25

用户点开「财务报表」看到 `参数 domain='income' 不在允许值
['fin.balance_sheet', 'fin.income_statement', 'fin.cashflow_statement']`。

**第三类「演示掩盖真实」的错误**（前两类是组合门面与免注册语义）：

1. **两套命名**：UI 简称 `income` vs SDK 全名 `fin.income_statement`。
   加显式映射 `STATEMENT_DOMAINS`，测试断言**发出的参数是全名**。
2. **两条实现路径**：`cli.statements.income()` 是门面（走 eval + assign），
   返回 `cn` 为上游英文键；`rptdom.statement` 目录函数给中文名 + 跨期 `vals`。
3. **形状完全不同**：真实是**跨期透视** `list[{cn,k,vals{期次:值}}]`
   （每科目一行、各期一列），而我按单期 `[{key,label,value,yoy}]` 捏了
   handler 与演示数据——两处一起错，所以演示模式看着完全正常。

**修复**：handler 发全名、按 `periods` + `rows` 返回；演示数据改成同构；
前端改为动态期次列（科目 × 2025/2024/2023/2022）。

**实测**（免注册·真实）：利润表 25 科目 × 4 期、资产负债表 52 × 5、
现金流量表 13 × 5。茅台 2025 营收 1688.38 亿、净利 853.10 亿、货币资金 516.91 亿。
pytest 282 passed。

**教训**：`test_demo_shape_matches_real` 这条断言必须逐 target 加——演示数据
要按**真实响应**捏，不能按前端方便捏。

### 三表与分红 · 2026-11-25

用户连问两个「为什么没有」：

1. **财务报表为什么只有一个表** —— 三表其实都能取，但前端只有「利润表」
   一个视图，`domain` 永远发 `income`。加三表切换（利润/资产负债/现金流量），
   实测 25×4 / 52×5 / 13×5 科目×期次，全是真实数据。
2. **分红是有数据的** —— 确实有，是我调错了接口：
   `bonus.snapshot_yield_ttm` 返回**裸 float**（0.0354），按 dict 处理
   得到 `{}`，页面显示「—」。改用 `bonus.snapshot`（一个接口给全 18 字段）
   + `bonus.query_list`（逐次派息），现在 11 字段 + 33 次明细。

**顺带修的两处**：
- 键名 `fields` 被估值分区占用（string[]），分红改 `dividend_fields`；
  同一分区集里两个 `fields` 指两种东西，前端必读错。
- 上游英文枚举 `valley` 直接显示给用户，改为「低位（近 3 年谷底）」。

**新增断言**（`test_real_mode_contract.py` 增至 27 条）：
- 分红必须用 `bonus.snapshot`，**不得**用 `snapshot_yield_ttm`（裸 float）
- 每个字段必须声明 format（pct/money/num/text），前端不猜口径
- 三表的 domain 必须各不相同（防「忽略参数、永远发 income」）
- 演示数据形状与真实同构

**代码拆分**：`EquityStatements.vue` / `EquityDividend.vue` /
`tools/equity/dividend.py`（handler 354→275 行）。pytest 292 passed。

### 主要指标前置 · 2026-11-25

用户点出实务顺序问题：「财务报表应该先看主要指标表啊」。

确实——原来默认落在 49/52 行科目明细上，等于让用户自己在几百个数字里
找重点。改为四子页，**主要指标排第一且为默认**：

主要指标 → 利润表 → 资产负债表 → 现金流量表

**主要指标走另一条路**（重要）：`rptdom.statement` 的 `domain` 只接受三张
会计表全名，**不含** `fin.indicator*`。指标表必须走门面
`cli.statements.indicators()`（内部 `build_statement_xs` + `eval_result`），
实测免注册可用，返回 49 项 × 5 期。

**上游 `cn` 不可信**：它是 `k` 的副本（`basicEps`、`grossProfitRatio`），
不是中文名。自建 `INDICATOR_LABELS` 映射 12 个确认过的指标并标注口径
（money/pct/num/days）；未登记的原样显示 key——**不猜中文名**，猜错比
英文更难发现。

**首屏顺序按分析阅读习惯**：规模（营收/归母净利）→ 盈利（ROE/毛利率/
净利率）→ 每股（EPS）→ 效率（周转/比率）。

实测茅台 5 年：营收 1094.64→1720.54 亿、ROE 29.89%→32.53%、
毛利率 91.18%、EPS 41.76→65.66。pytest 298 passed。
