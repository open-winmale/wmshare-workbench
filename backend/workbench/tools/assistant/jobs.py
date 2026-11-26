"""任务台账：chat 起后台线程，stream 轮询快照——进程内内存账。

**为什么不是 SSE**：后端是 stdlib ``ThreadingHTTPServer``，现有全部端点
都是「一问一答 JSON 信封」。本地回环轮询（前端 ~800ms）延迟可忽略，
却完全不引入新的服务端机制——这与「零第三方依赖、易于维护」同权重。

**为什么不是持久队列**：本地单用户工具，服务重启丢任务可接受；
会话本身已落库（``store``），丢的只是正在跑的那一轮的过程帧。
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["Job", "create_job", "get_job", "stop_job", "prune", "snapshot",
           "write_transcript"]

#: 任务保留时长（结束后）与台账上限——防无界增长。
KEEP_AFTER_DONE_S = 15 * 60
MAX_JOBS = 30

#: 会话/转写目录（``~/.wmshare/workbench/assistant/<session>/<turn>.jsonl``）。
TRANSCRIPT_DIR = Path.home() / ".wmshare" / "workbench" / "assistant"

_JOBS: dict[str, "Job"] = {}
_LOCK = threading.Lock()


@dataclass
class Job:
    """一轮回答的运行态。字段更新都在 ``_LOCK`` 内（stream 并发读）。"""

    id: str
    session_id: str
    title: str
    status: str = "running"          # running / done / error / stopped
    phase: str = "在读上下文"
    steps: list[dict[str, Any]] = field(default_factory=list)
    text: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)
    error: dict[str, str] | None = None
    stop: bool = False
    created: float = field(default_factory=time.time)
    #: ``threading.Event`` 不需要——``stop`` 布尔由执行闭包轮询


def create_job(session_id: str, title: str) -> Job:
    job = Job(id=uuid.uuid4().hex[:12], session_id=session_id, title=title)
    with _LOCK:
        prune_locked(time.time())
        _JOBS[job.id] = job
    return job


def get_job(job_id: str) -> Job | None:
    with _LOCK:
        return _JOBS.get(job_id)


def stop_job(job_id: str) -> bool:
    with _LOCK:
        job = _JOBS.get(job_id)
    if job is None or job.status != "running":
        return False
    job.stop = True
    return True


def finish(job: Job, *, status: str, error: dict[str, str] | None = None) -> None:
    job.status = status
    job.error = error
    job.created = time.time()  # 复用为「结束时刻」，供 prune 计龄


def snapshot(job: Job) -> dict[str, Any]:
    """轮询快照（信封 ``data``）：当前帧 + 已流出的文本与来源。"""
    with _LOCK:
        return {
            "job_id": job.id,
            "session_id": job.session_id,
            "status": job.status,
            "phase": job.phase,
            "steps": list(job.steps[-40:]),
            "text": job.text,
            "sources": list(job.sources),
            "error": job.error,
            "title": job.title,
        }


def prune_locked(now: float) -> None:
    """清完场的老任务（必须在持锁状态下调用）。"""
    stale = [jid for jid, j in _JOBS.items()
             if j.status != "running" and now - j.created > KEEP_AFTER_DONE_S]
    for jid in stale:
        _JOBS.pop(jid, None)
    while len(_JOBS) > MAX_JOBS:
        oldest = min(_JOBS, key=lambda k: _JOBS[k].created)
        if _JOBS[oldest].status == "running":
            break
        _JOBS.pop(oldest)


def write_transcript(job: Job, messages: list[dict[str, Any]]) -> None:
    """每轮过程落 JSONL（可回放台账）。**尽力而为**：写失败不影响回答。"""
    try:
        base = TRANSCRIPT_DIR / job.session_id
        base.mkdir(parents=True, exist_ok=True)
        payload = {"job_id": job.id, "status": job.status,
                   "phase": job.phase, "steps": job.steps,
                   "sources": job.sources,
                   "error": job.error, "messages": messages,
                   "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        (base / f"{job.id}.jsonl").write_text(
            json.dumps(payload, ensure_ascii=False, default=str),
            encoding="utf-8")
    except OSError:
        pass
