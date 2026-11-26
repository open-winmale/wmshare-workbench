/**
 * 选股结果的指标码 → 中文列名。
 *
 * 单独成模块：这是**纯展示映射**，会随指标码增长而增长，但它与页面的
 * 交互逻辑无关。留在 `.vue` 里会让页面文件因数据表膨胀而超限。
 *
 * 未登记的原样显示——**不猜含义**（猜错的中文名比原始码更有害）。
 */

export const COLUMN_LABELS: Record<string, string> = {
  symbol: '代码',
  name: '名称',
  $PE_TTM: 'PE(TTM)',
  $PB: 'PB',
  $PS: 'PS',
  $PR: 'PR',
  $ABOVE_MA20: '站上 MA20',
  $ID_BONUS_RATE_TTM: '股息率(TTM)',
  $ROIC_10Y_MIN_LAST: 'ROIC 10年最低',
  $NPM_10Y_MIN_LAST: '净利率 10年最低',
  $CF_NP_RATIO_LAST: '现金流/净利',
  $GW_RATE_LAST: '商誉/净资产',
  $IBD_RATE_LAST: '有息负债率',
  $IS_ST: 'ST',
  $IS_BANK: '银行',
}

/** 小数比率 → 百分数展示（0.188 → 18.88%）。 */
export const PERCENT_COLUMNS = new Set([
  '$ROIC_10Y_MIN_LAST',
  '$NPM_10Y_MIN_LAST',
  '$GW_RATE_LAST',
  '$IBD_RATE_LAST',
])

/** 布尔标志 → 是/否（不要显示 true/false）。 */
export const BOOL_COLUMNS = new Set(['$IS_ST', '$IS_BANK'])
