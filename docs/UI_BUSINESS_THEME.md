# UI 商务风改造提案（文档，不含代码）

> **状态：P0 已落地（2026-11-27）；P1/P2 未做。** P0 已改 token、顶栏/侧栏/
> PanelShell、字体栈、基础控件、默认亮色与持久化；DataTable 吸顶/密度、KPI/chips、
> 图表色板 CSS 变量化、CVD 亮色细节与视觉回归仍在 P1/P2。
>
> 对标背景见维护者本地的对标复评笔记（私有，不入库）；令牌来源见
> [ADR-002](ADR/002-self-defined-business-theme.md)。

## 1. 结论先行

当前 UI 不像「企业工作台」，主要不是颜色不够多，而是**终端化**：

- 纯黑背景 + 琥珀强调色 + 高饱和 12 色图表；
- 全站等宽字体（连中文正文、按钮、标题都是 mono）；
- 2–6px 小圆角、单层扁平卡片、全仓没有阴影；
- 大量 999px 彩色胶囊（模式、状态、as-of、EC）；
- ASCII 字形当图标（`▚` / `☰`）；
- 骨架屏 shimmer + ECharts 默认入场动画。

商务风要反过来：**浅灰底 + 白卡 + 蓝色主色 + 中文无衬线正文 + 数字等宽 +
8–12px 圆角 + 轻阴影 + 更少的彩色标签 + 统一图标**。默认亮色，暗色保留但
改为深蓝灰，不再用纯黑。

## 2. 现状诊断（带证据）

| # | demo 感来源 | 证据 | 影响 |
|---|---|---|---|
| 1 | 纯黑 `#000000` + 琥珀 `#f5a623` 终端配色 | `frontend/src/styles/tokens.css:14-41` | 像盯盘终端/开发者 demo，不像企业应用 |
| 2 | 全站 mono：body、按钮、输入、表格、标题同一字体族 | `tokens.css:58,171-179`；`styles/controls.css:17-18,40,58,70` | 中文走 monospace fallback；层级只靠字号 |
| 3 | 高密度小字号：168px 侧栏、16px 内容内边距、11–12px 标签 | `components/layout/AppNav.vue:29`；`App.vue:133-137`；`DataTable.vue:62,69` | 信息塞满、留白少，强化「原型」观感 |
| 4 | 大量 999px 彩色胶囊：模式/状态/as-of/EC | `AppTopbar.vue:113-152`；`StatusBadge.vue`；`PanelShell.vue:77-82`；`controls.css:109-116` | 标签化、颜色噪声高 |
| 5 | 单层扁平卡片，全仓 0 处 `box-shadow` | `PanelShell.vue:38-46` | 没有 elevation，层级只靠 1px 边框 |
| 6 | ASCII 图标 `▚` / `☰` | `AppTopbar.vue:36-68` | 缺图标系统，像原型 |
| 7 | 骨架屏 shimmer + Line/Bar 默认入场动画 | `LoadingSkeleton.vue:20-39`；`LineChart.vue`/`BarChart.vue` 未设 `animation:false` | 最容易产生「SaaS demo」既视感 |
| 8 | 设计系统承诺未实现 | `DESIGN_SYSTEM.md` §7（12 列栅格）、§4（表头吸顶）、§10（density）；`--wb-bg-inset` 未定义；`chart-theme.ts:13-21` 硬编码暗色盘 | 文档比实现精致，进一步强化「demo」 |

**不是问题的地方**（保留）：A 股红涨绿跌、数字等宽/tabular-nums、12 色
CVD 相邻对校验、五态规范、`prefers-reduced-motion`、焦点环。

## 3. 目标风格（企业级商务风）

> 参照企业协同/办公软件的通用商务语言（用户口语称「钉钉商务风」）。
> **只借风格原则，不复制钉钉的资产、代码、图标或品牌色值**；所有数值由
> 本项目自定，并作为新契约登记（见 §7）。

