"""通用 agent 工具循环：模型流式输出 ↔ 工具执行，直到给出最终回答。

一个循环、一次装配：系统提示 / 工具集 / 执行器闭包都由 ``runner`` 给出，
本模块不关心数据分域与取数细节，只负责「模型要工具就执行、要文本就流出」。

预算契约：

- 工具轮软上限 ``SOFT_ROUNDS``：到达后在系统层提醒收敛；
- 硬上限 ``HARD_ROUNDS``：到达即停止取数，基于已有信息作答并如实声明；
- EC 预算由执行器闭包守（见 ``runner``），循环只负责如实转述。
"""

from __future__ import annotations

import json
from typing import Any, Callable

from . import llm

__all__ = ["SOFT_ROUNDS", "HARD_ROUNDS", "run_turn"]

SOFT_ROUNDS = 8
HARD_ROUNDS = 15

#: ExecuteFn(name, args) -> (result_text_for_model, evidence|None, cost_hint_ec)
ExecuteFn = Callable[[str, dict[str, Any]], tuple[str, Any, int | None]]
#: 事件回调：phase / step / text_delta 由宿主决定怎么呈现
OnEvent = Callable[[dict[str, Any]], None]


def run_turn(*, config: Any, system: str, messages: list[dict[str, Any]],
             tools: list[dict[str, Any]], execute_fn: ExecuteFn,
             on_event: OnEvent,
             should_stop: Callable[[], bool] | None = None
             ) -> tuple[str, int]:
    """跑一轮工具循环，返回 ``(最终文本, 工具轮数)``。

    ``messages`` 会被**就地追加**（assistant/tool 消息）——调用方据此持久化
    多轮历史。文本增量实时经 ``on_event`` 流出；工具执行用 ``step`` 事件
    报告（前端渲染「哪个工具在跑」）。

    ``should_stop``：宿主轮询点（用户点「停止」），循环顶部与每个工具前
    都会检查——停止是尽力而为（正在流式的模型请求无法软中断）。
    """
    rounds = 0
    soft_warned = False
    while True:
        if should_stop is not None and should_stop():
            on_event({"type": "phase", "phase": "已停止"})
            return "（用户停止了本轮回答；以上内容到此为止）", rounds
        if rounds >= HARD_ROUNDS:
            note = ("（已连续执行 {} 轮工具，达到本轮上限；"
                    "以下基于已取得的数据回答，不再继续取数）").format(rounds)
            on_event({"type": "phase", "phase": "组织回答"})
            return note, rounds
        if rounds >= SOFT_ROUNDS and not soft_warned:
            soft_warned = True
            messages.append({"role": "user", "content":
                             "（系统提醒：工具轮数较多，请尽快基于已有信息作答；"
                             "确有必要再继续取数）"})
        calls = llm.chat_stream(
            config, system=system, messages=messages, tools=tools,
            on_event=lambda ev: on_event(ev))
        if not calls:
            return "", rounds  # 文本已全部流出；空返回表示本轮无工具调用
        rounds += 1
        messages.append({"role": "assistant", "content": None, "tool_calls": [
            {"id": c["id"], "type": "function",
             "function": {"name": c["name"], "arguments": c["arguments"]}}
            for c in calls]})
        for call in calls:
            if should_stop is not None and should_stop():
                on_event({"type": "phase", "phase": "已停止"})
                return "（用户停止了本轮回答）", rounds
            _run_one_tool(call, execute_fn, messages, on_event)


def _run_one_tool(call: dict[str, Any], execute_fn: ExecuteFn,
                  messages: list[dict[str, Any]], on_event: OnEvent) -> None:
    """执行单个工具调用并把结果追加为 tool 消息（失败也要给模型可读原因）。"""
    name, call_id = call["name"], call["id"]
    try:
        args = json_loads_or(call["arguments"])
    except ValueError as exc:
        result, evidence, cost = (f"工具参数不是合法 JSON：{exc}", None, None)
    else:
        on_event({"type": "step", "tool": name, "brief": _brief(args)})
        result, evidence, cost = execute_fn(name, args)
        on_event({"type": "tool_done", "tool": name, "cost_ec": cost,
                  "evidence": evidence})
    messages.append({"role": "tool", "tool_call_id": call_id,
                     "content": result})


def json_loads_or(raw: str) -> dict[str, Any]:
    """空串当空对象；非法 JSON 抛 ``ValueError``（由调用方转成工具结果）。"""
    if not raw or not raw.strip():
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"期望对象，收到 {type(value).__name__}")
    return value


def _brief(args: dict[str, Any]) -> str:
    parts = [f"{k}={str(v)[:20]}" for k, v in list(args.items())[:3]]
    return " ".join(parts)
