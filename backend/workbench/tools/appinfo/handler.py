"""``/api/appinfo``：版本、访问方式、凭证状态。

页顶横幅靠这个端点决定显示什么。**三种访问方式必须能分清楚**：

| ``auth_mode`` | 页顶显示 | 数据 |
|---|---|---|
| ``credentials`` | 自有凭证 | 真实 |
| ``public_pool`` | 免注册（真实数据） | 真实 |
| ``missing`` | 未接入 · **原因** | 无（取数会失败） |

只回一个 ``real: true/false`` 是不够的——用户看到「未接入」时最想知道的是
**为什么**，以及**怎样才能接入真实数据**。因此 ``reason`` 必填（``missing`` 态）。

**绝不返回 secret 原文**——只给尾 4 位便于用户确认用的是哪把 Key。
"""

from __future__ import annotations

from typing import Any

from ...core.envelope import EcEstimate, ok_envelope

__all__ = ["handle", "MODE_LABELS"]


#: 访问方式 → 中文标签（页顶直接显示）。
MODE_LABELS: dict[str, str] = {
    "credentials": "自有凭证",
    "public_pool": "免注册",
    "missing": "未接入数据源",
}


def handle(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    """返回运行期信息。不做任何取数，因此零 EC。"""
    import workbench

    cred = ctx.credentials
    mode = str(getattr(ctx, "auth_mode", "missing"))
    return ok_envelope(
        {
            "version": workbench.__version__,
            "auth_mode": mode,
            "mode_label": MODE_LABELS.get(mode, mode),
            # 是否真实数据（含免注册）。前端据此决定是否显示「未接入」琥珀标。
            "real": mode != "missing",
            # 未接入时的原因（已接入为空串）。没有它用户无从知道怎么接入。
            "reason": str(getattr(ctx, "mode_reason", "")),
            "credentials": cred.redacted() if cred is not None else {
                "configured": False, "source": "none"},
            "wmshare_available": _wmshare_available(),
            "python": _python_version(),
        },
        as_of="",
        meta={"source": "local"},
        ec=EcEstimate(model="zero_cost"),
    )


def _wmshare_available() -> bool:
    try:
        import wmshare  # noqa: F401
    except ImportError:
        return False
    return True


def _python_version() -> str:
    import platform

    return platform.python_version()
