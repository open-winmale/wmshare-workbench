"""``client/hub`` 的离线测试：策略、退避、新鲜度、单飞、终值、淘汰。

**零网络、零凭证、零等待**：``DataHub`` 的时钟可注入（``now``），退避用
``set_backoff`` 显式设置而不真 ``sleep``。

``errors`` 系列用例直接 import wmshare 的异常类——SDK 是可选运行时依赖
（CONTRIBUTING 的贡献者安装 `.[dev]` 不含它），缺 SDK 时**整组诚实跳过**
而不是 ModuleNotFoundError 砸脸；CI 装 `.[data]` 让它真跑。
"""

from __future__ import annotations

import threading
import time
from datetime import date

import pytest
from workbench.client.hub import (
    DataHub,
    classify,
    delay_for_attempt,
    jittered,
    judge,
    load_staleness_table,
    policy_for,
)

pytest.importorskip("wmshare", reason="wmshare SDK 未安装（pip install '.[data]' 后生效）")

# ---------------------------------------------------------------- policy

def test_quote_policy_is_short() -> None:
    """盘中行情 TTL 短（30s）；旧值可淘汰（无界主题集合）。"""
    p = policy_for("market:quote:600519")
    assert p.ttl_s <= 60
    assert p.drop_on_idle is True


def test_concept_list_policy_is_weekly() -> None:
    """板块目录是周更物化 —— TTL 必须 ≥7 天，否则天天重取。"""
    p = policy_for("board:concept_list")
    assert p.ttl_s >= 604800
    assert p.source == "weekly"


def test_longest_prefix_wins() -> None:
    """最长前缀匹配：``board:concept_list`` 不能被 ``board:`` 吃掉。"""
    weekly = policy_for("board:concept_list")
    daily = policy_for("board:moneyflow:ths_concept")
    assert weekly.ttl_s > daily.ttl_s


def test_unknown_topic_gets_fallback() -> None:
    """未知主题用兜底策略，且标记 source=fallback（不冒充已知）。"""
    p = policy_for("totally:unknown:topic")
    assert p.source == "fallback"
    assert p.ttl_s > 0


def test_policy_rejects_inverted_thresholds() -> None:
    """warning 阈值不能大于 expire 阈值，否则 stale 档永远不可达。"""
    from workbench.client.hub.policy import TopicPolicy
    with pytest.raises(ValueError):
        TopicPolicy(ttl_s=60, stale_after_s=100, expire_after_s=10)


def test_staleness_table_from_stats_config() -> None:
    """能从兄弟仓 AST 解析出真值（119 条）；缺失时返回空 dict 而非崩。"""
    table = load_staleness_table()
    if not table:
        pytest.skip("兄弟仓 stats_config 不可用（CI 单仓环境）")
    assert len(table) >= 100
    # 财报类应是真的季度阈值，不是 0
    assert "cn_stock_fn_balance" in table
    days, _warn = table["cn_stock_fn_balance"]
    assert days >= 30


def test_staleness_table_missing_file_returns_empty(tmp_path) -> None:
    """兄弟仓缺失 → 空 dict（调用方据此降级，不崩）。"""
    assert load_staleness_table(tmp_path / "nope.py") == {}


# ---------------------------------------------------------------- backoff

def test_retry_delay_sequence() -> None:
    """退避序列精确为 2/5/15/60/300，之后保持 300。"""
    assert [delay_for_attempt(i) for i in range(5)] == [2.0, 5.0, 15.0, 60.0, 300.0]
    assert delay_for_attempt(99) == 300.0


def test_jitter_stays_within_10_percent() -> None:
    """抖动 ±10%，不放大。"""
    for r in (0.0, 0.5, 0.999):
        d = jittered(100.0, r)
        assert 90.0 <= d <= 110.0


def test_quota_error_is_terminal_and_checked_before_limit() -> None:
    """``QuotaError`` 终态且必须先于 ``LimitError`` 判。

    ``QuotaError`` 是 ``LimitError`` 子类——顺序写反会把「额度耗尽」
    当成可重试，白烧一小时配额。
    """
    from wmshare.errors import QuotaError

    d = classify(QuotaError("额度没了", code="EC_BALANCE_EXHAUSTED"))
    assert d.retryable is False
    assert d.terminal is True
    assert d.action == "topup"


