"""``/api/assistant/*``：AI 助手（单 agent，工具按数据域分组）。

端点形态刻意与全仓一致（一问一答 JSON 信封，无 SSE）：

- ``POST chat``：起后台线程任务，返回 ``job_id``（立即返回，不阻塞）；
- ``GET stream``：轮询任务快照（阶段 / 步骤 / 已流出文本 / 来源账）；
- ``POST stop``：协作式停止（循环顶部检查，尽力而为）；
- ``GET sessions`` / ``POST session``：会话列表 / 读取与删除。

门（不达标直接给可读错误，不进 agent）：

1. **未接入数据源**（``auth_mode == "missing"``）→ ``config``：助手的价值
   在「用真实数据回答」，没有数据源就明说；
2. **模型未配置**（无 API key）→ ``config``：给三键引导，不半路失败。
"""

from __future__ import annotations

import threading
from datetime import date
from typing import Any

from ...core.envelope import EcEstimate, error_envelope, ok_envelope
from .._shared import ToolError, err_from, str_param
from . import agent, jobs, runner
from .config import load_config, redacted
from .ledger import SourceLedger
from .skills import load_skills

__all__ = ["handle_info", "handle_chat", "handle_stream", "handle_stop",
           "handle_sessions", "handle_session"]

_MESSAGE_MAX = 4_000


