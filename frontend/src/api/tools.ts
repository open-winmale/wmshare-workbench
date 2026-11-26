/**
 * 工具清单与路由表（**唯一真源**，前端只在这里写工具名）。
 *
 * 后端 ``/api/tools`` 也返回同一份清单（含 ``ready``），但前端**不能在
 * 运行时才决定有哪些页面**——路由必须在构建期就存在，否则刷新后
 * 拿不到 chunk。因此这里的 slug 必须与后端 ``core/envelope.ENDPOINTS``
 * 对齐，由 ``tests/test_frontend_contract.py`` 校验。
 */

/** 工具 slug（= 后端端点 slug）。 */
export type ToolSlug =
  | 'dashboard'
  | 'assistant'
  | 'watchlist'
  | 'markets'
  | 'economics'
  | 'screener'
  | 'equity'
  | 'backtest'
  | 'portfolio'
  | 'sources'
  | 'ec_estimate'

export interface ToolDef {
  slug: ToolSlug
  title: string
  /** 侧栏分组 */
  group: '日常' | '研究' | '工具'
  /** 一句话说明（显示在页面标题下与侧栏 tooltip） */
  hint: string
}

/** 侧栏顺序 = 这个数组顺序（驾驶舱最前，因为它是打开就看的那一页）。 */
export const TOOLS: ToolDef[] = [
  { slug: 'dashboard', title: '驾驶舱', group: '日常', hint: '指数估值 · 涨跌宽度 · 资金流' },
  { slug: 'assistant', title: '助手', group: '日常', hint: 'AI 数据问答（可选，需自备模型 Key）' },
  { slug: 'watchlist', title: '自选', group: '日常', hint: '批量行情 · 名称与 5日/20日/量比' },
  { slug: 'markets', title: '行情', group: '日常', hint: '全市场宽度与涨跌榜' },
  { slug: 'equity', title: '个股研究', group: '研究', hint: '分区懒加载（三表/估值/分红）' },
  { slug: 'screener', title: '选股', group: '研究', hint: '条件选股 + 策略库' },
  { slug: 'economics', title: '宏观', group: '研究', hint: '宏观时序 · 国债曲线 · 汇率' },
  { slug: 'backtest', title: '回测', group: '研究', hint: '均线/估值买卖点' },
  { slug: 'portfolio', title: '持仓', group: '日常', hint: '五法账本 · 价格/汇率拆分' },
  { slug: 'sources', title: '数据源', group: '工具', hint: '119 个数据集新鲜度' },
  { slug: 'ec_estimate', title: 'EC 试算', group: '工具', hint: '花钱之前先算账' },
]

/** 默认首页。 */
export const DEFAULT_SLUG: ToolSlug = 'dashboard'

export function toolBySlug(slug: string): ToolDef | undefined {
  return TOOLS.find((t) => t.slug === slug)
}

/** 分组 → 工具（保持声明顺序）。 */
export function groupedTools(): { group: string; tools: ToolDef[] }[] {
  const order: string[] = []
  const buckets = new Map<string, ToolDef[]>()
  for (const tool of TOOLS) {
    if (!buckets.has(tool.group)) {
      buckets.set(tool.group, [])
      order.push(tool.group)
    }
    buckets.get(tool.group)!.push(tool)
  }
  return order.map((group) => ({ group, tools: buckets.get(group)! }))
}

/** 从 location.hash 解析当前 slug（`#/dashboard` → `dashboard`）。

 * 支持 hash 查询参数（`#/equity?sym=000001`）——查询段不参与 slug 解析；
 * 各视图自行取参（如 EquityView 读 `sym` 作为默认标的）。 */
export function readHash(): ToolSlug {
  const raw = window.location.hash
    .replace(/^#\/?/, '')
    .split('?')[0]
    .trim()
  return (toolBySlug(raw)?.slug ?? DEFAULT_SLUG) as ToolSlug
}
