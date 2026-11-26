"""五种批次法：同一个「卖了 100 股」，成本基础取决于挑哪一批。

**为什么必须五种都给**：这是券商/税务/自管的真实差异，不是可选花活。
同一份成交记录用 FIFO 与 LIFO 算出的已实现盈亏可以差出一个数量级
（长期持有 + 期间大幅波动时），用户拿哪个数去对账都对不上——除非
他能选。对标物给了五种，我们也给五种，并且**断言它们结果互不相同**。

| 方法 | 挑哪一批 | 典型用途 |
|---|---|---|
| ``FIFO`` | 最早买入 | 多数市场的默认税务口径 |
| ``LIFO`` | 最晚买入 | 短期波段对账 |
| ``HIFO`` | 成本最高 | 节税（highest-in-first-out） |
| ``AVERAGE`` | 不分批，移动加权平均 | A 股实务常用口径 |
| ``SPECIFIC`` | 成交里显式指定 ``lot_id`` | 逐笔指定（券商「指定持仓」） |

**本模块只算「结转了多少成本基础」，不算盈亏。** 价格/汇率拆分在
``positions.split_pnl`` 里统一做一次——两处各写一遍必然漂移，而这里的
数学恰恰是最容易被写错的部分（把卖出汇率用在价格分量上，汇率损益会恒为 0，
看起来却完全正常）。
"""

from __future__ import annotations

from dataclasses import dataclass

from .types import ABSENT, Lot, present

__all__ = [
    "BASIS_METHODS",
    "AverageCost",
    "Basis",
    "InsufficientShares",
    "consume",
    "consume_average",
]

#: 支持的五种批次法（顺序即 UI 下拉顺序）。
BASIS_METHODS: tuple[str, ...] = ("FIFO", "LIFO", "HIFO", "AVERAGE", "SPECIFIC")


class InsufficientShares(Exception):
    """卖出超过持仓。**必须抛**——静默按现有股数结转会掩盖录入错误。"""


@dataclass(frozen=True)
class Basis:
    """一段股数的成本基础。

    ``local_cost`` 是当地货币成本，``base_cost`` 是本币成本。两者都给，
    是因为盈亏拆分需要**买入时的汇率**：``avg_fx = base_cost / local_cost``。
    只留 ``base_cost`` 就丢掉了这个信息，拆分只能猜。

    缺汇率时 ``base_cost`` 为 ``ABSENT``，但 ``local_cost`` 仍然有效
    （成本基础本身不依赖汇率）。
    """

    shares: float
    local_cost: float
    base_cost: float | None
    #: 归到本段的买入费用（本币）
    fee: float = 0.0

    @property
    def avg_price(self) -> float | None:
        """买入均价（当地货币）。"""
        return ABSENT if self.shares <= 0 else self.local_cost / self.shares

    @property
    def avg_fx(self) -> float | None:
        """买入时的加权平均汇率。缺任一环即 ``ABSENT``。"""
        if self.base_cost is None or self.local_cost <= 0:
            return ABSENT
        return self.base_cost / self.local_cost

    def __add__(self, other: "Basis") -> "Basis":
        base = None
        if self.base_cost is not None and other.base_cost is not None:
            base = self.base_cost + other.base_cost
        return Basis(shares=self.shares + other.shares,
                     local_cost=self.local_cost + other.local_cost,
                     base_cost=base, fee=self.fee + other.fee)


def _pick(lots: list[Lot], method: str, lot_id: str) -> int:
    """挑出要消耗的批次下标。``AVERAGE`` 不走这里。"""
    if method == "FIFO":
        return 0
    if method == "LIFO":
        return len(lots) - 1
    if method == "HIFO":
        return _pick_highest_cost(lots)
    if method == "SPECIFIC":
        return _pick_by_id(lots, lot_id)
    raise ValueError(f"未知批次法：{method!r}；支持 {BASIS_METHODS}")


def _pick_highest_cost(lots: list[Lot]) -> int:
    """成本最高的那一批；同价按下标靠前（结果可重放）。"""
    best = 0
    for i, lot in enumerate(lots):
        cur, top = lot.cost(), lots[best].cost()
        if present(cur) and present(top) and (cur or 0) > (top or 0):
            best = i
    return best