def test_rate_limited_uses_retry_after() -> None:
    """限流且服务端给了 ``retry_after`` → 照它给的等。"""
    from wmshare.errors import LimitError

    d = classify(LimitError("slow down", code="rate_limited", retry_after=7))
    assert d.retryable is True
    assert d.delay_s == 7.0


def test_ip_rate_limited_has_long_floor() -> None:
    """共享额度受限 → 退避地板 ≥60s（禁止紧循环）。"""
    from wmshare.errors import LimitError

    d = classify(LimitError("ip", code="ip_rate_limited"))
    assert d.retryable is True
    assert d.delay_s >= 60.0


def test_param_limit_is_not_retryable() -> None:
    """参数超限重试不会变 → 终态 + fix_input。"""
    from wmshare.errors import LimitError

    d = classify(LimitError("too many rows", code="limit"))
    assert d.retryable is False
    assert d.action == "fix_input"


def test_transport_error_is_retryable() -> None:
    """网络/服务端瞬时故障可重试。"""
    from wmshare.errors import ServerError, TransportError

    assert classify(TransportError("net")).retryable is True
    assert classify(ServerError("500")).retryable is True


def test_data_error_is_terminal_report() -> None:
    """数据完整性错误不重试（重试只会重复拿到坏数据），且要上报。"""
    from wmshare.errors import DataError

    d = classify(DataError("invariant", code="invariant"))
    assert d.retryable is False
    assert d.action == "report"


def test_unknown_exception_not_retried() -> None:
    """不认识的异常不重试——宁可让人看错误，也不静默重试掩盖问题。"""
    d = classify(RuntimeError("boom"))
    assert d.retryable is False
    assert d.action == "report"


# ---------------------------------------------------------------- freshness

def test_freshness_three_tiers() -> None:
    """期龄 128 天（阈值 120/90）→ expired；95 → stale；10 → fresh。"""
    today = date(2026, 11, 25)
    kw = dict(stale_after_days=90, expire_after_days=120, label="资产负债表",
              today=today)
    assert judge("2026-07-20", **kw).freshness == "expired"    # 128 天
    assert judge("2026-08-22", **kw).freshness == "stale"      # 95 天
    assert judge("2026-11-15", **kw).freshness == "fresh"      # 10 天


def test_expired_warning_is_specific() -> None:
    """告警必须含具体数字与数据集名，不能只说「数据旧了」。"""
    v = judge("2026-07-20", stale_after_days=90, expire_after_days=120,
              label="资产负债表", today=date(2026, 11, 25))
    assert "128" in v.warning
    assert "120" in v.warning
    assert "资产负债表" in v.warning


def test_unknown_when_no_thresholds() -> None:
    """无真值 → unknown，不猜（猜「新鲜」会让用户误信旧数据）。"""
    v = judge("2026-07-20", today=date(2026, 11, 25))
    assert v.freshness == "unknown"
    assert v.known is False


def test_unknown_when_as_of_unparsable() -> None:
    v = judge("", stale_after_days=30, today=date(2026, 11, 25))
    assert v.freshness == "unknown"


# ---------------------------------------------------------------- hub 核心

def test_hit_within_ttl_does_not_refetch() -> None:
    """TTL 内第二次调用不触发上游。"""
    hub = DataHub()
    calls = []

    def producer():
        calls.append(1)
        return {"v": len(calls)}, "2026-11-25"

    hub.get("market:kline:600519", producer)
    hub.get("market:kline:600519", producer)
    assert len(calls) == 1


