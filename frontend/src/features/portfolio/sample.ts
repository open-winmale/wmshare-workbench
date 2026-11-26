/**
 * 账本示例成交（**演示数据，不是建议持仓**）。
 *
 * 单独成模块而不是写在 `.vue` 的 `<script setup>` 里：后者不允许
 * `export const`（SFC 编译器会报错，且 typecheck 不覆盖这类错误）。
 */

export const DEFAULT_TRADES = `[
  {"date": "2025-01-02", "code": "600519", "side": "buy", "shares": 100, "price": 1288.4},
  {"date": "2025-03-02", "code": "600519", "side": "buy", "shares": 100, "price": 1435.2},
  {"date": "2025-06-02", "code": "600519", "side": "sell", "shares": 100, "price": 1502.0},
  {"date": "2025-02-02", "code": "000001", "side": "buy", "shares": 1000, "price": 10.5}
]`
