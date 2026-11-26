# 信封契约

> 唯一代码真源：`src/workbench/core/envelope.py`
> 唯一基线：`quality/baselines/envelope.json`（由 `gates/check_envelope.py` 校验三者一致）

## 1. 为什么冻结信封

工作台的 9 个工具、前端 5 个 composable、所有导出都消费同一个结构。信封一旦随工具各自演化，
就会出现「每个面板长得差不多但不完全一样」的腐化——这正是对标物
`docs/ARCHITECTURE.md` 自陈的 “a three-way caching scheme” 的来源。

**所以：一个信封，版本化，只许追加。**

## 2. 结构（v1）

```json
{
  "ok": true,
  "as_of": "2026-11-25",
  "data": {},
  "meta": {},
  "freshness": "fresh",
  "warnings": [],
  "ec": {"pred_lo": 218, "pred_hi": 219, "actual": 219, "model": "screener_light"}
}
```

| 字段 | 类型 | 必填 | 语义 |
|---|---|---|---|
| `ok` | `bool` | 是 | 是否成功 |
| `as_of` | `str` | 是 | 数据截至日（`YYYY-MM-DD`）；未知为 `""` |
| `data` | `Any` | 是 | 载荷。**`ok=false` 时必须为 `{}`** |
| `meta` | `dict` | 是 | 补充信息（含失败原因、分页、缓存状态） |
| `freshness` | `str` | 是 | `fresh` / `stale` / `expired` / `unknown` |
| `warnings` | `list[str]` | 是 | 中文告警，逐条可读（如「资产负债表 数据期龄 128 天，超过预警阈值 90 天」） |
| `ec` | `dict \| None` | 是 | 成本预估与实际；无成本模型时为 `null`（**不填 0**） |

### 2.1 `ok=false` 时 `data` 必须为 `{}`

与 wmshare 的既有契约一致：**失败原因一律进 `meta`，绝不把错误塞进 `data`。**
理由是消费方（表格组件）拿到 `data` 就渲染；若 `data` 里混入错误对象，
表格会渲染出一行「error: ...」，比白屏更难排查。

### 2.2 `freshness` 取值语义

| 值 | 含义 | UI 表现 |
|---|---|---|
| `fresh` | 期龄 ≤ 预警阈值 | 无角标 |
| `stale` | 期龄 > 预警阈值，≤ 过期阈值 | 黄色 `STALE` 角标 + 期龄 |
| `expired` | 期龄 > 过期阈值 | 红色角标 + 期龄 |
| `unknown` | 无新鲜度真值（兄弟仓缺失/该数据集未登记） | 灰色「新鲜度未知」 |

阈值来源：`../airflow/data_monitor/stats_config.py` 的 `StatsCheck.staleness_days` / `warn_days`。

### 2.3 `ec` 子结构

| 键 | 类型 | 语义 |
|---|---|---|
| `pred_lo` | `int \| None` | 预估下界 |
| `pred_hi` | `int \| None` | 预估上界 |
| `actual` | `int \| None` | 实际消耗（来自 `meta.metering`） |
| `model` | `str` | 成本模型名；无模型时 `"none"` |

**无成本模型时 `pred_lo`/`pred_hi` 为 `null`，UI 显示「无成本模型」——禁止显示 `0`。**

## 3. 变更流程

| 变更 | 级别 | 要求 |
|---|---|---|
| 新增可选字段 | MINOR | 更新本文档 + `baselines/envelope.json` |
| 改字段名 / 改语义 / 删字段 | **MAJOR** | ADR + 迁移说明 + 弃用窗口 ≥1 个 MINOR |
| 改 `freshness` 取值集合 | MAJOR | 同上 |
| 改 `ec` 子结构 | MAJOR | 同上 |

## 4. 校验（`gates/check_envelope.py`）

1. `core/envelope.py` 声明的字段集 == `baselines/envelope.json` 的字段集
2. 所有 `tools/*/handler.py` 中的信封字面量键集 ⊆ 契约键集（不许出现野字段）
3. `ok=False` 的返回处 `data` 必须为 `{}`（字面量为 `{}` 或变量带回溯检查）
4. `ec` 缺模型时不得写 `0`（扫描 `{"pred_lo": 0` 之类字面量）

## 5. 与 wmshare 的关系

wmshare 的门面返回 `{ok, as_of, data, meta}`。本项目的信封**在其上只追加**
`freshness` / `warnings` / `ec` 三键，**不改动原有四键的语义**。
因此任何 wmshare 返回可以直接包装成本项目信封，无需转换层——这是刻意设计的兼容点。