| 原则 | 具体做法 |
|---|---|
| 清晰优先 | 浅灰页面底 + 白色内容卡；标题/正文/辅助文字三级层次 |
| 蓝色主色 | 主操作、选中态、链接用蓝色；涨跌仍用红/绿，不让主色抢语义 |
| 中文无衬线 | UI 正文用系统无衬线（PingFang SC / Microsoft YaHei / Noto Sans CJK） |
| 数字等宽 | 数字、价格、代码、表格数值列用 mono + `tabular-nums` |
| 适度圆角 | 卡片 8–12px、控件 4–6px；胶囊只留给状态标签，且降饱和 |
| 轻阴影 | 白卡 `0 1px 2px rgba(...,.04)` + `0 2px 8px rgba(...,.04)`；不堆重阴影 |
| 密度分层 | 顶栏 56px、侧栏 220px、内容 20–24px；正文 14px、表格 13px |
| 动效克制 | 关闭 ECharts 默认入场；骨架改静态浅灰或 1.2s 低对比 shimmer |
| 可访问 | 正文对比度 ≥4.5:1；颜色不是唯一信息载体；`reduced-motion` 保留 |

## 4. Token 映射（提案值，非最终）

### 4.1 颜色（亮色默认）

| 令牌 | 现状（Obsidian/Daylight） | 提案（Business Light） | 说明 |
|---|---|---|---|
| `--wb-bg-base` | `#000000` / `#f4f4f4` | `#f5f7fa` | 页面底：浅蓝灰 |
| `--wb-bg-surface` | `#0b0b0b` / `#fdfdfd` | `#ffffff` | 卡片/面板 |
| `--wb-bg-raised` | `#161616` / `#eaeaea` | `#f2f3f5` | 次级块/表头 |
| `--wb-bg-hover` | `#222222` / `#dedede` | `#eef0f3` | 悬停 |
| `--wb-border-dim` | `#262626` / `#dcdcdc` | `#e5e6eb` | 分隔线 |
| `--wb-border-med` | `#3a3a3a` / `#c4c4c4` | `#c9cdd4` | 控件边框 |
| `--wb-border-bright` | `#525252` / `#8f8f8f` | `#86909c` | 强调边框 |
| `--wb-text-primary` | `#e8e8e8` / `#141414` | `#1d2129` | 标题/主文 |
| `--wb-text-secondary` | `#b7b7b7` / `#4a4a4a` | `#4e5969` | 正文 |
| `--wb-text-tertiary` | `#8c8c8c` / `#616161` | `#6b7280` | 辅助 |
| `--wb-text-dim` | `#767676` / `#6e6e6e` | `#6e7681` | 弱化（对比度 ≥4.5） |
| `--wb-accent` | `#f5a623` / `#a84c08` | `#2563eb` | 商务蓝（自定，不是钉钉品牌色） |
| `--wb-accent-bg` | `#2a1f0a` / `#fdf0e3` | `#e8f0fe` | 选中底 |
| `--wb-warning` | `#f2c94c` / `#8f5f00` | `#b45309` | 警示（深琥珀） |
| `--wb-info` | `#5b9dff` / `#1b55d9` | `#2563eb` | 信息=主色 |
| `--wb-up` | `#ff5d5d` / `#c62430` | `#d93026` | A 股红涨（保留语义） |
| `--wb-down` | `#2fd07a` / `#0b7a43` | `#0b7a43` | A 股绿跌（保留语义） |
| `--wb-row-alt` | `#0f0f0f` / `#f2f2f2` | `#fafbfc` | 斑马纹 |
| `--wb-seq-low/high` | 暗底→琥珀 | `#f2f3f5` → `#2563eb` | 热力低→高 |

暗色（Business Dark，替代 Obsidian）：底 `#0f1419`、面 `#171c24`、浮层
`#1f2630`、悬停 `#2a3340`、边框 `#2b333d`、主文 `#e6e8eb`、次文 `#b4bac3`、
主色 `#4d8dff`、涨跌 `#ff6b6b`/`#35c77a`。**不再是纯黑。**

