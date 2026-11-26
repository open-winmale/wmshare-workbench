"""持仓与估值：成本基础 → 市值 → 已实现/未实现，以及**唯一的盈亏拆分实现**。

拆分口径（全包只此一处，其它模块一律调用 ``split_pnl``）：

```
价格损益 = (卖出价 - 买入均价) × 买入加权汇率 × 股数
汇率损益 = (卖出汇率 - 买入加权汇率) × 卖出价 × 股数
gross    = 价格损益 + 汇率损益          ← 恒等式，可断言
net      = gross - 卖出费用 - 买入费用
```

**为什么价格分量要用「买入加权汇率」**：这样价格损益只反映价格变动，
汇率变动全部落进汇率分量，两者之和恰好等于「本币口径的总盈亏」。
如果用卖出汇率算价格分量，汇率损益会变成 ``(fx_sell - fx_buy) × 买入价``，
虽然总和仍对，但把汇率损益记到了价格上——对账时无法回答「这只票涨了多少、
汇率亏了多少」这个必答问题。

**缺汇率时全部 ``ABSENT``**：``total`` / ``price`` / ``fx`` 三项一起缺席。
不允许「只有价格部分算得出来就先给个价」——那会让用户在汇率未知时
看到一个假装完整的盈亏数字。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .basis import (
    BASIS_METHODS,
    AverageCost,
    Basis,
    InsufficientShares,
    consume,
)
from .types import ABSENT, Lot, Pnl, Trade, present

__all__ = [
    "Holding",
    "Fill",
    "PortfolioValuation",
    "Row",
    "build_holdings",
    "evaluate",
    "mark_to_market",
    "realized",
    "split_pnl",
    "unrealized",
]


def split_pnl(basis: Basis, shares: float, price: float,
              fx: float | None, fee: float = 0.0) -> Pnl:
    """把一笔卖出拆成价格/汇率两分量。

    ``basis`` 是 ``consume`` / ``consume_average`` 给出的成本基础。
    ``basis.base_cost`` 或 ``fx`` 任一为 ``ABSENT`` 时三项全缺失。
    """
    avg_price = basis.avg_price
    avg_fx = basis.avg_fx
    if basis.base_cost is None or avg_price is None or avg_fx is None or fx is None:
        return Pnl(total=ABSENT, price=ABSENT, fx=ABSENT, shares=shares, fee=fee)

    price_part = (price - avg_price) * avg_fx * shares
    fx_part = (fx - avg_fx) * price * shares
    gross = price_part + fx_part
    net = gross - fee - basis.fee
    return Pnl(total=net, price=price_part, fx=fx_part,
               shares=shares, fee=fee + basis.fee)


@dataclass
class Fill:
    """一笔已结算卖出的明细（供成交表展示与对账）。"""

    date: str
    code: str
    shares: float
    price: float
    fx: float | None
    pnl: Pnl
    method: str


@dataclass
class Holding:
    """单只标的的当前持仓状态。"""

    code: str
    method: str
    lots: list[Lot] = field(default_factory=list)
    average: AverageCost = field(default_factory=AverageCost)
    fills: list[Fill] = field(default_factory=list)

    @property
    def shares(self) -> float:
        if self.method == "AVERAGE":
            return self.average.shares
        return sum(lot.shares for lot in self.lots)

    @property
    def basis(self) -> Basis:
        """当前持仓的成本基础（未卖出部分）。"""
        if self.method == "AVERAGE":
            shares = self.average.shares
            local = self.average.local_cost
            return Basis(shares=shares, local_cost=local,
                         base_cost=self.average.base_cost)
        shares = sum(lot.shares for lot in self.lots)
        local = sum(lot.price * lot.shares for lot in self.lots)
        base = None
        if all(lot.fx is not None for lot in self.lots):
            base = sum((lot.price * lot.shares + lot.fee) * (lot.fx or 0)
                       for lot in self.lots)
        fee = sum(lot.fee for lot in self.lots)
        return Basis(shares=shares, local_cost=local, base_cost=base, fee=fee)

    @property
    def realized_total(self) -> float | None:
        """已实现盈亏合计；任一结算缺汇率则整体 ``ABSENT``。"""
        if not self.fills:
            return 0.0
        if any(f.pnl.total is None for f in self.fills):
            return ABSENT
        return sum(f.pnl.total or 0.0 for f in self.fills)


def build_holdings(trades: list[Trade], method: str = "FIFO") -> dict[str, Holding]:
    """按时间顺序回放成交，得到每只标的的持仓与已结算明细。

    成交必须**按日期升序**——乱序回放会让卖出找不到对应买入批次。
    因此这里显式检查并抛错，而不是偷偷排序（偷偷排序会掩盖数据源问题）。
    """
    if method not in BASIS_METHODS:
        raise ValueError(f"未知批次法：{method!r}；支持 {BASIS_METHODS}")

    dates = [t.date for t in trades]
    if dates != sorted(dates):
        raise ValueError("成交未按日期升序；请先排序（乱序回放会错配批次）")

    books: dict[str, Holding] = {}
    for trade in trades:
        hold = books.setdefault(trade.code, Holding(code=trade.code, method=method))
        if trade.side == "buy":
            _apply_buy(hold, method, trade)
        else:
            _apply_sell(hold, method, trade)
    return books


def _apply_buy(hold: Holding, method: str, trade: Trade) -> None:
    lot = Lot(lot_id=trade.lot_id or f"{trade.code}-{trade.date}-{trade.shares}",
              date=trade.date, shares=trade.shares, price=trade.price,
              fx=trade.fx, fee=trade.fee)
    if method == "AVERAGE":
        hold.average.buy(lot)
    else:
        hold.lots.append(lot)


def _apply_sell(hold: Holding, method: str, trade: Trade) -> None:
    if method == "AVERAGE":
        basis = hold.average.sell(trade.shares)
    else:
        basis = consume(hold.lots, trade.shares, method, trade.lot_id)
    pnl = split_pnl(basis, trade.shares, trade.price, trade.fx, trade.fee)
    hold.fills.append(Fill(date=trade.date, code=trade.code, shares=trade.shares,
                           price=trade.price, fx=trade.fx, pnl=pnl,
                           method=method))


def realized(hold: Holding) -> Pnl:
    """已实现盈亏汇总（三项分别求和；任一缺值则该项 ``ABSENT``）。"""
    if not hold.fills:
        return Pnl(total=0.0, price=0.0, fx=0.0)
    shares = sum(f.shares for f in hold.fills)
    fee = sum(f.pnl.fee for f in hold.fills)

    def _sum(attr: str) -> float | None:
        vals = [getattr(f.pnl, attr) for f in hold.fills]
        if any(v is None for v in vals):
            return ABSENT
        return sum(v or 0.0 for v in vals)

    return Pnl(total=_sum("total"), price=_sum("price"), fx=_sum("fx"),
               shares=shares, fee=fee)


def unrealized(hold: Holding, price: float | None,
               fx: float | None) -> Pnl:
    """未实现盈亏（用当前 ``price``/``fx`` 对剩余持仓定价）。

    缺价或缺汇率 → 三项 ``ABSENT``。持仓为 0 时返回全 0（不是 ``ABSENT``：
    「没有持仓」的盈亏确实是零，这是算出来的）。
    """
    shares = hold.shares
    if shares <= 0:
        return Pnl(total=0.0, price=0.0, fx=0.0)
    basis = hold.basis
    if price is None:
        return Pnl(total=ABSENT, price=ABSENT, fx=ABSENT, shares=shares)
    return split_pnl(basis, shares, price, fx)


@dataclass
class Row:
    """一行持仓估值（供表格渲染）。"""

    code: str
    shares: float
    avg_price: float | None
    price: float | None
    fx: float | None
    cost: float | None
    value: float | None
    unrealized: Pnl
    realized: Pnl


@dataclass
class PortfolioValuation:
    """组合估值结果。

    ``valued`` / ``total`` 是「有价行数 / 总行数」——**合计只覆盖有价部分**，
    并且必须把这个事实显示出来（``valued < total`` 时不能把合计当全量)。
    """

    method: str
    rows: list[Row] = field(default_factory=list)
    #: 有价的市值合计（本币）；一行都没价时为 ``ABSENT``
    value: float | None = None
    #: 有价的成本合计
    cost: float | None = None
    realized_total: float | None = None
    unrealized_total: float | None = None
    valued: int = 0
    total: int = 0

    @property
    def complete(self) -> bool:
        """是否所有持仓都有价（合计可直接当全量用）。"""
        return self.total > 0 and self.valued == self.total


@dataclass
class _Totals:
    """合计累加器（把「部分合计」的事实显式带在类型里）。"""

    value: float = 0.0
    cost: float = 0.0
    unrealized: float = 0.0
    realized: float = 0.0
    any_value: bool = False
    any_cost: bool = False
    unrealized_known: bool = True
    realized_known: bool = True
    valued: int = 0
    total: int = 0

    def add_valuation(self, value: float | None, cost: float | None,
                      unr: Pnl, rl: Pnl) -> None:
        if value is not None:
            self.value += value
            self.any_value = True
            self.valued += 1
        if cost is not None:
            self.cost += cost
            self.any_cost = True
        self.total += 1
        self._fold("unrealized", unr)
        self._fold("realized", rl)

    def _fold(self, field_name: str, pnl: Pnl) -> None:
        if pnl.total is None:
            setattr(self, f"{field_name}_known", False)
            return
        setattr(self, field_name,
                getattr(self, field_name) + pnl.total)


def _row_for(hold: Holding, price: float | None,
             rate: float | None) -> tuple[Row, float | None, float | None]:
    """构造一行 + 返回值/成本（``None`` 表示该行缺价或缺汇率）。"""
    shares = hold.shares
    basis = hold.basis
    value = None
    if price is not None and rate is not None:
        value = price * shares * rate
    return (
        Row(code=hold.code, shares=shares, avg_price=basis.avg_price,
            price=price, fx=rate, cost=basis.base_cost, value=value,
            unrealized=unrealized(hold, price, rate), realized=realized(hold)),
        value, basis.base_cost)


def mark_to_market(build: dict[str, Holding], prices: dict[str, float | None],
                   fx: dict[str, float | None] | None = None,
                   method: str = "FIFO") -> PortfolioValuation:
    """给每个持仓定价并汇总。

    ``prices`` / ``fx`` 缺某只票 → 该行 ``value=ABSENT``，**不计入合计**，
    且 ``valued < total``。绝不把缺价当 0——那会让组合市值凭空少一只票，
    而用户看到的合计数字看起来完全正常。
    """
    fx_map = fx or {}
    out = PortfolioValuation(method=method)
    acc = _Totals()
    for code, hold in sorted(build.items()):
        # 已实现盈亏**先结算**：清仓标的没有行，但它的已实现盈亏必须计入
        # 组合合计。上一版在 shares<=0 时直接 continue，导致「卖光了」的
        # 标的已实现盈亏凭空消失——总额对不上，却找不到是哪只票丢了。
        rl = realized(hold)
        if hold.shares > 0:
            row, value, cost = _row_for(hold, prices.get(code),
                                        fx_map.get(code, 1.0))
            out.rows.append(row)
            acc.add_valuation(value, cost, row.unrealized, rl)
        elif rl.total is not None:
            acc.realized += rl.total
        else:
            acc.realized_known = False

    out.value = acc.value if acc.any_value else ABSENT
    out.cost = acc.cost if acc.any_cost else ABSENT
    out.unrealized_total = acc.unrealized if acc.unrealized_known else ABSENT
    out.realized_total = acc.realized if acc.realized_known else ABSENT
    out.valued = acc.valued
    out.total = acc.total
    return out


def evaluate(trades: list[Trade], prices: dict[str, float | None],
             fx: dict[str, float | None] | None = None,
             method: str = "FIFO") -> PortfolioValuation:
    """``build_holdings`` + ``mark_to_market`` 的便捷组合。"""
    return mark_to_market(build_holdings(trades, method), prices, fx, method)


def check_shares(hold: Holding) -> None:
    """断言持仓非负（供外部在录入后自检）。"""
    if hold.shares < -1e-9:
        raise InsufficientShares(f"{hold.code} 持仓为负：{hold.shares}")


def describe(valuation: PortfolioValuation) -> str:
    """一行中文摘要（供日志与页脚）。"""
    parts = [f"{valuation.method} 持仓 {valuation.valued}/{valuation.total} 有价"]
    if present(valuation.value):
        parts.append(f"市值 {valuation.value:,.0f}")
    if not valuation.complete:
        parts.append("合计不完整（部分标的缺价或缺汇率）")
    return " · ".join(parts)
