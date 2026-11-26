"""新鲜度判决：把 ``as_of`` 变成可展示的三档结论。

**为什么单独一层**：wmshare 的信封只给 ``as_of``（数据截至哪天），但「哪天」本身
不告诉用户「这算不算旧」。阈值在平台侧已有定义（``stats_config`` 的
``staleness_days`` / ``warn_days``），本模块把它翻译成 ``fresh/stale/expired``
与一句人话告警。

**为什么必须有 ``unknown``**：兄弟仓缺失或该数据集未登记时，我们没有真值。
此时**不能猜**——猜「新鲜」会让用户误信旧数据，猜「过期」会让正常数据看着像坏了。
诚实的答案是「新鲜度未知」。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

__all__ = ["Freshness", "VERDICTS", "judge", "describe_age"]

Freshness = str
#: 合法取值（与 ``core/envelope.FRESHNESS_VALUES`` 一致）。
VERDICTS: tuple[str, ...] = ("fresh", "stale", "expired", "unknown")


@dataclass(frozen=True)
class FreshnessVerdict:
    """新鲜度结论。"""

    freshness: str
    #: 期龄（天）；``as_of`` 不可解析时为 None
    age_days: int | None
    #: 面向用户的中文告警；``fresh`` 时为空
    warning: str
    #: 该数据集是否登记了阈值
    known: bool


def _parse(as_of: str | None) -> date | None:
    if not as_of:
        return None
    text = str(as_of).strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def describe_age(age_days: int) -> str:
    """把期龄说成人话。"""
    if age_days <= 0:
        return "当日"
    if age_days < 31:
        return f"{age_days} 天"
    if age_days < 365:
        return f"{age_days // 30} 个月"
    return f"{age_days / 365:.1f} 年"


def judge(
    as_of: str | None,
    *,
    stale_after_days: int | None = None,
    expire_after_days: int | None = None,
    label: str = "",
    today: date | None = None,
) -> FreshnessVerdict:
    """判决新鲜度。

    ``stale_after_days`` / ``expire_after_days`` 来自 ``stats_config`` 的
    ``warn_days`` / ``staleness_days``。任一为 ``None`` 即视为**真值不可用**，
    返回 ``unknown``——不猜。

    ``label`` 用于告警文案（如「资产负债表」），让用户知道是哪份数据旧了。
    """
    parsed = _parse(as_of)
    if parsed is None:
        return FreshnessVerdict(
            freshness="unknown", age_days=None,
            warning="数据截至日不可解析，无法判断新鲜度" if as_of else "",
            known=False)

    base = today or date.today()
    age = (base - parsed).days

    if stale_after_days is None and expire_after_days is None:
        return FreshnessVerdict(
            freshness="unknown", age_days=age,
            warning="该数据集未登记过期阈值，新鲜度未知", known=False)

    prefix = f"{label} " if label else "数据"
    expire = expire_after_days if expire_after_days is not None else stale_after_days
    warn = stale_after_days

    assert expire is not None  # 上面已排除 both None
    if age > expire:
        return FreshnessVerdict(
            freshness="expired", age_days=age, known=True,
            warning=f"{prefix}数据期龄 {age} 天（{describe_age(age)}），"
                    f"已超过过期阈值 {expire} 天")
    if warn is not None and age > warn:
        return FreshnessVerdict(
            freshness="stale", age_days=age, known=True,
            warning=f"{prefix}数据期龄 {age} 天（{describe_age(age)}），"
                    f"超过预警阈值 {warn} 天")
    return FreshnessVerdict(freshness="fresh", age_days=age, warning="", known=True)
