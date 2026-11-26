"""``/api/health``：hub / db / wmshare 三态。

「健康」不等于「能取数」——本地工具最常见的故障是**配置缺失**而非服务挂了。
所以三态分开报：hub 有没有值、db 能不能读、wmshare 装没装且有没凭证。
"""

from __future__ import annotations

from typing import Any

from ...core.envelope import EcEstimate, ok_envelope

__all__ = ["handle"]


def handle(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    return ok_envelope(
        {
            "hub": _hub_state(ctx),
            "db": _db_state(ctx),
            "wmshare": _wmshare_state(ctx),
        },
        meta={"note": "任一态为 false 时前端应在设置页给出对应指引"},
        ec=EcEstimate(model="zero_cost"),
    )


def _hub_state(ctx: Any) -> dict[str, Any]:
    """主题缓存状态。``peek`` 不触发取数，所以这里零 EC。"""
    hub = getattr(ctx, "hub", None)
    if hub is None:
        return {"ok": False, "topics": 0, "note": "hub 未初始化"}
    snap = hub.snapshot()
    return {
        "ok": True,
        "topics": len(snap),
        "with_value": sum(1 for v in snap.values() if v.get("has_value")),
        "with_error": sum(1 for v in snap.values() if v.get("error")),
    }


def _db_state(ctx: Any) -> dict[str, Any]:
    store = getattr(ctx, "store", None)
    if store is None:
        return {"ok": False, "note": "store 未初始化"}
    try:
        tables = store.tables()
        return {"ok": True, "version": store.version(), "tables": len(tables),
                "permission_ok": bool(getattr(store, "permission_ok", True))}
    except Exception as exc:  # noqa: BLE001 - 健康检查不吞真实原因
        return {"ok": False, "note": f"{type(exc).__name__}: {exc}"}


def _wmshare_state(ctx: Any) -> dict[str, Any]:
    try:
        import wmshare
    except ImportError:
        return {"ok": False, "installed": False,
                "note": "未安装 wmshare；请 pip install \".[data]\" 后重启"}
    cred = getattr(ctx, "credentials", None)
    return {
        "ok": True,
        "installed": True,
        "version": getattr(wmshare, "__version__", ""),
        "credentials": bool(cred.present) if cred is not None else False,
        "mode": "live",
    }
