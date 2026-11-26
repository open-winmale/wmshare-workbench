"""``/api/tools``：工具注册表。

前端据此生成导航与路由。与 ``core.envelope.ENDPOINTS`` 同源——
端点路径不在前端硬编码，而是从这里/契约读取。
"""

from __future__ import annotations

from typing import Any

from ...core.envelope import ENDPOINTS, EcEstimate, ok_envelope

__all__ = ["handle"]

#: 工具元信息：slug → 展示名与所属阶段。
#: 新增工具必须同时在此与 ``core.envelope.ENDPOINTS`` 登记。
META: dict[str, dict[str, str]] = {
    "sources": {"title": "数据源", "stage": "P3", "kind": "tool"},
    "watchlist": {"title": "自选", "stage": "P3", "kind": "tool"},
    "markets": {"title": "行情", "stage": "P3", "kind": "tool"},
    "economics": {"title": "宏观", "stage": "P3", "kind": "tool"},
    "backtest": {"title": "回测", "stage": "P3", "kind": "tool"},
    "dashboard": {"title": "驾驶舱", "stage": "P3", "kind": "tool"},
    "screener": {"title": "选股", "stage": "P4", "kind": "tool"},
    "equity": {"title": "个股研究", "stage": "P4", "kind": "tool"},
    "portfolio": {"title": "持仓", "stage": "P4", "kind": "tool"},
}


def handle(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    """列出全部工具与端点。``ready`` 表示该端点本轮是否已实现业务逻辑。"""
    items: list[dict[str, Any]] = []
    for slug, meta in META.items():
        spec = ENDPOINTS.get(slug, {})
        items.append({
            "slug": slug,
            "title": meta["title"],
            "stage": meta["stage"],
            "method": spec.get("method", ""),
            "path": spec.get("path", ""),
            "ready": slug in getattr(ctx, "registry", {}),
        })
    return ok_envelope(
        {"tools": items, "count": len(items)},
        meta={"note": "ready=false 的端点在对应阶段接入真实取数"},
        ec=EcEstimate(model="zero_cost"),
    )
