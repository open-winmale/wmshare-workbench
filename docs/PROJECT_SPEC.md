# 项目与架构规范

> 目的：**防项目腐化**。本文件是可执行的约束清单，不是愿景陈述。
> 每条硬规则要么被 `gates/check_*.py` 机械校验，要么在 §10 标为 `manual` 并进评审清单。
> 冲突时以本文件为准；改动本文件需 ADR。

## 1. 防腐化的核心假设

腐化不是「写错代码」，是**结构失去约束后逐步退化**。我们对标对象 `FinceptTerminal` 在自己的
`docs/ARCHITECTURE.md` 里把腐化结果列成了清单，这份清单是本项目的反面教材：

| 对标物的技术债（原文） | 本项目的对应硬规则 |
|---|---|
| “a 3,300-line CMake file” | 单文件行数预算，超限即红（§3） |
| “40+ singletons currently in use”, “No new singletons” | 禁止新增单例，依赖走显式传参（§4） |
| “stringly typed event bus” | 事件必须枚举化，禁止裸字符串（§4） |
| “screens never unload (100–250 MB per window)” | 面板必须有卸载钩子，内存基线门禁（§7） |
| “Python cold starts 0.5–1.5s” | 重活走进程外或预计算，不在请求路径上冷启 |
| “a three-way caching scheme” | 只有一层缓存（`hub`），禁止旁路（§4） |
| “remaining UI-thread queries” | UI 层零阻塞调用（§2） |

**推论**：我们不做「大而全的单体」，做「小内核 + 可插拔工具」。工具的增删不应触碰内核。

## 2. 分层与依赖方向（前后端分离，一个契约边界）

**前后端物理分离，跨边界不得 import**——只能走 HTTP JSON。契约真源在
`backend/workbench/core/envelope.py`，前端读生成的 `frontend/src/api/contract.ts`。

```
┌─────────────────────── frontend/src/ ───────────────────────┐
│ depth 3  features/    工具页面，禁止横向 import              │
│ depth 2  composables/ 状态与编排                             │
│ depth 1  components/  纯展示，只接 props                     │
│ depth 0  api/         唯一 fetch 处 + 生成的 contract.ts     │
└────────────────────────────┬─────────────────────────────────┘
                             │ HTTP JSON（★ 契约边界）
┌────────────────────────────┴─────────────────────────────────┐
│ depth 0  core/       信封、单位、格式化（零 IO，零本项目 import）│
│ depth 1  platform/   SQLite、凭证、HTTP、文件、日志            │
│ depth 2  client/     hub / autoload / ec / fetchers           │
│ depth 3  tools/      工具 handler + panels                    │
└────────────────────── backend/workbench/ ────────────────────┘
```

**深度语义统一：数字越小越深。** 两套层次各自独立编号，不混在一个图里
（旧版把 `ui`/`features` 与 `core`/`client` 塞进同一五层图，但 Python 侧根本没
`ui`/`features`、前端也没 `platform`，导致 `allowed_edges` 里出现跨语言废边）。

**规则**

1. 允许边：`depth[dst] ≤ depth[src]`（向下或同层）。反向即红。
2. **判定顺序：先查白名单，再判方向。** 顺序反了会让每条合法向下边被误判为反向
   （旧版 `check_layers` 的真实 bug，详见 §12 教训）。
3. `core/` 是叶子，不得 import 任何本项目模块。
4. 同层允许横向，但 `features/a` 与 `tools/a` **不得**跨工具 import。
5. `components/` 禁止 import `composables/`（组件不该有状态编排）；允许 import
   `api/`（需要类型）。
6. `api/` 是前端**唯一** `fetch` 处，其它层出现 `fetch(` 即红。
7. `backend/workbench/` 顶层模块（`server.py`/`__main__.py`）归 `platform` 层。

**机械校验**：`gates/check_layers.py` 解析 Python 的 `import`/`from`（**含相对
import**）与前端的 `@/`、相对路径说明符，对照 `quality/baselines/imports.json`
（version 2，双套 `depth` + `allowed_edges`）。

## 3. 模块与文件预算（棘轮，只允许变小）

| 对象 | 上限 | 理由 |
|---|---|---|
| 单 `.py` 文件 | 400 行 | `server.py` 特许 600，且必须在文件头注释说明为何不能再拆 |
| 单 `.vue` 文件 | 250 行 | 超了说明该拆原子组件 |
| 单函数 | 60 行 | |
| 单函数圈复杂度 | 12 | |
| `backend/workbench/tools/<n>/handler.py` | 300 行 | 业务超了挪 `panels.py` |
| `frontend/src/composables/*.ts` | 120 行 | |
| 单个 `<style>` 块 | 150 行 | 超了说明该抽组件 |