def _pick_by_id(lots: list[Lot], lot_id: str) -> int:
    for i, lot in enumerate(lots):
        if lot.lot_id == lot_id:
            return i
    raise InsufficientShares(
        f"SPECIFIC 批次法未找到 lot_id={lot_id!r} 的持仓批次")


def _split_lot(lot: Lot, take: float) -> Basis:
    """从一批里切出 ``take`` 股的成本基础（费用按股数比例分摊）。"""
    ratio = 1.0 if lot.shares <= 0 else take / lot.shares
    local = lot.price * take
    base = None
    if lot.fx is not None:
        base = local * lot.fx
    return Basis(shares=take, local_cost=local, base_cost=base,
                 fee=lot.fee * ratio)


def consume(lots: list[Lot], shares: float, method: str,
            lot_id: str = "") -> Basis:
    """从 ``lots`` 里消耗 ``shares`` 股，返回合计成本基础。

    ``lots`` **就地修改**（剩余股数减少，整批耗尽则移除）。卖出超过持仓时抛
    ``InsufficientShares``——**不允许**「有多少卖多少」，那会把录入错误
    变成一个看起来正常的数字。
    """
    if method == "AVERAGE":
        raise ValueError("AVERAGE 请用 consume_average（它重算成本基础）")
    if method not in BASIS_METHODS:
        raise ValueError(f"未知批次法：{method!r}；支持 {BASIS_METHODS}")

    held = sum(lot.shares for lot in lots)
    if shares > held + 1e-9:
        raise InsufficientShares(
            f"卖出 {shares} 股超过持仓 {held} 股（批次法 {method}）")

    total = Basis(shares=0.0, local_cost=0.0, base_cost=0.0)
    remaining = shares
    while remaining > 1e-9 and lots:
        idx = _pick(lots, method, lot_id)
        lot = lots[idx]
        take = min(lot.shares, remaining)
        total = total + _split_lot(lot, take)
        if lot.shares - take <= 1e-9:
            lots.pop(idx)
        else:
            lots[idx] = Lot(lot_id=lot.lot_id, date=lot.date,
                           shares=lot.shares - take, price=lot.price,
                           fx=lot.fx,
                           fee=lot.fee * (1 - take / lot.shares))
        remaining -= take
    return total


@dataclass
class AverageCost:
    """``AVERAGE`` 的移动加权状态。

    与批次法的关键差别：卖出时**不挑批次**，按当前均价结转，并把剩余
    持仓的成本基础等比减少。因此同一只票的所有卖出单位成本相同。
    """

    shares: float = 0.0
    #: 当地货币成本合计
    local_cost: float = 0.0
    #: 本币成本合计；任一买入缺汇率则为 ``ABSENT``（不会「只算知道的那些」）
    base_cost: float | None = 0.0

    def buy(self, lot: Lot) -> None:
        """买入：成本累加。``lot.shares`` 为本批股数。"""
        self.shares += lot.shares
        self.local_cost += lot.price * lot.shares + lot.fee
        if self.base_cost is None or lot.fx is None:
            self.base_cost = None
        else:
            self.base_cost += (lot.price * lot.shares + lot.fee) * lot.fx

    def sell(self, shares: float) -> Basis:
        """卖出：按均价结转，剩余成本基础等比减少。"""
        if shares > self.shares + 1e-9:
            raise InsufficientShares(
                f"卖出 {shares} 股超过持仓 {self.shares} 股（AVERAGE）")
        ratio = 1.0 if self.shares <= 0 else shares / self.shares
        local = self.local_cost * ratio
        base = None if self.base_cost is None else self.base_cost * ratio
        self.shares -= shares
        self.local_cost -= local
        if self.base_cost is not None and base is not None:
            self.base_cost -= base
        return Basis(shares=shares, local_cost=local, base_cost=base)


def consume_average(state: AverageCost, shares: float) -> Basis:
    """``consume`` 的平均成本版本。"""
    return state.sell(shares)