CVD 变体沿用现有语义（蓝/橙替代红/绿），只换 `--wb-up/--wb-down` 与
序列色，不改组件。

### 4.2 字体

```css
--wb-font-sans: -apple-system, BlinkMacSystemFont, "PingFang SC",
                "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC",
                sans-serif;
--wb-font-mono: "JetBrains Mono", "SF Mono", Consolas, monospace;
```

- body / 标题 / 按钮 / 表单：`--wb-font-sans`
- 数字、价格、代码、表格数值列：`--wb-font-mono` + `tabular-nums`
- 字号：11/12/13/14/16/20/28（保留），正文 14px，表格 13px
- 行高：正文 1.5，数字 1.2

### 4.3 圆角、阴影、密度

| 令牌 | 现状 | 提案 |
|---|---|---|
| `--wb-r-1..5` | 2/4/6/8/999 | 4/6/8/12/999（卡片 8–12，控件 4–6，胶囊只给状态） |
| `--wb-shadow-1` | 无 | `0 1px 2px rgba(29,33,41,.04), 0 2px 8px rgba(29,33,41,.04)` |
| `--wb-shadow-2` | 无 | `0 4px 16px rgba(29,33,41,.08)`（浮层/下拉） |
| 顶栏高度 | ~49px | 56px |
| 侧栏宽度 | 168px | 220px |
| 内容内边距 | 16px | 20–24px |
| 表格行高 | 紧凑 | comfortable 40px / compact 32px |

## 5. 组件改造清单

| 组件 | 现状 | 改造 | 优先级 |
|---|---|---|---|
| `AppTopbar` | 深色条 + 文字按钮 + ASCII mark | 56px 白底；品牌（内联 SVG/简单方块）+ 环境徽标 + 搜索入口 + 主题/设置；按钮用图标+文字 | P0 |
| `AppNav` | 168px 纯文字 | 220px；分组标题、图标+文字、选中蓝底圆角 6px；移动端抽屉 | P0 |
| `PanelShell` | 1px 边框 + 6px 圆角 + 无阴影 | 白卡、8–12px 圆角、`--wb-shadow-1`、头部标题 20px/副标题 13px、动作区右对齐 | P0 |
| `KpiStrip` | 无卡片、底部分隔线 | 标签 12px 次级、数值 24px semibold、涨跌带箭头+色；>5 项按均衡拆行（保留 P5-03） | P1 |
| `DataTable` | 12px、表头 raised、无吸顶/密度 | 表头浅灰吸顶、13px、行悬停、数值右对齐 mono、`density` prop；分页优先于无限滚动 | P1 |
| 按钮 | raised 深底、2px 圆角 | primary 蓝实心 / secondary 白底描边 / ghost 文字；高 32–36px、圆角 6px | P1 |
| 输入/下拉 | 2px 圆角、mono | sans、6px 圆角、focus 蓝边；错误态红边+文案 | P1 |
| chips/badges | 多色 999px 胶囊 | 中性灰底 + 语义色 dot；只保留 3–4 种状态色 | P1 |
| `StateBlock` | 居中、amber/red 标题 | 中性图标 + 标题 + 原因 + 动作；empty 不用大插图 | P1 |
| `LoadingSkeleton` | 1.4s shimmer | 静态浅灰块或 1.2s 低对比 shimmer（尊重 reduced-motion） | P1 |
| 图表 | 透明底、默认动画、硬编码盘 | 关闭默认动画；网格线浅灰；tooltip 白卡；系列色读 CSS 变量 | P1 |
| 主题 | 默认暗色、不持久 | 默认亮色；`prefs.ts` 持久化；暗色改 Business Dark | P0 |
| 图标 | ASCII `▚/☰` | 内联 SVG（零依赖，不引图标包） | P2 |

## 6. 页面级落点（11 页）

