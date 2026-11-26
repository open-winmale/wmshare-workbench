"""组合绩效：TWR（时间加权收益）与 VaR（历史模拟）。

**为什么不用「期末市值 / 期初市值 - 1」**：那个数在有任何出入金时都是错的。
用户月中追加 10 万，收益会被算成「赚了 10 万」。TWR 通过在每个现金流节点
切分区间、只连乘区间内收益，把入金的影响剔干净——这是基金行业的标准口径，
也是唯一能让「我这个月的操作水平」和「我这个月的运气」分开的算法。

**VaR 用历史模拟法而不是正态假设**：A 股收益分布尖峰厚尾，正态假设会
系统性低估尾部风险。历史模拟只需要「我有 N 天历史」，不需要假设分布形状。
代价是它只能反映历史出现过的极端情形——这个局限必须写在返回的
``method`` 里，让用户知道自己拿到的是哪种数。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .types import ABSENT

__all__ = [
    "CashFlow",
    "TwrResult",
    "VarResult",
    "twr",
    "twr_from_nav",
    "var",
]


@dataclass(frozen=True)
class CashFlow:
    """一笔出入金。``amount`` 为正表示入金（增加持仓），负为出金。

    **必须在发生当天**登记——TWR 的切分点就是它。
    """

    date: str
    amount: float


@dataclass(frozen=True)
class TwrResult:
    """时间加权收益结果。"""

    #: 累计 TWR（小数，0.12 = +12%）；数据不足时为 ``ABSENT``
    total: float | None
    #: 年化（按实际天数折算）；不足 30 天时为 ``ABSENT``（年化短期数据是误导）
    annualized: float | None
    #: 参与连乘的区间数
    periods: int
    #: 未参与计算的区间（缺净值）
    skipped: int
    note: str = ""


def twr_from_nav(nav_points: list[tuple[str, float]],
                 flows: list[CashFlow] | None = None) -> TwrResult:
    """从净值序列算 TWR。

    ``nav_points`` 是 ``(date, nav)``，按日期升序。``nav`` 为**组合总市值**
    （含现金），``flows`` 是期间的出入金。

    **算法**：在每个出入金日把区间切开。区间内收益 = ``(期末 - 期初 - 区间内净流入)
    / 期初``。然后 ``∏(1 + r_i) - 1``。

    这个式子的关键点：出入金后的市值变化不算进收益。若某天入金 10 万且市值
    正好涨 10 万，剔除入金后收益为 0——这才是「操作水平」的正确度量。

    数据不足（< 2 个点）时返回 ``total=ABSENT``，**不给 0**：0 会被读成
    「持平」，而真相是「算不出来」。
    """
    if len(nav_points) < 2:
        return TwrResult(total=ABSENT, annualized=ABSENT, periods=0,
                         skipped=0, note="净值点不足 2 个，无法计算")

    flow_map: dict[str, float] = {}
    for f in flows or []:
        flow_map[f.date] = flow_map.get(f.date, 0.0) + f.amount

    product = 1.0
    periods = 0
    skipped = 0
    started = False
    for i in range(1, len(nav_points)):
        prev_date, prev_nav = nav_points[i - 1]
        date_i, nav_i = nav_points[i]
        if prev_nav <= 0:
            skipped += 1
            continue
        # 出入金按「发生在区间起点」处理：本区间净流入只加在分子
        inflow = flow_map.get(date_i, 0.0)
        ret = (nav_i - prev_nav - inflow) / prev_nav
        product *= (1.0 + ret)
        periods += 1
        started = True

    if not started:
        return TwrResult(total=ABSENT, annualized=ABSENT, periods=0,
                         skipped=skipped, note="全部区间因期初净值为 0 被跳过")

    total = product - 1.0
    days = _days_between(nav_points[0][0], nav_points[-1][0])
    annual = ABSENT
    note = ""
    if days is not None and days >= 30:
        annual = (1.0 + total) ** (365.0 / days) - 1.0
    elif days is not None:
        note = f"区间仅 {days} 天，不做年化（短期年化会显著夸大）"
    else:
        note = "日期不可解析，不做年化"
    return TwrResult(total=total, annualized=annual, periods=periods,
                     skipped=skipped, note=note)


def twr(nav_points: list[tuple[str, float]],
        flows: list[CashFlow] | None = None) -> TwrResult:
    """``twr_from_nav`` 的别名（对外主入口）。"""
    return twr_from_nav(nav_points, flows)


def _days_between(start: str, end: str) -> int | None:
    from datetime import date, datetime

    def _p(text: str) -> date | None:
        for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(str(text)[:10], fmt).date()
            except ValueError:
                continue
        return None

    a, b = _p(start), _p(end)
    if a is None or b is None:
        return None
    return max(0, (b - a).days)


@dataclass(frozen=True)
class VarResult:
    """在险价值结果。"""

    #: 该置信度下的损失分位（正数表示亏损占净值的比例，0.03 = 亏 3%）
    var: float | None
    #: 置信度（0.95 = 95%）
    confidence: float
    #: 样本数与实际用于计算的样本数
    samples: int
    used: int
    #: 计算方法说明（必须如实告知，历史模拟不等于正态假设）
    method: str = "historical"


def var(returns: list[float | None], confidence: float = 0.95) -> VarResult:
    """历史模拟法 VaR。

    ``returns`` 是逐期收益率序列（小数），``None`` 表示该期缺失——
    **跳过但不补 0**：补 0 会把波动率压低，系统性低估风险。

    ``used < samples`` 时调用方应把样本不足的事实展示出来：用 20 个点算出的
    95% VaR 在统计上几乎没有意义，但把它显示成一个精确数字是误导。
    """
    if not 0.5 < confidence < 1.0:
        raise ValueError(f"confidence 需在 (0.5, 1)，收到 {confidence!r}")
    clean = sorted(r for r in returns if r is not None)
    if not clean:
        return VarResult(var=ABSENT, confidence=confidence,
                         samples=len(returns), used=0,
                         method="historical（无样本）")
    worst = clean[_tail_index(len(clean), confidence)]
    return VarResult(var=max(0.0, -worst), confidence=confidence,
                     samples=len(returns), used=len(clean),
                     method=f"historical（{len(clean)} 个样本经验分位）")


def _tail_index(n: int, confidence: float) -> int:
    """尾部起始下标（升序样本上）。

    用 ``ceil((1-c)·n) - 1`` 而非 ``floor``，理由是它给出一个可复核的锚点：
    **当样本数恰好等于 ``1/(1-c)`` 时，取到的就是最差的那一个观测**。
    例：置信度 95% 时，20 个样本 → 下标 0（最差）；40 个样本 → 下标 1
    （第二差，即约 5% 分位）。样本更多时才逐步向内收敛。

    用 ``floor`` 会让 20 个样本取到下标 1（第二差）——**在有 20 个样本、
    要估 5% 尾部时，把最差的一天排除在风险之外是危险的方向**。

    **必须扣掉浮点误差**：``(1.0 - 0.95) * 20`` 在二进制里是
    ``1.0000000000000009``，直接 ``ceil`` 得 2，于是 20 个样本取到了第二差。
    这个错误只在某些 ``(n, confidence)`` 组合下出现，肉眼读代码完全看不出来。
    """
    tail = round((1.0 - confidence) * n, 9)      # 先抹掉累积误差
    idx = math.ceil(tail) - 1
    return min(n - 1, max(0, idx))