基线：`quality/baselines/sizes.json` 与 `complexity.json`。
**允许欠账存在，但只允许变小**：记录当前值，任何文件变大即失败。
新增文件超限直接失败（无历史欠账可继承）。

## 4. 禁止清单

| 禁止 | 替代 | 校验 |
|---|---|---|
| 新增模块级可变全局 | 显式传参或 `@dataclass` 容器 | manual |
| 新增单例 | 依赖注入，构造期组装 | manual |
| `except Exception: pass` | 捕获具体异常 + 记日志 + 上抛或显式降级 | `check_envelope` 附带扫描 |
| 裸字符串事件名 | `enum` 成员 | manual |
| 组件内写十六进制色值 / 裸 px | 只用 `var(--wb-*)` 令牌 | `check_tokens` |
| 旁路 `hub` 直接取数 | 必须经 `hub.get_or_fetch()` | manual（无静态检查手段） |
| 用格式化文本排序 | 数值排序键 | manual |
| 用 `0` 表示缺失 | `NaN` 哨兵 + UI 渲染 `—` | manual |
| 静默截断结果 | 显式 `truncated` 标记 + UI 提示 | `check_envelope` |
| 测试里构造真实 `Client` | 只许 `FakeFetcher` | `check_plan` + 测试审查 |
| `features/*` 或 `components/*` 直接 `fetch` | 经 `frontend/src/api/` | `check_layers` |
| 服务绑 `0.0.0.0` | 固定 `127.0.0.1` | manual（评审 + 启动日志断言） |

**说明**：标 `manual` 的条目由 §10 的评审清单在每次阶段性评审时逐条过，不依赖脚本。
之所以不硬做静态分析，是因为这类规则误报率高、会逼人加绕过注释，反而降低约束力。

## 5. 契约管理

### 5.1 信封契约（冻结）

`backend/workbench/core/envelope.py` 是唯一真源：

```python
ENVELOPE_VERSION = 1

{
  "ok": bool,
  "as_of": str,                      # 数据截至日；未知为 ""
  "data": Any,                       # ok=False 时 必须为 {}
  "meta": dict,
  "freshness": str,                  # fresh|stale|expired|unknown
  "warnings": list[str],
  "ec": dict | None,                 # {pred_lo, pred_hi, actual, model}
}
```

**铁律**：`ok=False` 时 `data` **必须为 `{}`**——这与 wmshare 的既有契约一致
（失败原因一律进 `meta`，绝不把错误塞进 `data`）。

### 5.2 变更流程

| 变更 | 级别 | 要求 |
|---|---|---|
| 新增可选字段 | MINOR | 更新 `docs/ENVELOPE.md` + `baselines/envelope.json` |
| 改字段名 / 改语义 / 删字段 | **MAJOR** | 须 ADR + 迁移说明 + 弃用窗口 ≥1 个 MINOR |
| 改 `freshness` 取值集合 | MAJOR | 同上 |
| 改 `ec` 子结构 | MAJOR | 同上 |

`gates/check_envelope.py` 校验：
1. `backend/workbench/core/envelope.py` 的字段集 == `baselines/envelope.json`
2. 所有 `handler.py` 里的 `return` 信封字面量键集 ⊆ 契约键集
3. `ok=False` 的返回必须 `data == {}`

## 6. 四级质量门禁

| 级别 | 触发 | 时限 | 内容 |
|---|---|---|---|
| **L0** | 保存 | <2s | `ruff format` + `ruff check --fix`（编辑器集成） |
| **L1** | 提交前 | <15s | `ruff check` · `ruff format --check` · 受影响的快速单测 · `check_tokens` |
| **L2** | `make preview` | <30s | 七个门禁 + 全量离线 pytest |
| **L3** | CI | — | L2 + 前端 `typecheck`/`build` + wheel 含 static 断言（结构见 ARCHITECTURE.md §7） |

**离线铁律**：L0–L2 **全部零网络零凭证**。任何需要网络的测试必须标 `@pytest.mark.live`，
默认跳过、CI 不跑。理由：wmshare 的匿名免费档在无凭证时**也会真实取数**，
测试里误构造 `Client` 会悄悄烧共享配额。

## 7. 棘轮基线（八份，只进不退）

