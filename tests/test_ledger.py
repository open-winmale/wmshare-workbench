"""账本内核离线测试：五法 / 拆分 / 缺失语义 / TWR / VaR。

这些用例的定位是**抓数学错**，不是提高覆盖率。每条对应一个真实的
算错方式（见各 test 的 docstring），因为账本错一个方向就会让用户
拿错数去对账，而结果看起来完全正常。
"""

from __future__ import annotations

import pytest
from workbench.client.ledger import (
    ABSENT,
    InsufficientShares,
    Lot,
    Trade,
    build_holdings,
    consume,
    realized,
    split_pnl,
    twr,
    twr_from_nav,
    unrealized,
    var,
)
from workbench.client.ledger.basis import AverageCost
from workbench.client.ledger.performance import CashFlow
from workbench.client.ledger.positions import evaluate, mark_to_market


def _trades() -> list[Trade]:
    """三笔买入 + 一笔卖出，价差足够大以区分五种方法。"""
    return [
        Trade(date="2024-01-02", code="600519", side="buy", shares=100, price=10.0),
        Trade(date="2024-02-02", code="600519", side="buy", shares=100, price=20.0),
        Trade(date="2024-03-02", code="600519", side="buy", shares=100, price=30.0),
        Trade(date="2024-04-02", code="600519", side="sell", shares=100, price=40.0),
    ]


class TestFiveMethods:
    def test_five_methods_differ(self):
        """同一份成交，四种批次法（AVERAGE 单列）已实现盈亏必须互不相同。

        如果某个方法的实现退化成「永远取第一批」，这个用例会红——
        而只测单一方法的用例不会发现。
        """
        totals = {}
        # SPECIFIC 需要显式 lot_id，由 test_specific_* 单独覆盖；
        # 这里比的是「同一份成交、四种自动挑批法」的差异。
        for method in ("FIFO", "LIFO", "HIFO", "AVERAGE"):
            val = evaluate(_trades(), {"600519": 40.0}, method=method)
            totals[method] = round(val.realized_total or 0.0, 6)
        # FIFO 结转 10 元 → 赚 30*100；LIFO 结转 30 元 → 赚 10*100
        assert totals["FIFO"] == pytest.approx(3000.0)
        assert totals["LIFO"] == pytest.approx(1000.0)
        assert totals["AVERAGE"] == pytest.approx(2000.0)   # 均价 20 → 赚 20*100
        assert totals["FIFO"] != totals["LIFO"]
        assert totals["FIFO"] != totals["AVERAGE"]

    def test_hifo_picks_highest_cost(self):
        """HIFO 挑成本最高的那批（30 元），所以赚得最少。"""
        val = evaluate(_trades(), {"600519": 40.0}, method="HIFO")
        assert val.realized_total == pytest.approx(1000.0)

    def test_specific_requires_lot_id(self):
        """SPECIFIC 未指定 lot_id 必须抛错，不许默默挑一批。"""
        trades = [
            Trade(date="2024-01-02", code="A", side="buy", shares=100, price=10.0,
                  lot_id="L1"),
            Trade(date="2024-02-02", code="A", side="sell", shares=100, price=20.0),
        ]
        with pytest.raises(InsufficientShares):
            build_holdings(trades, "SPECIFIC")

    def test_specific_uses_named_lot(self):
        trades = [
            Trade(date="2024-01-02", code="A", side="buy", shares=100, price=10.0,
                  lot_id="L1"),
            Trade(date="2024-02-02", code="A", side="buy", shares=100, price=30.0,
                  lot_id="L2"),
            Trade(date="2024-03-02", code="A", side="sell", shares=100, price=40.0,
                  lot_id="L2"),
        ]
        val = evaluate(trades, {"A": 40.0}, method="SPECIFIC")
        assert val.realized_total == pytest.approx(1000.0)

    def test_sell_more_than_held_raises(self):
        """卖超必须抛错——静默按现有股数结转会掩盖录入错误。"""
        with pytest.raises(InsufficientShares):
            build_holdings([
                Trade(date="2024-01-02", code="A", side="buy", shares=100, price=10.0),
                Trade(date="2024-02-02", code="A", side="sell", shares=150, price=20.0),
            ], "FIFO")

    def test_out_of_order_trades_rejected(self):
        """乱序成交必须抛错，不许偷偷排序（排序会掩盖数据源问题）。"""
        with pytest.raises(ValueError, match="升序"):
            build_holdings([
                Trade(date="2024-02-02", code="A", side="buy", shares=100, price=10.0),
                Trade(date="2024-01-02", code="A", side="buy", shares=100, price=20.0),
            ])

    def test_average_cost_moves_with_buys(self):
        """平均成本法：买入后均价变化，卖出按当时均价结转。"""
        state = AverageCost()
        state.buy(Lot(lot_id="a", date="2024-01-02", shares=100, price=10.0))
        state.buy(Lot(lot_id="b", date="2024-02-02", shares=100, price=20.0))
        basis = state.sell(100)
        assert basis.avg_price == pytest.approx(15.0)
        assert basis.local_cost == pytest.approx(1500.0)
        assert state.shares == pytest.approx(100.0)
        assert state.local_cost == pytest.approx(1500.0)

    def test_fifo_consume_partial_lot(self):
        """部分消耗：剩余股数与费用按比例保留。"""
        lots = [Lot(lot_id="a", date="2024-01-02", shares=100, price=10.0, fee=10.0)]
        basis = consume(lots, 40, "FIFO")
        assert basis.shares == pytest.approx(40.0)
        assert basis.local_cost == pytest.approx(400.0)
        assert basis.fee == pytest.approx(4.0)
        assert lots[0].shares == pytest.approx(60.0)
        assert lots[0].fee == pytest.approx(6.0)