def test_single_flight_merges_concurrent_requests() -> None:
    """同 key 并发 10 请求，上游只被调用 **1** 次。

    这是本门禁最重要的一条：驾驶舱一屏 8 个面板会并发触发取数，
    没有单飞就是 8 次重复请求 × EC。
    """
    hub = DataHub()
    calls = []
    started = threading.Event()

    def producer():
        calls.append(1)
        started.wait(timeout=5)     # 让其余线程都进来等同一个 flight
        return {"v": 1}, "2026-11-25"

    results: list[object] = []

    def worker():
        results.append(hub.get("market:quote:600519", producer))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    time.sleep(0.05)                # 让首个线程进入 producer
    started.set()
    for t in threads:
        t.join(timeout=5)

    assert len(calls) == 1
    assert len(results) == 10


def test_last_known_good_survives_error() -> None:
    """异常后 ``peek_raw`` 仍返回旧值——有数据就不白屏。"""
    hub = DataHub()
    hub.get("market:kline:600519", lambda: ({"close": 100}, "2026-11-20"))

    def boom():
        raise RuntimeError("upstream down")

    with pytest.raises(RuntimeError):
        hub.get("market:kline:600519", boom, force=True)

    entry = hub.peek_raw("market:kline:600519")
    assert entry is not None
    assert entry.value == {"close": 100}
    assert "RuntimeError" in entry.error


def test_backoff_blocks_refetch_until_due() -> None:
    """退避期内不重新打上游；到点后可再试。"""
    clock = {"t": 1000.0}
    hub = DataHub(now=lambda: clock["t"])
    calls = []

    def producer():
        calls.append(1)
        return {"v": len(calls)}, "2026-11-25"

    hub.get("market:kline:600519", producer, force=True)
    hub.set_backoff("market:kline:600519", 60.0)
    clock["t"] += 30                      # 退避未到期
    hub.get("market:kline:600519", producer)
    assert len(calls) == 1

    clock["t"] += 40                      # 到期了
    hub.get("market:kline:600519", producer, force=True)
    assert len(calls) == 2


def test_drop_on_idle_clears_after_last_subscriber() -> None:
    """``drop_on_idle`` 主题在最后订阅者离开后清态（防无界集合撑爆内存）。"""
    hub = DataHub()
    hub.get("market:quote:600519", lambda: ({"close": 1}, "2026-11-25"))
    hub.subscribe("market:quote:600519")
    hub.unsubscribe("market:quote:600519")
    assert hub.peek_raw("market:quote:600519") is None


def test_non_droppable_topic_survives_unsubscribe() -> None:
    """非 ``drop_on_idle`` 主题（如指数行情）退订后仍保留。"""
    hub = DataHub()
    hub.get("index:trend:index.hs300", lambda: ({"pe": 12}, "2026-11-25"))
    hub.subscribe("index:trend:index.hs300")
    hub.unsubscribe("index:trend:index.hs300")
    assert hub.peek_raw("index:trend:index.hs300") is not None


def test_expensive_entry_never_evicted() -> None:
    """用户花 EC 换来的结果不因 LRU 被丢——丢了意味着让用户重付一次。"""
    hub = DataHub()
    hub.get("market:kline:600519", lambda: ({"v": 1}, "2026-11-25"),
            expensive=True)
    for i in range(50):
        hub.get(f"market:quote:x{i}", lambda: ({"v": i}, "2026-11-25"),
                force=True)
    hub.evict_idle(max_entries=1)
    assert hub.peek_raw("market:kline:600519") is not None


def test_clear_removes_everything() -> None:
    """换凭证后必须清空——旧凭证的缓存结果不应被复用。"""
    hub = DataHub()
    hub.get("market:kline:600519", lambda: ({"v": 1}, "2026-11-25"))
    hub.clear()
    assert hub.peek_raw("market:kline:600519") is None


def test_peek_does_not_fetch() -> None:
    """``peek`` 绝不触发取数（面板首次渲染前先用 peek 判断有无缓存）。"""
    hub = DataHub()
    calls = []
    assert hub.peek("market:kline:600519") is None
    assert calls == []


def test_snapshot_reports_state() -> None:
    """``snapshot`` 供 ``/api/health``；应含 has_value/error/attempt。"""
    hub = DataHub()
    hub.get("market:kline:600519", lambda: ({"v": 1}, "2026-11-25"))
    snap = hub.snapshot()
    assert "market:kline:600519" in snap
    assert snap["market:kline:600519"]["has_value"] is True