| 基线文件 | 内容 | 判定 |
|---|---|---|
| `quality/baselines/imports.json` | 允许的跨层 import 边 | 新增边即红 |
| `quality/baselines/sizes.json` | 每文件行数 | 变大即红 |
| `quality/baselines/complexity.json` | 每函数圈复杂度 | 变大即红 |
| `quality/baselines/tokens.json` | 设计令牌清单（双主题必须齐全） | 删令牌即红；增令牌须带 `reason` |
| `quality/baselines/envelope.json` | 信封字段集 | 变更须 ADR 编号 |
| `quality/baselines/tests.json` | 每工具测试数下限 | 低于即红（`check_plan` 实现） |
| `quality/baselines/components.json` | UI 组件清单 + 引用处数 | 孤儿组件（0 引用）即红 |

**为什么用棘轮而不是绝对标准**：绝对标准（如「覆盖率必须 90%」）在项目初期不可达，
会逼人写无意义测试刷数字。棘轮保证「**不许变差**」，让质量单调改善。

## 8. 新增功能的验收模板

### 8.1 新增工具页

1. 建 `backend/workbench/tools/<name>/{handler.py, panels.py}` + `frontend/src/features/<name>/`
2. 注册 `server.py` 的 `TOOLS` 与 `HANDLERS`
3. **五态全实现**：loading / empty / error / stale / partial
4. **成本前置**：handler 入口调 `cost_estimate`，重活标 `Manual` + 二次确认
5. 离线测试：正常路径 + 空结果 + 上游报错 + **预算闸触发时零请求**
6. 离线夹具（`FakeFetcher` 注入数据表或 resolver；运行时无内置假数据）
7. 更新 `docs/PANELS.md`、`docs/PROGRESS.md`、`baselines/tests.json`

### 8.2 新增门面调用（最容易翻车）

1. **先核实签名**：`wmshare.load().cat.function("<name>")`，禁止凭记忆写
2. **确认返回形态**——已知陷阱：
   - `index.keys()` 返回**单列 DataFrame（列名 `"0"`）**，不是 list；可用键用 `index.universe_keys()`
   - `index.trend(key, window)` **只接受单个 key**，多键必须循环
   - `screener.index_breadth_summary()` 返回**裸 dict，不是信封**
   - `valuation.daily_basic()` 的 `data` 是**长表 `list[dict]`**，不是 DataFrame
   - `statements.*` 的 `vals` 是**嵌套 dict**，需客户端透视；且**不可批量**
   - `dividend.rating()` 冷缓存返回 `ok=false` + `meta.error="COLD_CACHE"`，**不重算**
3. **登记成本量级**与 `AutoRun`/`Manual` 归类（`docs/EC_BUDGET.md`）
4. **优先用原生批量**：`kline.batch_live` / `kline.snapshot(list)` / `valuation.daily_basic_multi` /
   `dividend.diagnose(symbols)` / `dividend.calendar(codes=)` / `screener.query` / `moneyflow.board`
5. 加缓存策略（主题 + TTL），禁止旁路 `hub`
6. 测试断言返回形态（不是「跑通就行」）

### 8.3 新增图表组件

1. 语义色只从 `--wb-up` / `--wb-down` 取，**不许用调色板色冒充涨跌**
2. 序列色按 `palette[i]` **固定分配**，不重排
3. 缺值**断线留白**，绝不补 0
4. tooltip 必须含 `as_of` 与单位
5. 双主题截图 + 色盲变体截图入基线
6. 提供「数据表」替代视图（无障碍要求）

### 8.4 新增 UI 原子

1. **≥2 个使用方**才允许进 `frontend/src/components/ui/`（否则留在 feature 目录）
2. props 全部类型化；枚举用联合字面量
3. **五态全实现**
4. 组件内零硬编码色值（`check_tokens` 拦）
5. 加进组件预览页
6. 更新 `baselines/components.json`

## 9. 腐化早期信号与处置

| 信号 | 阈值 | 处置 |
|---|---|---|
| 某文件逼近行数上限 | ≥90% | 重构，不许「再加一点点」 |
| 单工具测试数下降 | 任何下降 | 阻断 |
| 新增令牌无 `reason` | 1 次 | 阻断 |
| `TODO` 无工作项 id | 任何 | `check_plan` 报错 |
| 同一逻辑出现 3 次 | 3 处 | 抽公共，否则登记 `DEBT.md` |
| 覆盖率下降 | 任意 | 阻断 |
| 新增第二个缓存层 | 1 处 | 立即重构（单向缓存是硬约束） |
| 面板无卸载钩子 | 1 处 | 补 `unloadable` 声明或卸载逻辑 |