class TestPnlSplit:
    def test_price_fx_split_sums(self):
        """价格分量 + 汇率分量 == 总盈亏（恒等式，容差 1e-9）。"""
        basis = consume(
            [Lot(lot_id="a", date="2024-01-02", shares=100, price=10.0, fx=7.0)],
            100, "FIFO")
        pnl = split_pnl(basis, 100, price=12.0, fx=6.5)
        assert pnl.price == pytest.approx((12.0 - 10.0) * 7.0 * 100)
        assert pnl.fx == pytest.approx((6.5 - 7.0) * 12.0 * 100)
        assert pnl.total == pytest.approx(pnl.price + pnl.fx, abs=1e-9)

    def test_fx_split_isolates_currency_move(self):
        """价格不动、只有汇率跌 → 价格分量为 0，全部亏损进汇率分量。

        这是最容易写错的一处：若用卖出汇率算价格分量，价格分量会是
        ``(12-10)*6.5*100``，把汇率损失算进了「价格上涨赚的钱」。
        """
        basis = consume(
            [Lot(lot_id="a", date="2024-01-02", shares=100, price=12.0, fx=7.0)],
            100, "FIFO")
        pnl = split_pnl(basis, 100, price=12.0, fx=6.5)
        assert pnl.price == pytest.approx(0.0, abs=1e-9)
        assert pnl.fx == pytest.approx(-0.5 * 12.0 * 100)
        assert pnl.total < 0

    def test_missing_fx_never_one(self):
        """缺汇率 → 三项全 ``ABSENT``，绝不用 1.0 顶替。"""
        basis = consume(
            [Lot(lot_id="a", date="2024-01-02", shares=100, price=10.0, fx=None)],
            100, "FIFO")
        pnl = split_pnl(basis, 100, price=12.0, fx=6.5)
        assert pnl.total is ABSENT
        assert pnl.price is ABSENT
        assert pnl.fx is ABSENT

    def test_missing_sell_fx_also_absent(self):
        """卖出侧缺汇率同样三项缺失。"""
        basis = consume(
            [Lot(lot_id="a", date="2024-01-02", shares=100, price=10.0, fx=7.0)],
            100, "FIFO")
        pnl = split_pnl(basis, 100, price=12.0, fx=None)
        assert pnl.total is ABSENT

    def test_fees_reduce_total_not_price(self):
        """费用只扣总额，不进价格分量（费用不是「价格变动」）。"""
        basis = consume(
            [Lot(lot_id="a", date="2024-01-02", shares=100, price=10.0, fx=1.0)],
            100, "FIFO")
        pnl = split_pnl(basis, 100, price=12.0, fx=1.0, fee=5.0)
        assert pnl.price == pytest.approx(200.0)
        assert pnl.total == pytest.approx(195.0)


