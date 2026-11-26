# ADR-002：采用自定商务主题，仅保留图表调色板与等宽字体族的数值移植

- 状态：已采纳（2026-11-27）
- 关系：部分取代 [ADR-001](001-adopt-peer-design-tokens.md) 的视觉令牌范围
- 相关：[DESIGN_SYSTEM.md](../DESIGN_SYSTEM.md)、[UI_BUSINESS_THEME.md](../UI_BUSINESS_THEME.md)

## 背景

ADR-001 决定只取对标物 `FinceptTerminal`（AGPL-3.0）公开源码里的数值型设计
参数（色值、字体族、12 色图表盘）。这套令牌把界面定成了「纯黑 + 琥珀 + 全站
等宽」的终端风：对盯盘终端是合理的，对「个人投研工作台」则 demo 感过强，
不像企业应用。2026-11-27 的整体功能复评确认：UI 是四类主要差距之一。

用户明确要求把界面改为「钉钉式商务风」。钉钉是**风格参照**，不是代码/资产
来源；本项目也不会复制其图标、字体文件、品牌色精确值、组件代码或文案。

## 决策

1. **语义色自定**：`bg-*`、`border-*`、`text-*`、`accent`、`warning`、`info`、
   `up`、`down` 以及相应背景色，全部由本项目独立确定（Business Light / Business
   Dark 两套），不再声称是 ADR-001 的移植值。
2. **字体栈自定**：新增 `--wb-font-sans`（PingFang SC / Microsoft YaHei /
   Noto Sans CJK）用于 UI 正文与标题；`--wb-font-mono`（JetBrains Mono /
   Consolas）继续用于数字、代码、表达式。等宽字体族的**数值**仍来自 ADR-001。
3. **阴影/布局/圆角自定**：新增 `--wb-shadow-1/2`、`--wb-topbar-h`、
   `--wb-nav-w`、`--wb-content-pad`；圆角重映射为 4/6/8/12/999。
4. **12 色图表盘保留**：`--wb-chart-1..12` 的顺序与数值不变（已过 CVD 相邻
   对校验），仍属 ADR-001 的移植范围。若未来替换，必须重新做色盲校验并更新
   `quality/baselines/tokens.json` 与 `tests/test_frontend_contract.py`。
5. **默认亮色**：`index.html` 初始 `data-theme="daylight"`，暗色保留为
   Business Dark；主题/CVD 选择经 `composables/prefs.ts` 持久化。

## 后果

- `LICENSE` / `README.md` / `DESIGN_SYSTEM.md` / `tokens.css` 头部的来源说明
  必须同步：语义色/UI 字体栈/阴影为自定；12 色图表盘与等宽字体族仍是数值移植。
- `quality/baselines/tokens.json` 的 `origin` 同步：颜色与新增令牌标「自定」，
  `chart-1..12`、`font-mono` 标「移植」。
- 组件内部仍只允许 `var(--wb-*)`；阴影只写在 `tokens.css`（`check_tokens`
  禁止其他文件出现 `rgba()`）。
- 不新增运行时依赖；图标用内联 SVG / `currentColor`。
- 若未来引入新的第三方设计参考，必须另立 ADR，不得把其代码/资产直接搬入。

## 被否方案

- **继续用 ADR-001 终端色**：用户已明确观感不符，且「个人工作台」不是终端。
- **逐值复制钉钉品牌色/组件**：风格可参照，品牌资产与代码不可复制；也违反
  本仓「不复制对标物代码/资产」的既有纪律。
- **只换色不换字体**：亮色底 + 全站等宽仍是半成品，故 P0 一并落字体栈与
  基础控件。