## 10. 评审清单（`manual` 条款，每阶段评审逐条过）

- [ ] 是否新增了模块级可变全局或单例？
- [ ] 是否出现裸字符串事件名？
- [ ] 是否有 `except Exception: pass` 或吞异常？
- [ ] 是否有「用格式化文本排序」的地方？
- [ ] 是否有「用 0 表示缺失」的地方？
- [ ] 是否静默截断了结果而未标 `truncated`？
- [ ] 是否有 `features/*` 直接 `fetch`？
- [ ] 服务是否仍然只绑 `127.0.0.1`？
- [ ] 是否有面板缺少卸载路径？
- [ ] 是否有组件内硬编码色值/像素（脚本已拦，抽查）？
- [ ] 同一逻辑是否已出现 3 次而未抽取？

## 11. 与技术无关的一条

**不替用户判断**。任何面板、文案、示例都不得给出买卖结论、目标价或仓位建议。
统计、分位、历史归因可以说；「应该买」「值得持有」不可以说。这条不进门禁，进评审红线。

## 12. 教训：门禁曾经集体失效（2026-11-25 审计）

第一版门禁看起来齐备（六个脚本、七份基线、16 个自检用例全绿），但审计发现
**15 处「规范声称校验了 X，代码没做」**。记录在此，因为它们都是会被重复踩的坑。

| 失效方式 | 具体 | 教训 |
|---|---|---|
| **判定顺序反了** | `check_layers` 先判 `depth[dst] < depth[src]` 为反向，但基线里 `core:0` 最深 → **每条白名单边都被判反向**，「未登记边」分支成死代码 | 白名单必须**先查再判方向** |
| **空仓库掩盖** | 上述 bug 之所以没暴露，是因为仓库零跨层 import，`scanned == 2`，门禁永远绿 | 门禁必须配「**该绿时也绿**」的用例，不只测「会红」 |
| **扫错目录** | `check_envelope` 扫 `repo/tools/*/handler.py`（门禁脚本目录），而规范写 `backend/workbench/tools/`。真实 handler 落地后完全不被检查 | 两个同名 `tools/` 是根因 → 门禁目录改名 `gates/` |
| **相对 import 盲区** | `if node.level: continue` → `from ..client import hub` 完全隐形。**想绕过分层，写相对 import 就行** | 必须解析 `node.level` 拼回绝对模块名 |
| **深度 1 免检** | `len(parts) < 2: return None` → `server.py` 等入口模块不参与校验 | 顶层模块归最浅层 `platform` |
| **别名漏检** | `LAYER_DIRS` 把 `tools`→`features`，但横向检查匹配字面量 `features` → 跨工具耦合抓不到 | 横向判定用**映射后的层名** |
| **死基线** | `tests.json` 声明「低于即红」，**无任何代码读取** | 基线要么被读，要么删掉——挂着不读比没有更糟 |
| **隐性松弛** | `sizes.json` 登记 217 行而实际 206、17 行而实际 15；棘轮只拦增大 → 白送 13 行额度 | 基线应为**实际值**；高出 >10% 时告警 |
| **未实现的预算** | `tool_handler`/`composable`/`css_block` 三个上限写在配置里，代码零读取 | 配置项必须有消费者 |
| **半实现的校验** | `check_tokens` 只在全文找一次令牌名 → 只写 `:root` 也能过，而语义是「双主题都要有」 | 声明「各自」就必须真的分别解析 |
| **不存在的入口** | `Makefile` 是 Python 脚本，**零个 make target**，但五份文档都写 `make check` | 文档里的每条命令都必须实跑验证过 |
| **重复的 ID** | `PROGRESS.md` 里 `P1-01..P1-04` 出现两次（旧「设计系统」段 + 「数据面」段），`check_plan` 不去重 | 台账 ID 必须全局唯一 |
| **假承诺** | 规范称解析 Vue 的 `@/` 别名、校验 hub 旁路、`ok=False` 时变量回溯 —— **全部不存在** | 写「机械校验」前必须先跑一遍确认 |

**三条可迁移的规则**：

1. **每个门禁都要有「该绿」和「该红」两类用例。** 只测该红的门禁会退化成
   「永远红」而被关闭；只测该绿的门禁会退化成「永远绿」而无人察觉。
2. **不要相信「扫了 0 项通过」。** 输出里必须有扫描计数；`check N 项` 里 N 过小
   本身就是信号。
3. **文档里的每条命令、每个路径、每个「已校验」，都要能被一条测试或一次实跑证伪。**