class TestAbsentNotZero:
    def test_absent_is_not_zero(self):
        """缺价 → 该行市值 ``ABSENT``，且不计入合计（合计 ≠ 把缺价当 0）。"""
        val = evaluate(_trades(), {"600519": None}, method="FIFO")
        assert val.rows[0].value is ABSENT
        # 唯一一行没价 → 合计根本没有可加的数，应为 ABSENT 而非 0
        assert val.value is ABSENT
        assert val.valued == 0
        assert val.total == 1
        assert val.complete is False

    def test_total_marks_partial(self):
        """有价与缺价混合时，合计只覆盖有价部分且 ``valued < total``。"""
        trades = [
            Trade(date="2024-01-02", code="A", side="buy", shares=100, price=10.0),
            Trade(date="2024-01-02", code="B", side="buy", shares=100, price=20.0),
        ]
        val = evaluate(trades, {"A": 15.0, "B": None}, method="FIFO")
        assert val.valued == 1
        assert val.total == 2
        assert val.complete is False
        assert val.value == pytest.approx(1500.0)   # 只含 A

    def test_zero_position_realized_is_zero_not_absent(self):
        """没有卖出时已实现盈亏是**算出来的 0**，不是缺失。"""
        trades = [Trade(date="2024-01-02", code="A", side="buy", shares=100, price=10.0)]
        hold = build_holdings(trades, "FIFO")["A"]
        rl = realized(hold)
        assert rl.total == 0.0

    def test_unrealized_needs_price(self):
        hold = build_holdings(_trades(), "FIFO")["600519"]
        assert unrealized(hold, None, 1.0).total is ABSENT
        assert unrealized(hold, 50.0, None).total is ABSENT
        assert unrealized(hold, 50.0, 1.0).total is not ABSENT


class TestRealizedUnrealized:
    def test_realized_unrealized(self):
        """已实现 + 未实现 = 全周期盈亏（同一价格口径下）。"""
        trades = _trades()
        val = evaluate(trades, {"600519": 40.0}, method="FIFO")
        row = val.rows[0]
        assert row.shares == pytest.approx(200.0)
        # 剩余两批成本 20 + 30 = 50 元/股，均价 25；现价 40 → 未实现 15*200
        assert row.unrealized.total == pytest.approx(3000.0)
        assert row.realized.total == pytest.approx(3000.0)

    def test_holdings_basis_after_partial_sell(self):
        trades = _trades()
        hold = build_holdings(trades, "FIFO")["600519"]
        assert hold.shares == pytest.approx(200.0)
        assert hold.basis.avg_price == pytest.approx(25.0)


