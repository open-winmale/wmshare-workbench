# 长期跟踪规范

> 目的：让「高质量落地」可核对。本文件定义跟踪结构、状态机、DoD 与**可机械验证的验收条件写法**。
> 配套脚本：`gates/check_plan.py`（六条阻断规则，见 §5）。

## 1. 三层跟踪

| 层 | 文件 | 粒度 | 更新时机 |
|---|---|---|---|
| **阶段** | `docs/PLAN.md` | P1–P6，每阶段带验收标准与退出条件 | 阶段变更时 |
| **任务** | `docs/PROGRESS.md` | 活动台账，一行一工作项 | 每次提交 |
| **缺陷与债务** | `docs/DEBT.md` | 技术债 + 已知缺陷，带触发条件 | 发现即记 |

配套：`docs/ADR/NNN-<slug>.md` 记录**不可逆决策**（主题动作、契约变更、依赖引入、跨仓抽取）。

## 2. 工作项状态机

```
proposed → accepted → in_progress → in_review → done
                          ↓             ↓
                       blocked        rejected
```

- `blocked` 必须写明阻塞原因与解除条件；超过一个阶段未解除，升级到 `DEBT.md`。
- `rejected` 必须写明拒绝理由（否则三个月后有人重做）。
- **不允许跳过 `in_review`**：所有 `done` 都经过一次全门禁 + DoD 核对。

## 3. 台账字段（`PROGRESS.md`）

| 列 | 说明 |
|---|---|
| `id` | `<阶段>-<序号>`，如 `P3-07` |
| `type` | `feat` / `fix` / `refactor` / `docs` / `debt` |
| `scope` | `hub` / `ui` / `tool:screener` / `docs` … |
| `status` | 状态机取值 |
| `acceptance` | **可机械验证的验收条件**（§4） |
| `evidence` | 指向测试名 / 截图基线 / 命令输出（`done` 必填） |
| `ec_impact` | `none` / `auto` / `manual`（是否新增付费路径） |
| `updated` | 绝对日期 `YYYY-MM-DD` |

**规则**：`ec_impact=manual` 必须在 `docs/EC_BUDGET.md` 有对应条目；`evidence` 必须能定位到真实存在的测试或文件。

## 4. 验收条件写法（强制）

必须写成**可机械判定**的句子。禁止「体验良好」「性能可以」「界面美观」。

| 差（禁止） | 好（要求） |
|---|---|
| 驾驶舱加载快 | `/api/dashboard/run` 在 `FakeFetcher` 下 p95 < 300ms，且不发出任何 `Manual` 级调用 |
| 表格排序对 | `1.2万` 单元格的排序键为 `12000`；点击列头后首行为最大值 |
| 成本可控 | `ec_pred_hi > 40000` 时二次确认弹窗出现；取消后**零网络请求** |
| 过期提示对 | `staleness_days=120` 且期龄 128 天时 `freshness=="expired"` 且 `warnings` 非空 |
| 主题统一 | 双主题下 15 个原子 + 5 个表格组件全部渲染，且无硬编码色值告警 |
| 空态完整 | 五个面板各自在空数据下渲染 `EmptyState` 且不抛异常 |

**一句话标准**：验收条件写完后，另一个人能照着写出一条断言。

## 5. `gates/check_plan.py` 六条阻断规则

1. 每个 `done` 工作项必须有非空 `evidence`，且其指向的**测试文件或文档真实存在**。
2. `PLAN.md` 里某阶段标 `done` 时，该阶段所有工作项必须全 `done`。
3. `DEBT.md` 每条必须有 `trigger`（何时偿还）与 `owner`；`severity=P0` 未偿不允许进入下一阶段。
4. `PROGRESS.md` 的统计行（总数/完成数/按类型）必须与表格行数一致——**台账不许手改数字**。
5. 任何 `TODO` 必须形如 `TODO(<id>): …`，且 `<id>` 在 `PROGRESS.md` 中存在。
6. `ec_impact=manual` 的工作项必须在 `EC_BUDGET.md` 有对应条目。

