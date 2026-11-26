# 贡献指南

> 本文件是**人类贡献者的唯一事实源**。`AGENTS.md` 是给 AI 代理的摘要，冲突时以本文件为准。

## 开始之前

```bash
git clone https://github.com/open-winmale/wmshare-workbench && cd wmshare-workbench
python -m pip install -e ".[dev]"
make preview          # 门禁 + 测试，全绿才能开工
```

## 工作流

1. **先看 `docs/PLAN.md`** 确认你要做的工作项在哪个阶段。
2. **在 `docs/PROGRESS.md` 登记工作项**（`proposed` → `accepted`），
   `acceptance` 列必须写**可机械验证**的条件。
3. **写代码**。
4. **`make preview` 全绿**。
5. 把工作项改 `done`，填 `evidence`（指向测试名或文件路径）。
6. 更新统计行（`**统计**：总计 N · done N · ...`）——`check_plan` 会校验它。

## 坑：验收条件怎么写

验收条件不是给人看的，是给门禁看的。写得含糊，三周后没人知道算不算完成。

| 别写 | 要写 |
|---|---|
| 加载快 | `/api/dashboard/run` 在 `FakeFetcher` 下 p95 < 300ms，且不发 `Manual` 级调用 |
| 排序对 | `1.2万` 单元格的排序键为 `12000`；点击列头后首行为最大值 |
| 成本可控 | `ec_pred_hi > 40000` 时出现二次确认；取消后**零网络请求** |
| 空态完整 | 五个面板各自在空数据下渲染 `EmptyState` 且不抛异常 |

## 门禁说明

八个门禁（`make check`）都在 `gates/` 下，全部离线。

**门禁红了怎么办**：

- **不要**改门禁去迁就代码。
- 若确实是基线过时（如重构后文件变小、需要清理已删文件），跑对应的 `--write`
  或手工收紧基线值。
- 若需要放宽约束，在 `docs/DEBT.md` 记一条并说明原因，然后在 PR 里单独讨论。

## 新增工具页的清单

见 `docs/PROJECT_SPEC.md` §8.1。摘要：

- [ ] `tools/<name>/{handler.py, panels.py}` + `frontend/src/features/<name>/`
- [ ] 注册 `TOOLS` / `HANDLERS`
- [ ] 五态全实现（loading / empty / error / stale / partial）
- [ ] 成本前置 + `Manual` 归类 + 二次确认
- [ ] 离线测试（正常 / 空 / 上游错 / 预算闸零请求）
- [ ] `FakeFetcher` 注入分支（数据表或 resolver）
- [ ] 更新 `docs/PANELS.md`、`PROGRESS.md`、`baselines/tests.json`

## 新增门面调用：先查目录

**这是最重要的一条**。动手算任何指标之前，先确认 wmshare 里是否已有算好的：

```python
import wmshare
cat = wmshare.load()
cat.search("ROE")            # 找指标码
cat.function("kline.bars")   # 看签名
```

自己重算 = 重复造轮子，且口径必然与平台漂移。

## 提交信息

```
type(scope): 中文描述

为什么这么改（不是改了什么——改了什么看 diff）
```

`type` ∈ `feat` `fix` `refactor` `chore` `docs` `test` `perf` `ci`。
breaking 用 `!`，如 `refactor!: 移除 X`。

## 不做的事

- 不加第三方运行期依赖（`dependencies = []` 是产品价值的一部分）
- 不把服务绑到 `0.0.0.0`
- 不擅自新增 CI/CD 配置
- 不在测试里构造真实 `wmshare.Client`（会烧共享配额）
- 不复制对标物（FinceptTerminal）的代码、图标、文案
