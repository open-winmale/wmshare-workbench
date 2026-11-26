"""数据面内核：单飞、last-known-good、淘汰。

这是整个工作台唯一的缓存层（``PROJECT_SPEC`` §4 硬约束：不许有第二层）。
它补掉了 ``wmshare-tools`` 的 ``CachedFetcher`` 四处缺口：

| 它的做法 | 这里 |
|---|---|
| 扁平 ``ttl=300`` 一种策略 | per-topic ``TopicPolicy`` |
| 无退避 | ``backoff.classify`` 分级 |
| 无单飞 | 同 key 并发合并为一次（下方 ``_single_flight``） |
| 报错即丢值 | ``last_known_good`` 保留，只降 ``freshness`` |

**单飞的实现要点**：用 ``threading.Event`` 而不是锁住整个 ``fetch``——
若持锁取数，其它订阅者会串行等待，把「一个慢请求」放大成「一屏全慢」。
正确做法是让后来者等同一个 Event，然后共享结果。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .policy import TopicPolicy, policy_for

__all__ = ["Entry", "DataHub"]


@dataclass
class Entry:
    """一个主题的当前状态。"""

    topic: str
    value: Any = None
    as_of: str = ""
    fetched_at: float = 0.0
    error: str = ""
    #: 已尝试次数（用于指数退避）
    attempt: int = 0
    #: 下次允许刷新的时刻（退避用）
    next_retry_at: float = 0.0
    #: 引用计数：订阅者数量
    subscribers: int = 0
    #: 是否是用户「付费」取回的结果——LRU 永不淘汰
    expensive: bool = False

    @property
    def has_value(self) -> bool:
        return self.value is not None


@dataclass
class _Flight:
    """一次进行中的取数（单飞用）。"""

    event: threading.Event = field(default_factory=threading.Event)
    error: BaseException | None = None


class _Cached(Exception):
    """内部信号：本次可直接用缓存，无需取数。"""

    def __init__(self, entry: "Entry") -> None:
        self.entry = entry


class DataHub:
    """主题键控的取数协调器。

    线程安全：所有 ``_entries`` / ``_flights`` 的读写都在 ``_lock`` 下；
    但 ``producer()`` 在**锁外**执行——否则一个慢请求会阻塞所有主题。
    """

    def __init__(self, *, now: Callable[[], float] = time.time) -> None:
        self._entries: dict[str, Entry] = {}
        self._flights: dict[str, _Flight] = {}
        self._lock = threading.Lock()
        self._now = now

    # ---------------------------------------------------------------- 读取

    def peek(self, topic: str, *, respect_ttl: bool = True) -> Entry | None:
        """看当前值，**不触发取数**。

        ``respect_ttl=True`` 时过期的值算「没有」（调用方应改为 ``get``）；
        ``False`` 时无视 TTL 返回 last-known-good——这是「有数据就不白屏」的基础。
        """
        with self._lock:
            entry = self._entries.get(topic)
            if entry is None or not entry.has_value:
                return None
            if respect_ttl:
                policy = policy_for(topic)
                if self._now() - entry.fetched_at > policy.ttl_s:
                    return None
            return entry

    def peek_raw(self, topic: str) -> Entry | None:
        """无视 TTL 与错误，返回最后一笔已知值。"""
        return self.peek(topic, respect_ttl=False)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """所有主题的当前状态（供 ``/api/health``）。"""
        with self._lock:
            return {
                t: {
                    "as_of": e.as_of, "fetched_at": e.fetched_at,
                    "has_value": e.has_value, "error": e.error,
                    "attempt": e.attempt, "subscribers": e.subscribers,
                }
                for t, e in self._entries.items()
            }

    # ---------------------------------------------------------------- 取数

    def get(
        self,
        topic: str,
        producer: Callable[[], tuple[Any, str]],
        *,
        force: bool = False,
        expensive: bool = False,
        policy: TopicPolicy | None = None,
    ) -> Entry:
        """取一个主题的值；命中 TTL 直接返回，否则取数。

        ``producer()`` 返回 ``(value, as_of)``。抛出的异常会被捕获、
        记入 ``entry.error``，并**保留旧值**。

        ``force=True`` 绕过 TTL 与退避（但仍走单飞）。
        """
        pol = policy or policy_for(topic)
        try:
            _entry, flight, leader = self._prepare(topic, pol, force, expensive)
        except _Cached as hit:
            return hit.entry

        if not leader:
            # 跟随者：等同一次取数，不重复打上游
            flight.event.wait(timeout=pol.refresh_timeout_s)
            with self._lock:
                return self._entries[topic]

        return self._lead(topic, producer, flight)

    def _prepare(
        self, topic: str, pol: TopicPolicy, force: bool, expensive: bool,
    ) -> tuple[Entry, _Flight, bool]:
        """决定「直接返回缓存 / 跟随别人的 flight / 自己当领飞者」。"""
        now = self._now()
        with self._lock:
            entry = self._entries.get(topic)
            if entry is None:
                entry = Entry(topic=topic)
                self._entries[topic] = entry
            if expensive:
                entry.expensive = True
            flight, leader = self._claim(topic, entry, pol, force, now)
            return entry, flight, leader

    def _claim(
        self, topic: str, entry: Entry, pol: TopicPolicy, force: bool, now: float,
    ) -> tuple[_Flight, bool]:
        """登记/复用 flight。

        返回 ``(flight, leader)``；``leader=False`` 表示已有别人在取，等它即可。
        """
        if not force and entry.has_value and now - entry.fetched_at <= pol.ttl_s:
            raise _Cached(entry)
        if not force and entry.next_retry_at > now:
            raise _Cached(entry)
        existing = self._flights.get(topic)
        if existing is not None:
            return existing, False
        flight = _Flight()
        self._flights[topic] = flight
        return flight, True

    def _lead(
        self, topic: str, producer: Callable[[], tuple[Any, str]], flight: _Flight,
    ) -> Entry:
        """领飞：在**锁外**取数，避免一个慢请求阻塞所有主题。"""
        try:
            value, as_of = producer()
        except BaseException as exc:  # noqa: BLE001 - 交由上层分类
            with self._lock:
                entry = self._entries[topic]
                flight.error = exc
                entry.error = f"{type(exc).__name__}: {exc}"
                entry.attempt += 1
            flight.event.set()
            self._flights.pop(topic, None)
            raise
        with self._lock:
            entry = self._entries[topic]
            entry.value = value
            entry.as_of = str(as_of or "")
            entry.fetched_at = self._now()
            entry.error = ""
            entry.attempt = 0
            entry.next_retry_at = 0.0
        flight.event.set()
        self._flights.pop(topic, None)
        with self._lock:
            return self._entries[topic]

    def set_backoff(self, topic: str, delay_s: float) -> None:
        """设置某主题的下次重试时刻（由 ``backoff.classify`` 的结果驱动）。"""
        with self._lock:
            entry = self._entries.get(topic)
            if entry is not None:
                entry.next_retry_at = self._now() + max(0.0, delay_s)

    # ---------------------------------------------------------------- 订阅

    def subscribe(self, topic: str) -> None:
        with self._lock:
            entry = self._entries.setdefault(topic, Entry(topic=topic))
            entry.subscribers += 1

    def unsubscribe(self, topic: str) -> None:
        """退订；若无订阅者且策略要求 ``drop_on_idle``，清掉该主题。

        ``drop_on_idle`` 是针对**无界主题集合**的（如任意个股行情：
        5375 家公司 × 多个主题，全留会撑爆内存）。
        """
        with self._lock:
            entry = self._entries.get(topic)
            if entry is None:
                return
            entry.subscribers = max(0, entry.subscribers - 1)
            if entry.subscribers == 0 and not entry.expensive:
                if policy_for(topic).drop_on_idle:
                    self._entries.pop(topic, None)

    def evict_idle(self, max_entries: int = 2000) -> int:
        """LRU 淘汰：超过上限时清掉「可淘汰 + 无订阅」的最旧条目。

        返回清掉的条数。**``expensive=True`` 的条目永不淘汰**——那是用户
        花 EC 换来的结果，丢掉意味着让用户重付一次。
        """
        with self._lock:
            if len(self._entries) <= max_entries:
                return 0
            candidates = [
                (t, e) for t, e in self._entries.items()
                if e.subscribers == 0 and not e.expensive
            ]
            candidates.sort(key=lambda kv: kv[1].fetched_at)
            drop = max(0, len(self._entries) - max_entries)
            removed = 0
            for topic, _ in candidates[:drop]:
                self._entries.pop(topic, None)
                removed += 1
            return removed

    def clear(self) -> None:
        """清空全部（换凭证时用——旧凭证的缓存结果不应复用）。"""
        with self._lock:
            self._entries.clear()
            self._flights.clear()