## 6. Definition of Done（按类型）

| 类型 | DoD |
|---|---|
| 后端模块 | 单测 + 边界断言 + 覆盖率不降 + `check_layers`/`check_sizes` 绿 |
| 工具页 | 五态 + 成本前置 + 离线夹具 + 双主题截图基线 + 路由冒烟 |
| UI 原子 | props 类型 + 五态 + 令牌校验 + 预览页 + ≥2 使用方 |
| 图表 | 双主题 + 色盲变体 + 缺值断线 + tooltip 带 `as_of` 截图 |
| 文档 | 上下游链接可解析 + 不超行数预算 |
| 修复 | **先写复现测试**，再修，测试永久保留 |

## 7. 评审节奏

| 频率 | 动作 | 产出 |
|---|---|---|
| 每次提交 | 更新 `PROGRESS.md` + 跑 L1 | — |
| 每阶段结束 | 跑全门禁 + 视觉基线更新 + `DEBT` 复审 + §10 评审清单逐条过 | 阶段验收记录追加到 `PROGRESS.md` |
| 每周 | 只看三件事：覆盖率趋势、债务新增、`done` 无 `evidence` 清零 | 周报 3 行 |
| 每季度 | 架构复审：是否出现第二个缓存、是否新增单例、文件预算余量、孤儿组件 | ADR 或重构工作项 |

**周报只需三行**。跟踪的价值在于「异常被看见」，不在于「填表完整」。表格越重，越早被放弃。

## 8. 证据沉淀

`evidence` 指向的产物分三类，各自存放：

| 类型 | 位置 | 例 |
|---|---|---|
| 测试证据 | `tests/` | `tests/test_hub_policy.py::test_ttl_boundary` |
| 视觉证据 | `quality/screenshots/<tool>/<theme>/<state>.png` | `screenshots/dashboard/obsidian/loading.png` |
| 命令证据 | `PROGRESS.md` 内联代码块（可复跑的命令 + 关键输出行） | `make check` → `6 gates ok` |

视觉基线**入库**（PNG），因为它是最容易悄悄退化的部分；测试和命令可复跑，不必入库输出。

## 9. 风险登记（`DEBT.md` 初始四条）

| id | 风险 | severity | trigger | 处置 |
|---|---|---|---|---|
| D-01 | 与 `wmshare-tools` 账本逻辑漂移 | P1 | 两仓 `portfolio` 计算函数出现第 2 处不一致 | 抽共享模块（破坏 `dependencies=[]`，需 ADR） |
| D-02 | `stats_config.py` 在兄弟仓，CI 缺失 | P2 | CI 首次跑 `--check` 时 | 显式 SKIP + 兜底表（沿用既有先例） |
| D-03 | B 类屏（期权/新闻）长期空占位 | P2 | 占位超过 2 个阶段仍未接数据 | 要么接源要么删屏，不许长期挂空 |
| D-04 | `index.trend` 逐键调用成本 | P1 | 驾驶舱出现 ≥5 键同时 `trend` | 改懒加载 + 显式「加载估值历史」按钮 |

## 10. 阶段评审清单（与 `PROJECT_SPEC.md` §10 联动）

每阶段结束时逐条勾选，未过项不得进入下一阶段：

- [ ] 全门禁绿（`make check`）
- [ ] 全量离线测试绿，覆盖率不降
- [ ] 本阶段所有工作项 `done` 且有 `evidence`
- [ ] `DEBT.md` 无新增 P0
- [ ] `manual` 条款评审清单逐条过
- [ ] 视觉基线已更新并与设计规范一致
- [ ] `EC_BUDGET.md` 与实际 `meta.metering` 同量级
- [ ] 文档链接可解析、行数未超预算
