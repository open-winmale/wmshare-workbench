"""OpenAI 兼容的流式 chat/completions 客户端（纯 stdlib）。

**为什么不用 httpx/openai SDK**：运行时零第三方依赖是本项目的硬约束
（``pyproject.toml`` ``dependencies = []``）。SSE 行解析 + tool_calls
增量拼装一共 ~150 行，比引入一套客户端依赖更易维护。

流式约定（OpenAI 兼容）：

- 响应体是 ``data: {json}`` 行序列，``data: [DONE]`` 结束；
- ``choices[0].delta.content`` 是文本增量；``delta.tool_calls`` 是
  按序号增量的工具调用（``id``/``function.name`` 首块出现、
  ``function.arguments`` 逐块追加）。

**必须带 ``Accept-Encoding: identity``**：部分供应商（DeepSeek 等）的
压缩流在逐行读取时会卡住或乱码（平台侧实测，2026-11-26）。
"""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib.request import Request, urlopen

__all__ = ["LLMError", "chat_stream"]

#: HTTP 状态 → 信封处置动作（402 余额不足是**终态**，不该重试）。
_ACTION_BY_STATUS = {401: "config", 402: "topup", 403: "config",
                     404: "config", 408: "retry", 429: "retry"}


class LLMError(Exception):
    """模型 API 错误（带信封处置动作，``err_from`` 可直接映射）。"""

    def __init__(self, message: str, *, status: int = 0,
                 action: str = "retry") -> None:
        super().__init__(message)
        self.status = status
        self.action = action


def chat_stream(config: Any, *, system: str, messages: list[dict[str, Any]],
                tools: list[dict[str, Any]] | None,
                on_event: Callable[[dict[str, Any]], None]) -> list[dict[str, Any]]:
    """发一轮流式请求。事件回调两种：``text_delta`` / ``tool_calls``。

    返回**完整的工具调用列表**（无工具调用时为空列表）——文本增量已经
    通过回调流出，工具调用必须攒齐才能执行，所以由返回值给出。
    抛 :class:`LLMError`（状态码已映射为处置动作）。
    """
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": [{"role": "system", "content": system}, *messages],
        "stream": True,
    }
    if tools:
        payload["tools"] = [{"type": "function", "function": t} for t in tools]
    req = Request(  # noqa: S310 - base_url 来自用户本地配置
        config.base_url + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
            # 防压缩流卡死（见模块 docstring）
            "Accept-Encoding": "identity",
        },
        method="POST")
    try:
        resp = urlopen(req, timeout=config.timeout_s)  # noqa: S310
    except Exception as exc:  # noqa: BLE001 - 统一转 LLMError
        raise _transport_error(exc) from None
    try:
        return _read_sse(resp, on_event)
    finally:
        resp.close()


def _read_sse(resp: Any, on_event: Callable[[dict[str, Any]], None]
              ) -> list[dict[str, Any]]:
    """逐行读 SSE；拼装工具调用；文本增量即时回调。"""
    if resp.status >= 400:  # pragma: no cover - urlopen 对 >=400 抛 HTTPError
        raise LLMError(f"模型 API HTTP {resp.status}", status=resp.status,
                       action=_ACTION_BY_STATUS.get(resp.status, "retry"))
    calls: dict[int, dict[str, Any]] = {}
    for raw in resp:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:"):
            continue
        body = line[len("data:"):].strip()
        if body == "[DONE]":
            break
        try:
            chunk = json.loads(body)
        except json.JSONDecodeError:
            continue  # 心跳/残行：跳过，不中断整轮
        delta = _delta_of(chunk)
        if delta is None:
            continue
        text = delta.get("content")
        if isinstance(text, str) and text:
            on_event({"type": "text_delta", "text": text})
        for piece in delta.get("tool_calls") or []:
            _absorb_tool_call(calls, piece)
    return [calls[i] for i in sorted(calls)]


def _delta_of(chunk: dict[str, Any]) -> dict[str, Any] | None:
    choices = chunk.get("choices") or []
    if not choices:
        return None
    delta = choices[0].get("delta")
    return delta if isinstance(delta, dict) else None


def _absorb_tool_call(calls: dict[int, dict[str, Any]], piece: Any) -> None:
    """按序号增量拼装一个工具调用（arguments 是逐块追加的字符串）。"""
    if not isinstance(piece, dict):
        return
    idx = int(piece.get("index") or 0)
    slot = calls.setdefault(idx, {"id": "", "name": "", "arguments": ""})
    if piece.get("id"):
        slot["id"] = piece["id"]
    fn = piece.get("function") or {}
    if fn.get("name"):
        slot["name"] = fn["name"]
    if fn.get("arguments"):
        slot["arguments"] += fn["arguments"]


def _transport_error(exc: Exception) -> LLMError:
    """网络层异常 → 可分类错误（超时/连接失败都可重试）。"""
    status = getattr(exc, "code", 0) or 0
    if isinstance(status, int) and status >= 400:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]  # noqa: B009
        except Exception:  # noqa: BLE001
            detail = ""
        action = _ACTION_BY_STATUS.get(status, "retry")
        return LLMError(f"模型 API HTTP {status}：{detail or str(exc)}",
                        status=status, action=action)
    return LLMError(f"模型 API 连接失败：{type(exc).__name__}: {exc}",
                    action="retry")
