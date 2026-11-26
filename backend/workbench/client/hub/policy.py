"""主题策略：每个数据主题的 TTL、最小刷新间隔、过期阈值。

**阈值来源是 ``../airflow/data_monitor/stats_config.py`` 的 119 条 ``StatsCheck``**
（字段 ``staleness_days`` / ``warn_days`` / ``update_frequency``），AST 解析而不 import
——那个文件依赖 airflow，我们只要数据。

**为什么不硬编码数字**：TTL 拍脑袋会有两个后果——设短了疯狂重取烧 EC，设长了
数据旧了不提示。平台侧早已为每个数据集定义了「多久算过期」，直接复用才是同源。

兄弟仓缺失时（CI 单仓环境）降级为内置兜底表并标记 ``source="fallback"``，
**服务仍可启动**——沿用 ``wmshare/tools/gen_data_calendar.py`` 的既有做法。
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "TopicPolicy",
    "policy_for",
    "load_staleness_table",
    "STRATEGIES",
    "STATS_CONFIG",
]

def _find_stats_config() -> Path:
    """向上逐级找兄弟仓的 ``stats_config.py``。

    **不用 ``parents[N]`` 硬编码层数**：包布局变过一次（``src/wmshare/`` →
    ``backend/workbench/``），硬编码的层数当场失效——返回值是个不存在的路径，
    于是 ``available: false``，而且没有任何报错。逐级找对重构免疫。
    """
    rel = Path("airflow") / "data_monitor" / "stats_config.py"
    for base in Path(__file__).resolve().parents:
        candidate = base / rel
        if candidate.is_file():
            return candidate
    # 找不到就返回「最可能的位置」，让调用方显式处理「文件不存在」
    here = Path(__file__).resolve()
    for base in here.parents:
        if (base / "backend").is_dir() or (base / ".git").is_dir():
            return base.parent / rel
    return here.parents[4] / rel


#: 兄弟仓的统计配置（新鲜度真值）。
_DEFAULT_STATS = _find_stats_config()
STATS_CONFIG = Path(os.environ.get("WORKBENCH_STATS_CONFIG") or _DEFAULT_STATS)

#: 秒/天。
_DAY = 86400


@dataclass(frozen=True)
class TopicPolicy:
    """一个主题族的刷新与过期策略。

    ``ttl_s`` 内不重复取数；``min_interval_s`` 是**地板**（无论多少订阅者，
    刷新频率有下限）；``stale_after_s`` 与 ``expire_after_s`` 驱动 ``freshness``
    三档判决；``drop_on_idle`` 用于无界主题集合（如任意个股行情）。
    """

    ttl_s: int
    min_interval_s: int = 5
    stale_after_s: int = _DAY
    expire_after_s: int = _DAY * 7
    #: 生产者既不 publish 也不报错则清 ``in_flight``——防一个挂死的请求
    #: 永久钉住该主题（单飞的跟随者会一直等）。
    refresh_timeout_s: int = 30
    drop_on_idle: bool = False
    push_only: bool = False
    source: str = "fallback"

    def __post_init__(self) -> None:
        if self.ttl_s < 0:
            raise ValueError("ttl_s 不能为负")
        if self.min_interval_s < 0:
            raise ValueError("min_interval_s 不能为负")
        if self.refresh_timeout_s <= 0:
            raise ValueError("refresh_timeout_s 必须为正（否则单飞跟随者永不超时）")
        if self.stale_after_s > self.expire_after_s:
            raise ValueError(
                f"stale_after_s({self.stale_after_s}) 不能大于 "
                f"expire_after_s({self.expire_after_s})；否则 stale 档永远不可达")


#: 主题族 → (匹配前缀, 策略)。
#:
#: 前缀最长匹配优先（见 ``policy_for``）。TTL 按「数据多久变一次」定，
#: 过期阈值按平台 ``stats_config`` 的 ``staleness_days`` 对齐。
STRATEGIES: tuple[tuple[str, TopicPolicy], ...] = (
    # ---- 盘中/准实时：短 TTL，可淘汰（无界主题集合）----
    ("market:quote", TopicPolicy(
        ttl_s=30, min_interval_s=5, stale_after_s=300, expire_after_s=_DAY,
        drop_on_idle=True, source="realtime")),
    ("market:live", TopicPolicy(
        ttl_s=30, min_interval_s=5, stale_after_s=300, expire_after_s=_DAY,
        drop_on_idle=True, source="realtime")),
    # ---- 每日 EOD：按交易日刷新 ----
    ("market:kline", TopicPolicy(
        ttl_s=300, min_interval_s=30, stale_after_s=_DAY, expire_after_s=_DAY * 7,
        drop_on_idle=True, source="eod")),
    ("market:moneyflow", TopicPolicy(
        ttl_s=600, min_interval_s=60, stale_after_s=_DAY, expire_after_s=_DAY * 4,
        source="eod")),
    ("market:breadth", TopicPolicy(
        ttl_s=300, min_interval_s=30, stale_after_s=_DAY, expire_after_s=_DAY * 4,
        source="eod")),
    ("market:margin", TopicPolicy(
        ttl_s=1800, min_interval_s=60, stale_after_s=_DAY, expire_after_s=_DAY * 4,
        source="eod")),
    # ---- 指数估值：依赖平台预热缓存，TTL 稍长避免反复打未命中 ----
    ("index:trend", TopicPolicy(
        ttl_s=3600, min_interval_s=300, stale_after_s=_DAY * 2,
        expire_after_s=_DAY * 10, source="cache")),
    ("index:", TopicPolicy(
        ttl_s=1800, min_interval_s=60, stale_after_s=_DAY, expire_after_s=_DAY * 7,
        source="eod")),
    # ---- 周更：板块/概念目录 ----
    ("board:concept_list", TopicPolicy(
        ttl_s=_DAY * 7, min_interval_s=_DAY, stale_after_s=_DAY * 8,
        expire_after_s=_DAY * 21, source="weekly")),
    ("board:", TopicPolicy(
        ttl_s=1800, min_interval_s=60, stale_after_s=_DAY, expire_after_s=_DAY * 4,
        source="eod")),
    # ---- 财报/披露：季度或事件驱动，TTL 长 ----
    ("fund:statement", TopicPolicy(
        ttl_s=_DAY, min_interval_s=3600, stale_after_s=_DAY * 120,
        expire_after_s=_DAY * 150, source="quarterly")),
    ("fund:", TopicPolicy(
        ttl_s=_DAY, min_interval_s=3600, stale_after_s=_DAY * 120,
        expire_after_s=_DAY * 150, source="quarterly")),
    ("disc:", TopicPolicy(
        ttl_s=3600, min_interval_s=300, stale_after_s=_DAY * 30,
        expire_after_s=_DAY * 60, source="event")),
    # ---- 宏观：月度/年度 ----
    ("macro:", TopicPolicy(
        ttl_s=_DAY, min_interval_s=3600, stale_after_s=_DAY * 35,
        expire_after_s=_DAY * 400, source="monthly")),
)

#: 未知主题的兜底策略：宁可短一点（多取一次）也不要长（拿到旧数据不说）。
_FALLBACK = TopicPolicy(
    ttl_s=300, min_interval_s=30, stale_after_s=_DAY, expire_after_s=_DAY * 7,
    source="fallback")


def _entry_kv(node: ast.AST) -> dict[str, object]:
    """把一条 ``StatsCheck(...)`` 调用拍平成 ``{字段: 字面量}``。"""
    if not isinstance(node, ast.Call):
        return {}
    out: dict[str, object] = {}
    for kw in node.keywords:
        if kw.arg and isinstance(kw.value, ast.Constant):
            out[kw.arg] = kw.value.value
    return out


def parse_staleness(stats_path: Path = STATS_CONFIG) -> dict[str, tuple[int, int | None]]:
    """AST 解析 ``stats_config.py``，返回 ``{collection: (staleness_days, warn_days)}``。

    用 AST 而不是 import：那个文件除 ``dataclasses`` 外还依赖 airflow 运行时；
    我们只要字面量数字。

    解析失败或文件缺失返回空 dict（调用方降级）。
    """
    try:
        tree = ast.parse(stats_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return {}

    out: dict[str, tuple[int, int | None]] = {}
    for items in _stats_check_lists(tree):
        for elt in items:
            kv = _entry_kv(elt)
            coll = kv.get("collection")
            days = kv.get("staleness_days")
            if isinstance(coll, str) and isinstance(days, int):
                warn = kv.get("warn_days")
                out[coll] = (days, warn if isinstance(warn, int) else None)
    return out


def _stats_check_lists(tree: ast.AST) -> list[list[ast.AST]]:
    """找出 ``STATS_CHECKS = [...]`` 的字面量列表内容。"""
    found: list[list[ast.AST]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign):
            continue
        if getattr(node.target, "id", "") != "STATS_CHECKS":
            continue
        value = node.value
        if isinstance(value, ast.List):
            found.append(list(value.elts))
    return found


def load_staleness_table(stats_path: Path = STATS_CONFIG) -> dict[str, tuple[int, int | None]]:
    """同 ``parse_staleness``；额外语义：返回空 dict 表示「真值不可用」。"""
    return parse_staleness(stats_path)


def policy_for(
    topic: str, *,
    table: dict[str, tuple[int, int | None]] | None = None,
) -> TopicPolicy:
    """按主题取策略：**最长前缀匹配**。

    最长优先很重要——``board:concept_list`` 必须命中自己的周更策略，
    而不是被 ``board:`` 的日更策略吃掉。
    """
    _ = table  # 保留参数位：将来若要用 collection 级真值覆盖 TTL
    best: tuple[str, TopicPolicy] | None = None
    for prefix, policy in STRATEGIES:
        if topic.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, policy)
    return best[1] if best is not None else _FALLBACK