class TestTwr:
    def test_twr_ignores_deposit(self):
        """纯入金不产生收益：市值从 100 涨到 200 但当天入金 100 → 收益 0。"""
        nav = [("2024-01-01", 100.0), ("2024-01-02", 200.0)]
        res = twr_from_nav(nav, [CashFlow(date="2024-01-02", amount=100.0)])
        assert res.total == pytest.approx(0.0, abs=1e-9)
        assert res.periods == 1

    def test_twr_counts_real_gain(self):
        """真涨 10% 计 10%（无出入金）。"""
        nav = [("2024-01-01", 100.0), ("2024-01-02", 110.0)]
        res = twr_from_nav(nav)
        assert res.total == pytest.approx(0.10)

    def test_twr_chains_periods(self):
        """多区间连乘：+10% 后 +10% → +21%（不是 +20%）。"""
        nav = [("2024-01-01", 100.0), ("2024-01-02", 110.0),
               ("2024-01-03", 121.0)]
        res = twr_from_nav(nav)
        assert res.total == pytest.approx(0.21, abs=1e-9)
        assert res.periods == 2

    def test_twr_insufficient_data_is_absent(self):
        """不足 2 个点 → ``ABSENT``，不给 0（0 会被读成持平）。"""
        res = twr_from_nav([("2024-01-01", 100.0)])
        assert res.total is ABSENT
        assert "不足" in res.note

    def test_twr_no_annualize_short_window(self):
        """窗口 < 30 天不做年化（短期年化会显著夸大）。"""
        nav = [("2024-01-01", 100.0), ("2024-01-05", 110.0)]
        res = twr_from_nav(nav)
        assert res.annualized is ABSENT
        assert "不做年化" in res.note

    def test_twr_annualizes_long_window(self):
        nav = [("2024-01-01", 100.0), ("2025-01-01", 110.0)]
        res = twr_from_nav(nav)
        assert res.annualized is not None
        assert res.annualized == pytest.approx(0.10, abs=0.01)

    def test_twr_alias(self):
        assert twr([("2024-01-01", 100.0), ("2024-01-02", 101.0)]).total is not None


class TestVar:
    def test_var_historical(self):
        """历史模拟：20 个样本取最差那一个（95% 尾部 = 1/20）。"""
        rets = [-0.05, -0.02, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05,
                0.06, 0.07, 0.08, 0.09, 0.10, 0.11, 0.12, 0.13,
                0.14, 0.15, 0.16, 0.17]
        res = var(rets, confidence=0.95)
        assert res.used == 20
        assert res.var is not None
        assert res.var == pytest.approx(0.05)   # 最差那个点

    def test_var_converges_inward_with_more_samples(self):
        """样本翻倍到 40 时才取第二差（约 5% 分位，不是永远取最差）。"""
        rets = [-0.20, -0.05] + [i / 100 for i in range(38)]
        res = var(rets, confidence=0.95)
        assert res.used == 40
        assert res.var == pytest.approx(0.05)

    def test_var_skips_none_without_filling_zero(self):
        """缺失样本跳过但不补 0——补 0 会把波动率压低、低估风险。"""
        with_none = var([-0.10, None, 0.01], confidence=0.95)
        without = var([-0.10, 0.01], confidence=0.95)
        assert with_none.used == without.used == 2
        assert with_none.var == pytest.approx(without.var or 0)

    def test_var_empty_is_absent(self):
        res = var([], confidence=0.95)
        assert res.var is ABSENT
        assert "无样本" in res.method

    def test_var_all_positive_is_zero_loss(self):
        """全部样本为正 → 该置信度下无亏损，VaR 为 0（不是负）。"""
        res = var([0.01, 0.02, 0.03], confidence=0.95)
        assert res.var == 0.0

    def test_var_rejects_bad_confidence(self):
        with pytest.raises(ValueError):
            var([0.01], confidence=1.5)


class TestMarkToMarket:
    def test_empty_portfolio(self):
        val = mark_to_market({}, {}, method="FIFO")
        assert val.total == 0
        assert val.complete is False
        assert val.value is ABSENT

    def test_zero_share_holdings_skipped(self):
        """全部卖出后持仓为 0 的标的不出现在估值表里。"""
        trades = [
            Trade(date="2024-01-02", code="A", side="buy", shares=100, price=10.0),
            Trade(date="2024-02-02", code="A", side="sell", shares=100, price=20.0),
        ]
        val = evaluate(trades, {"A": 20.0}, method="FIFO")
        assert val.rows == []
        assert val.realized_total == pytest.approx(1000.0)

    def test_fx_applied_to_value(self):
        """外币持仓市值按汇率折算为本币。"""
        trades = [Trade(date="2024-01-02", code="AAPL", side="buy", shares=10,
                        price=100.0, fx=7.0)]
        val = evaluate(trades, {"AAPL": 110.0}, fx={"AAPL": 6.9}, method="FIFO")
        assert val.value == pytest.approx(110.0 * 10 * 6.9)