def handle_info(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    """``GET /api/assistant/info``：配置状态 + 领域清单（零 EC 零网络）。

    前端引导卡（未配模型/未接入数据源）与域提示都从这取——**先看状态再发问**，
    而不是发问后被 chat 门挡回来。
    """
    from . import executor

    config = load_config()
    registry = executor.load_registry()
    domains = [{
        "id": s.id,
        "display_name": s.display_name,
        "description": s.description,
        "when_to_use": s.when_to_use,
        "tools": [t["id"] for t in registry if t.get("domain") == s.id],
    } for s in load_skills()]
    return ok_envelope(
        {
            "assistant": redacted(config),
            "auth_mode": str(getattr(ctx, "auth_mode", "missing")),
            "mode_reason": str(getattr(ctx, "mode_reason", "")),
            "domains": domains,
            "max_ec": config.max_ec,
        },
        as_of="", meta={"note": "配置状态；不访问任何上游"},
        freshness="fresh", ec=EcEstimate(model="zero_cost"))


def handle_chat(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    """发起一轮提问：参数校验 + 双门 + 起任务。**零上游请求**（任务异步跑）。"""
    try:
        message = str_param(params, "message", max_len=_MESSAGE_MAX)
        if not message:
            raise ToolError("缺少提问内容（message）", code="missing_param")
    except Exception as exc:  # noqa: BLE001
        return err_from(ctx, exc)

    gate = _gate(ctx)
    if gate is not None:
        return gate

    config = load_config()
    store = getattr(ctx, "store", None)
    session_id = str(params.get("session_id") or "").strip()
    history: list[dict[str, Any]] = []
    if session_id and store is not None:
        saved = store.get_assistant_session(session_id)
        if saved is not None:
            history = list(saved.get("messages") or [])
        else:
            session_id = ""
    if not session_id:
        session_id = _new_session_id()

    skills = load_skills()
    job = jobs.create_job(session_id, message[:24])
    thread = threading.Thread(
        target=_run_job, daemon=True,
        args=(job, ctx, config, skills, message, history))
    thread.start()
    return ok_envelope(
        {"job_id": job.id, "session_id": session_id},
        as_of="", meta={"note": "任务已起；用 /api/assistant/stream 轮询进度"},
        freshness="fresh", ec=EcEstimate(model="local"))


def handle_stream(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    job_id = str(params.get("job_id") or "")
    job = jobs.get_job(job_id)
    if job is None:
        return error_envelope(message=f"任务不存在或已过期：{job_id}",
                              code="not_found", action="fix_input")
    return ok_envelope(jobs.snapshot(job), as_of="",
                       meta={"note": "快照口径：已流出文本与来源，非最终稿"},
                       freshness="fresh", ec=EcEstimate(model="zero_cost"))


def handle_stop(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    job_id = str(params.get("job_id") or "")
    stopped = jobs.stop_job(job_id)
    return ok_envelope(
        {"job_id": job_id, "stopped": stopped},
        as_of="", meta={"note": "协作式停止：当前模型请求无法软中断"},
        freshness="fresh", ec=EcEstimate(model="zero_cost"))


def handle_sessions(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    store = getattr(ctx, "store", None)
    sessions = store.list_assistant_sessions() if store is not None else []
    return ok_envelope({"sessions": sessions, "count": len(sessions)},
                       as_of="", meta={"note": "本地会话，存 SQLite"},
                       freshness="fresh", ec=EcEstimate(model="zero_cost"))


def handle_session(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    """读取一个会话（``{id}``）或删除（``{id, action: "delete"}``）。"""
    session_id = str(params.get("id") or "")
    store = getattr(ctx, "store", None)
    if not session_id or store is None:
        return err_from(ctx, ToolError("缺少会话 id", code="missing_param"))
    if str(params.get("action") or "") == "delete":
        deleted = store.delete_assistant_session(session_id)
        return ok_envelope({"id": session_id, "deleted": deleted}, as_of="",
                           meta={"note": "会话已从本地库删除"},
                           freshness="fresh", ec=EcEstimate(model="zero_cost"))
    saved = store.get_assistant_session(session_id)
    if saved is None:
        return err_from(ctx, ToolError(f"没有会话 {session_id}",
                                       code="not_found", action="fix_input"))
    return ok_envelope(saved, as_of="", meta={"note": "历史消息整体返回"},
                       freshness="fresh", ec=EcEstimate(model="zero_cost"))


# ------------------------------------------------------------------ 门与执行

def _gate(ctx: Any) -> dict[str, Any] | None:
    """启动前双门：数据源 / 模型配置。返回错误信封或 ``None``（放行）。"""
    if str(getattr(ctx, "auth_mode", "")) == "missing":
        return error_envelope(
            message=("未接入数据源（"
                     + str(getattr(ctx, "mode_reason", "") or "未安装 wmshare")
                     + "）。助手用真实数据回答，没有数据源就明说；"
                     '请先 `pip install ".[data]"` 或配置凭证。'),
            code="not_ready", action="config")
    config = load_config()
    if not config.configured:
        return error_envelope(
            message=("AI 助手未配置模型。在 ~/.wmshare/credentials.env 或环境变量"
                     "设置三个键即可启用：WMSHARE_LLM_API_KEY（必填）、"
                     "WMSHARE_LLM_BASEURL（默认 DeepSeek）、"
                     "WMSHARE_LLM_MODEL（默认 deepseek-chat）。"),
            code="llm_not_configured", action="config")
    return None


def _run_job(job: Any, ctx: Any, config: Any, skills: list,
             message: str, history: list[dict[str, Any]]) -> None:
    """后台线程：一轮单 agent 工具循环。所有异常都要落状态。"""
    ledger = SourceLedger()
    on_event = _make_on_event(job, ledger)
    messages = list(history) + [{"role": "user", "content":
                                 message + f"\n\n（今天是 {date.today().isoformat()}）"}]
    execute_fn = runner.make_execute_fn(ctx, config, ledger, skills)
    try:
        final, _rounds = agent.run_turn(
            config=config,
            system=runner.build_system_prompt(skills),
            messages=messages,
            tools=runner.build_tools(skills),
            execute_fn=execute_fn,
            on_event=on_event,
            should_stop=lambda: job.stop)
        if job.stop and job.status != "error":
            jobs.finish(job, status="stopped")
        else:
            job.text = (job.text + final).strip()
            jobs.finish(job, status="done")
    except Exception as exc:  # noqa: BLE001 - 状态帧必须兜住一切
        jobs.finish(job, status="error",
                    error=_error_of(exc))
    _persist(ctx, job, messages, ledger)
    jobs.write_transcript(job, messages)


def _make_on_event(job: Any, ledger: SourceLedger) -> Any:
    """把 agent 事件写进任务状态（stream 轮询的就是它）。"""

    def on_event(event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == "text_delta":
            job.text += str(event.get("text") or "")
            job.phase = "组织回答"
        elif kind == "phase":
            job.phase = str(event.get("phase") or job.phase)
        elif kind == "step":
            job.steps.append({"tool": event.get("tool"),
                              "brief": event.get("brief")})
            job.phase = "取数中"
        elif kind == "tool_done":
            if event.get("evidence"):
                ledger.add(kind=str(event["evidence"].get("kind")),
                           title=str(event["evidence"].get("title")),
                           detail=str(event["evidence"].get("detail") or ""),
                           as_of=str(event["evidence"].get("as_of") or ""))
        job.sources = ledger.to_list()

    return on_event


def _persist(ctx: Any, job: Any, messages: list[dict[str, Any]],
             ledger: SourceLedger) -> None:
    """会话落库（用户消息 + 助手最终稿）。失败不吞——但也不砸任务状态。

    中间的 ``tool`` / tool_calls 消息**不入库**：那是本轮过程账
    （转写 JSONL 全量可回放），会话回放只需要问答本体。
    """
    store = getattr(ctx, "store", None)
    if store is None:
        return
    try:
        clean = [m for m in messages
                 if m.get("role") in ("user", "assistant") and m.get("content")]
        reply = {"role": "assistant", "content": job.text,
                 "sources": ledger.to_list()}
        store.save_assistant_session(job.session_id, job.title,
                                     clean + [reply])
    except Exception:  # noqa: BLE001 - 落库失败不影响本轮已给出的回答
        return


def _error_of(exc: BaseException) -> dict[str, str]:
    from .._shared import classify_exc

    action, code = classify_exc(exc)
    return {"message": str(exc) or type(exc).__name__,
            "code": code, "action": action}


def _new_session_id() -> str:
    import uuid

    return uuid.uuid4().hex[:12]
