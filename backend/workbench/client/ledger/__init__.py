"""组合账本：批次法、盈亏拆分、TWR、VaR。**纯计算，零 I/O。**

这一层是「部分复刻」里最容易被糊弄的地方——随便算个 `(卖价-买价)*股数`
也能出个数，但那个数在三种情况下是错的：

1. **混了外币**：价格涨了但汇率跌了，用一个汇率乘回去会把汇率损益算进价格损益；
2. **缺汇率**：拿 ``1.0`` 顶替会凭空造出一个「汇率没动」的假结论；
3. **缺价格**：把缺失当 0 计入合计，会把组合市值算少一整只票。

所以本包的三个核心类型都显式承载「不知道」：

- ``ABSENT``（即 ``None``）：**缺失**，不是 0，也不是空；
- ``Pnl.total / price / fx`` 三者要么全有值，要么全为 ``ABSENT``；
- ``mark_to_market`` 返回 ``valued`` 与 ``total`` 两个计数，合计只覆盖有价的部分。

模块分工：

| 模块 | 内容 |
|---|---|
| ``types`` | ``Lot`` / ``Trade`` / ``Pnl`` / ``ABSENT`` |
| ``basis`` | 五种批次法：FIFO / LIFO / HIFO / AVERAGE / SPECIFIC |
| ``positions`` | 成本→市值、已实现/未实现、价格与汇率拆分 |
| ``performance`` | TWR（时间加权，切分现金流）、历史模拟 VaR |
"""

from __future__ import annotations

from .basis import BASIS_METHODS, InsufficientShares, consume
from .performance import twr, twr_from_nav, var
from .positions import (
    Holding,
    PortfolioValuation,
    build_holdings,
    mark_to_market,
    realized,
    split_pnl,
    unrealized,
)
from .types import ABSENT, Lot, Pnl, Trade, is_absent

__all__ = [
    "ABSENT",
    "BASIS_METHODS",
    "Holding",
    "InsufficientShares",
    "Lot",
    "Pnl",
    "PortfolioValuation",
    "Trade",
    "build_holdings",
    "consume",
    "is_absent",
    "mark_to_market",
    "realized",
    "split_pnl",
    "twr",
    "twr_from_nav",
    "unrealized",
    "var",
]