| 页面 | 重点 |
|---|---|
| 驾驶舱 | 三指数卡/宽度/双榜改白卡；KPI 层级；页面 20–24px 留白 |
| 助手 | 聊天气泡白底、来源 chip 中性化、输入条白卡；阶段胶囊降饱和 |
| 自选 / 行情 | 表格优先：吸顶表头、行悬停、数值右对齐 |
| 个股研究 | 分区页签用 Segmented；概览/KPI 卡、图表白卡 |
| 选股 | 表达式卡 + 结果卡分离；示例/已存策略用次级按钮 |
| 宏观 | 三个白卡（指标/曲线/汇率）；日期 chip 中性 |
| 回测 | 参数卡 + 结果卡；K 线/净值图关闭默认动画 |
| 持仓 | 成交表 + 汇总卡；五法对比表吸顶 |
| 数据源 | 状态表 + KPI；"问题项"筛选用 Segmented |
| EC 试算 | 表单卡 + 成本结果卡 |
| 全局 | 顶栏/侧栏/页脚统一；页脚保持免责声明 |

## 7. 法务与来源（重要）

- 现行 token 的**色值、字体族、12 色图表盘**是 FinceptTerminal（AGPL-3.0）
  公开源码的数值移植，见 [ADR-001](ADR/001-adopt-peer-design-tokens.md)、
  `LICENSE`、`README.md`。
- 本提案若落地，等于**换掉移植色彩与字体**，需要：
  1. 新增 ADR-002「自定商务主题」，记录新 token 由本项目独立确定；
  2. 更新 `LICENSE` / `README.md` / `DESIGN_SYSTEM.md` / `tokens.css` 头部的
     来源说明；
  3. 图表 12 色盘可暂时保留（已过 CVD 相邻对校验）；若替换，必须重新做
     色盲可辨性校验并更新 `quality/baselines/tokens.json`。
- **钉钉只作风格参照**：不复制其图标、字体文件、品牌色精确值、组件代码或
  文案。公开文档用「企业级商务风 / 企业协同软件常见做法」描述。
- 不新增前端运行时依赖；图标用内联 SVG。

## 8. 优先级与工作量（估算）

| 批次 | 内容 | 估算 | 验收 |
|---|---|---|---|
| P0 ✅ | tokens + 顶栏/导航 + PanelShell + 默认亮色/持久化 + 字体栈 + 基础控件 | 1–2 天 | `make check`；亮色下 3 页目视 |
| P1 | DataTable 吸顶/density、KPI/chips、StateBlock/Skeleton、图表读 CSS 变量 | 2–3 天 | 11 页亮色截图；对比度检查 |
| P2 | 图表亮色适配、视觉回归基线、内联 SVG 图标 | 约 2 天 | 双主题 + CVD + reduced-motion |
| 后续 | 12 列栅格、命令面板、跨页联动 | 另开批次 | 与 `DEBT` D-19/D-20 合并 |

## 9. 验收清单（落地时用）

> **P0 已核（2026-11-27）**：默认亮色/持久化、正文对比度（亮暗均 ≥4.5）、
> CVD 亮色背景、无新增依赖；DataTable 密度/视觉基线/图标系统待 P1/P2。

- [ ] `make check` 全绿（`check_tokens` 无裸色值；新 shadow/字体令牌入基线）
- [ ] 亮色/暗色各 11 页截图（视觉回归基线，见 D-12）
- [ ] 正文对比度 ≥4.5:1（双主题）
- [ ] 涨跌同时有符号与颜色（不能只靠颜色）
- [ ] `prefers-reduced-motion` 下无动画
- [ ] CVD 变体可辨
- [ ] 无新增运行时依赖
- [ ] 顶栏/侧栏/卡片/表格在 1280/1680/2400 三档断点不溢出

## 10. 明确不做（本提案范围）

- 不重做信息架构（仍 11 页，不加 docking/54 屏）
- 不引入 UI 组件库或图标包（零依赖约束）
- 不改数据口径、信封、EC 逻辑
- 不在本轮改任何样式代码
