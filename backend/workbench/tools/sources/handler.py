"""``/api/sources/run``：数据源与新鲜度总览。

**为什么第一个做这个**：它零取数（只读本地配置与库），因此能在没有任何凭证、
不消耗一 EC 的前提下验证整条管道（handler → 信封 → 前端渲染）。
同时它是本项目「不骗人」原则最集中的体现——把 119 个数据集的过期状态摊开。

数据来源：
1. ``client.hub.policy.load_staleness_table()`` — 从兄弟仓 ``stats_config.py``
   AST 解析出的 ``{collection: (staleness_days, warn_days)}``
2. ``store`` — 库版本、表数、凭证来源
3. wmshare 可用性

兄弟仓缺失时如实返回 ``available: false`` 并给指引，**不伪造阈值**。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ...client.hub import judge, load_staleness_table, policy_for
from ...core.envelope import EcEstimate, ok_envelope

__all__ = ["handle", "DATASET_LABELS"]

#: collection → 中文展示名。只列 UI 需要显示的高频集；
#: 未列出的按 collection 原名显示（不猜含义）。
DATASET_LABELS: dict[str, str] = {
    "cn_stock_fn_balance": "资产负债表",
    "cn_stock_fn_income": "利润表",
    "cn_stock_fn_cashflow": "现金流量表",
    "cn_stock_fn_main": "财务指标",
    "cn_stock_notice": "公告 PDF",
    "cn_stock_dividend_lxr": "分红",
    "cn_kzz_cb_list": "转债合约快照",
    "cn_stock_thbj_gzbj": "估值比较",
}

#: 每个数据集对应的主题前缀（用于取 TTL，让用户看到「多久刷一次」）。
_TOPIC_HINTS: tuple[tuple[str, str], ...] = (
    ("fn_balance", "fund:statement"),
    ("fn_income", "fund:statement"),
    ("fn_cashflow", "fund:statement"),
    ("fn_main", "fund:statement"),
    ("notice", "disc:notice"),
    ("dividend", "disc:dividend"),
    ("kzz", "disc:cbond"),
    ("gzbj", "fund:valuation"),
)


def _topic_for(collection: str) -> str:
    for needle, topic in _TOPIC_HINTS:
        if needle in collection:
            return topic
    return "fund:"


def _label(collection: str) -> str:
    return DATASET_LABELS.get(collection) or collection


def handle(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    """返回新鲜度总览。**零 EC**：不调用 fetcher。"""
    table = load_staleness_table()
    today = date.today()

    rows: list[dict[str, Any]] = []
    for collection, (stale_days, warn_days) in sorted(table.items()):
        topic = _topic_for(collection)
        policy = policy_for(topic)
        verdict = judge(
            None,
            stale_after_days=warn_days if warn_days is not None else stale_days,
            expire_after_days=stale_days,
            label=_label(collection),
            today=today,
        )
        rows.append({
            "collection": collection,
            "label": _label(collection),
            "stale_after_days": warn_days if warn_days is not None else stale_days,
            "expire_after_days": stale_days,
            "topic": topic,
            "ttl_s": policy.ttl_s,
            "freshness": verdict.freshness,
            "age_days": verdict.age_days,
            "warning": verdict.warning,
        })

    summary = _summarize(rows)
    # 新鲜度是相对「参照日（今天）」算的——把参照日如实给出去，
    # 否则 age_days 是个没有锚点的相对数，用户无从校验
    reference = today.isoformat()
    return ok_envelope(
        {
            "available": bool(table),
            "count": len(rows),
            "summary": summary,
            "datasets": rows,
            "reference": reference,
            "store": _store_state(ctx),
            "credentials": _cred_state(ctx),
            "note": ("" if table else
                     "未找到兄弟仓 stats_config.py；新鲜度阈值不可用。"
                     "设置 WORKBENCH_STATS_CONFIG 指向该文件即可启用。"),
        },
        as_of="",
        meta={"source": "local", "zero_cost": True,
              "reference": reference},
        ec=EcEstimate(model="zero_cost"),
        warnings=[f"{summary['expired']} 个数据集已过期"] if summary["expired"] else [],
    )


def _summarize(rows: list[dict[str, Any]]) -> dict[str, int]:
    out = {"fresh": 0, "stale": 0, "expired": 0, "unknown": 0}
    for r in rows:
        out[r["freshness"]] = out.get(r["freshness"], 0) + 1
    return out


def _store_state(ctx: Any) -> dict[str, Any]:
    store = getattr(ctx, "store", None)
    if store is None:
        return {"ok": False}
    try:
        return {
            "ok": True,
            "version": store.version(),
            "tables": len(store.tables()),
            "path": str(getattr(store, "path", "")),
        }
    except Exception as exc:  # noqa: BLE001 - 如实回传原因
        return {"ok": False, "note": f"{type(exc).__name__}: {exc}"}


def _cred_state(ctx: Any) -> dict[str, Any]:
    cred = getattr(ctx, "credentials", None)
    if cred is None:
        return {"configured": False, "source": "none"}
    return cred.redacted()
