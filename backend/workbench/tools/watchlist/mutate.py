"""自选的增删（**零取数**：只写本地 SQLite，不碰行情）。

**为什么单独一个模块**：取数路径（批量优先 / 逐票降级）与写入路径是两件
不同的事——前者要处理权限拒绝与请求计数，后者只跟本地库打交道。挤在一个
handler 里会让 `handle` 的圈复杂度撞上 12 的上限，也让人误以为增删会花钱。

**此前的缺口**：`store.add_watch/remove_watch` 早已实现，却没有任何调用方。
用户只能读到 ``DEFAULT_SYMBOLS`` 那 5 只样例，`watchlist` 表形同虚设——
「自选清单存在本地库」这句话在文档里写了很久，但根本没有写入路径。

**写库失败必须如实报**：用户加了一只票、刷新后不见了，若是静默失败
他会以为自己记错。
"""

from __future__ import annotations

from typing import Any

from ...core.envelope import EcEstimate, ok_envelope
from ...tools._shared import ToolError, err_from, str_list_param, str_param

__all__ = ["run", "saved_codes"]

#: 默认分组名（UI 目前不暴露分组切换）。
DEFAULT_GROUP = "default"


def run(ctx: Any, action: str,
        params: dict[str, Any]) -> dict[str, Any]:
    """按 ``action`` 增删自选，返回**落库后的真实清单**。

    回显 ``saved`` 而不是只回显「已加入」：让用户看见库里真有什么，
    而不是相信一句提示语。
    """
    store = getattr(ctx, "store", None)
    if store is None:
        return err_from(ctx, ToolError("存储未初始化：无法保存自选",
                                       code="internal", action="report"))
    try:
        targets = _targets(params)
        group = str_param(params, "group") or DEFAULT_GROUP
        _apply(store, action, targets, group)
        saved = saved_codes(store, group)
    except Exception as exc:  # noqa: BLE001
        return err_from(ctx, exc)

    verb = "加入" if action == "add" else "移出"
    return ok_envelope(
        {"action": action, "changed": targets, "group": group,
         "saved": saved, "count": len(saved),
         "groups": _groups(ctx)},
        as_of="",
        meta={"note": f"已{verb}自选 {len(targets)} 只；零取数",
              "zero_requests": True},
        freshness="fresh",
        ec=EcEstimate(model="zero_cost"))


def _targets(params: dict[str, Any]) -> list[str]:
    """要增删的代码。``symbols``（逗号串/数组）优先，退回单个 ``symbol``。"""
    codes = str_list_param(params, "symbols")
    one = str_param(params, "symbol")
    targets = codes or ([one] if one else [])
    if not targets:
        raise ToolError("缺少标的（symbol 或 symbols）", code="missing_param")
    return targets


def _apply(store: Any, action: str, targets: list[str], group: str) -> None:
    """逐只写入/删除。重复加入是幂等的（`INSERT OR IGNORE`）。"""
    for code in targets:
        if action == "add":
            store.add_watch(code, group=group)
        else:
            store.remove_watch(code, group=group)


def saved_codes(store: Any, group: str) -> list[str]:
    """当前分组里真实落库的代码（用于回显「确实写进去了」）。"""
    try:
        rows = store.list_watch(group)
    except Exception:  # noqa: BLE001
        return []
    return [str(r.get("code")) for r in rows if r.get("code")]


def _groups(ctx: Any) -> list[str]:
    """已有分组名（供 UI 分组切换）。读库失败按「无分组」处理。"""
    store = getattr(ctx, "store", None)
    if store is None:
        return []
    try:
        rows = store.list_watch()
    except Exception:  # noqa: BLE001
        return []
    out: list[str] = []
    for r in rows:
        g = str(r.get("group_name") or "")
        if g and g not in out:
            out.append(g)
    return out
