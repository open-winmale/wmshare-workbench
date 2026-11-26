"""账本基础类型。

**``ABSENT`` 为什么是 ``None`` 而不是 ``NaN``**：项目内部算术最喜欢 ``NaN``
（``NaN != NaN`` 天然不会被误比作 0），但信封要序列化成 JSON，而
``json.dumps(float('nan'))`` 会产出裸 ``NaN`` 字面量——**不是合法 JSON**，
前端 ``JSON.parse`` 直接抛。前端拿不到数，比拿到 ``null`` 糟得多。

因此本包用 ``None`` 作为「缺失」的唯一表示，并靠三个约定防止它被当成 0：

1. 任何聚合函数遇到 ``ABSENT`` 就返回 ``ABSENT``（不跳过、不求平均）；
2. 需要「部分合计」的地方显式返回 ``(值, 覆盖数, 总数)`` 三元组；
3. 类型标注一律 ``float | None``，让「可能是 None」在阅读时就可见。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["ABSENT", "Lot", "Trade", "Pnl", "is_absent", "present"]

#: 「缺失」的唯一表示。**不是 0**：0 是「算出来是零」，缺失是「没算出来」。
ABSENT: None = None


def is_absent(value: Any) -> bool:
    """是否缺失。显式函数而非 ``value is None``，让调用点自解释。"""
    return value is None


def present(value: float | None) -> bool:
    """是否有值（``is_absent`` 的反面，避免双重否定读起来费劲）。"""
    return value is not None


@dataclass(frozen=True)
class Lot:
    """一个买入批次。

    ``price`` 与 ``fx`` 都是**每股**口径：``price * shares`` 是当地货币成本，
    乘 ``fx`` 才是本币成本。``fx`` 为 ``ABSENT`` 表示汇率未知——此时任何
    跨币种损益都是 ``ABSENT``，而不是「按 1.0 算」。
    """

    #: 批次标识（``SPECIFIC`` 批次法按它指定消耗哪一个）
    lot_id: str
    date: str
    shares: float
    price: float
    #: 当地货币 → 本币汇率；本币标的为 1.0；未知为 ABSENT
    fx: float | None = 1.0
    #: 归到本批次的买入费用（本币）
    fee: float = 0.0

    def cost(self, shares: float | None = None) -> float | None:
        """本币成本（含按比例分摊的买入费用）。缺汇率时返回 ``ABSENT``。"""
        if self.fx is None:
            return ABSENT
        n = self.shares if shares is None else shares
        ratio = 1.0 if self.shares <= 0 else n / self.shares
        return self.price * n * self.fx + self.fee * ratio


@dataclass(frozen=True)
class Trade:
    """一笔成交。``side`` 只认 ``buy`` / ``sell``（不建模做空开平仓）。"""

    date: str
    code: str
    side: str
    shares: float
    price: float
    fx: float | None = 1.0
    fee: float = 0.0
    #: ``SPECIFIC`` 批次法下卖出时指定消耗的买入批次
    lot_id: str = ""

    def __post_init__(self) -> None:
        if self.side not in ("buy", "sell"):
            raise ValueError(f"side 只支持 buy/sell，收到 {self.side!r}")
        if self.shares <= 0:
            raise ValueError(f"shares 必须为正，收到 {self.shares!r}")
        if self.price < 0:
            raise ValueError(f"price 不能为负，收到 {self.price!r}")


@dataclass(frozen=True)
class Pnl:
    """盈亏，**三项要么全有值、要么全缺失**。

    拆分公式的唯一实现是 ``positions.split_pnl``——这里不重复写，
    因为公式写在两个地方必然漂移，而漂移出来的第二份看起来同样合理。

    缺任一端汇率时三项都为 ``ABSENT``——**绝不拿 1.0 顶替**：顶替会
    让「汇率未知」看起来像「汇率没动」，这个错误无法从结果反推出来。
    """

    total: float | None
    price: float | None
    fx: float | None
    #: 参与计算的股数（便于对账时核「拆了多少股」）
    shares: float = 0.0
    #: 卖出费用（本币，已从 ``total`` 扣除）
    fee: float = 0.0

    @property
    def known(self) -> bool:
        return self.total is not None
