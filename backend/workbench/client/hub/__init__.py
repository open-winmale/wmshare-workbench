"""数据面：``policy`` / ``backoff`` / ``freshness`` / ``hub``。

工作台**唯一**的缓存层（``PROJECT_SPEC`` §4：不许有第二层）。
"""

from __future__ import annotations

from .backoff import RetryDecision, classify, delay_for_attempt, jittered
from .freshness import FreshnessVerdict, judge
from .hub import DataHub, Entry
from .policy import STRATEGIES, TopicPolicy, load_staleness_table, policy_for

__all__ = [
    "DataHub",
    "Entry",
    "FreshnessVerdict",
    "RetryDecision",
    "STRATEGIES",
    "TopicPolicy",
    "classify",
    "delay_for_attempt",
    "jittered",
    "judge",
    "load_staleness_table",
    "policy_for",
]
