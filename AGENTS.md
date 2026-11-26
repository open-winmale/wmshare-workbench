# AGENTS.md

给 AI 编码代理（Claude Code、ZCode、Codex…）的仓库工作约定。
**人类贡献者的唯一事实源是 [CONTRIBUTING.md](CONTRIBUTING.md)**，本文件只是代理视角的摘要；
两者冲突时以 CONTRIBUTING 为准。

## 门禁（提交前全部跑一遍）

```bash
make check      # 八个质量门禁，<1s，离线
make smoke       # 真实模式冒烟（动了取数形状/门面后必跑；需服务已启动）
make test       # 离线测试
make preview    # 上面两个一起跑（提交前用这个）
```

## 硬规则（按优先级）

1. **先改规范，再改代码**。新增能力若与 `docs/PROJECT_SPEC.md` 冲突，先改规范并记 ADR，
   而不是在代码里开例外。门禁会拦，不要试图绕过。
2. **棘轮只许变小**。行数、复杂度、测试数基线都只允许变严格。要放宽必须解释原因。
3. **信封不许发明字段**。任何 handler 返回的信封键集必须是 `ENVELOPE_FIELDS` 的子集。
   `ok=False` 时 `data` 必须为 `{}`。
4. **`0` 不是缺失**。缺失用 `NaN` 哨兵，UI 渲染 `—`。无成本模型时 `ec` 写 `null` 不是 `0`。
5. **组件内零硬编码色值/像素**。只用 `var(--wb-*)` 令牌；间距圆角只用 4px 基准的档位。
6. **测试里不许构造真实 `wmshare.Client`**。匿名免费档也会真实取数，会悄悄烧共享配额。
   一律用 `FakeFetcher`。
7. **不替用户判断**。任何面板、文案、示例都不得出现买卖结论、目标价、仓位建议。
8. **不复制对标物代码**。UI 参考仅限设计令牌数值（见 `docs/ADR/001`）。

## 新增接口前必查（最高优先级，与 wmshare 仓同源）

任何指标/序列/分位，动手算之前**必须先在 wmshare 目录里查「是否已有算好的」**：

```python
import wmshare
cat = wmshare.load()
cat.search("股息率")        # 指标码
cat.function("kline.bars")  # 目录函数签名
```

**自己从头重算 = 重复造轮子且口径必然漂移。**

## wmshare 门面的已知陷阱（都踩过）

| 陷阱 | 正确做法 |
|---|---|
| `index.keys()` 返回**单列 DataFrame（列名 `"0"`）**，不是 list | 用 `index.universe_keys()` 拿 `index.hs300` 这类可用键 |
| `index.trend(key, window)` **只接受单个 key** | 多键必须循环；驾驶舱只用 `index.valuation` 取当前值 |
| `screener.index_breadth_summary()` 返回**裸 dict，不是信封** | 别按信封解析 |
| `valuation.daily_basic()` 的 `data` 是**长表 `list[dict]`** | 不是 DataFrame，需自己透视 |
| `statements.*` 的 `vals` 是**嵌套 dict**，且**不可批量** | 客户端透视；逐票调用 |
| `dividend.rating()` 冷缓存返回 `ok=false` + `meta.error="COLD_CACHE"` | UI 提示「榜单未生成」，**不要重试** |
| `QuotaError` 是 `LimitError` 子类 | **先判 `QuotaError`** 再判 `LimitError`，否则会把终态当可重试 |
| 共享 client 的 `last_ec_cost` **无锁** | 用请求自带的 `meta.metering` 归因 |

## 原生批量（不要循环）

`kline.batch_live` · `kline.snapshot(list)` · `valuation.daily_basic_multi` ·
`dividend.diagnose(symbols)` · `dividend.calendar(codes=)` · `screener.query` · `moneyflow.board`

## 成本纪律

`EC_PER_ROW = (60, 75)`；`kline` 实测 ≈67 EC/行；重列选股 `40k–60k`，冷物化可达 `600k`；
`dividend.decomp` 实测 `501,577`（2 标的×3 年）。
耗时/昂贵的调用必须标 `Manual`：显式点击 + 二次确认 + **取消后零请求**。

## 提交信息

`type(scope): 中文描述`，type ∈ `feat` `fix` `refactor` `chore` `docs` `test` `perf`。
breaking 变更用 `!`。
