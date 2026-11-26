"""来源账（宿主编号）：证据由宿主统一编号，模型只引用，不自己造来源。

借鉴成熟投研助手产品的「来源账」理念（宿主侧从 1 起编号、去重、封顶，
工具结果交给模型前加「来源 n：标题」前缀；成稿只写 ``[n]``），实现刻意
精简：无独立集合、无平台路由字段——账随轮次存在，随消息落库。

**为什么编号必须由宿主做**：让模型自己管理「第几个来源」必然错位
（它数不清自己读过多少块结果）；宿主在工具结果前写好编号行，模型只需
照抄 ``[n]``，前端把 ``[n]`` 渲染成可点的来源芯片。
"""

from __future__ import annotations

__all__ = ["MAX_SOURCES", "SourceLedger"]

#: 单轮证据上限：再多说明这轮在乱翻，应该收敛问题而不是继续取证。
MAX_SOURCES = 24


class SourceLedger:
    """一轮对话的内存证据账。线程约束：单轮内串行使用，无需加锁。"""

    def __init__(self) -> None:
        #: ``[{n, kind, title, detail, as_of}]``——落库给前端渲染芯片。
        self.sources: list[dict[str, object]] = []
        self._keys: set[tuple[str, str]] = set()

    def add(self, *, kind: str, title: str, detail: str = "",
            as_of: str = "") -> int | None:
        """登记一条证据，返回编号；重复键或超上限返回 ``None``。"""
        key = (kind, title)
        if key in self._keys:
            existing = next(s["n"] for s in self.sources
                            if (s["kind"], s["title"]) == key)
            return int(existing)  # type: ignore[arg-type]
        if len(self.sources) >= MAX_SOURCES:
            return None
        n = len(self.sources) + 1
        self._keys.add(key)
        self.sources.append({"n": n, "kind": kind, "title": title,
                             "detail": detail, "as_of": as_of})
        return n

    def prefix_for(self, n: int | None, title: str, as_of: str) -> str:
        """工具结果交给模型前的编号行（模型据此在成稿里写 ``[n]``）。"""
        if n is None:
            return ""
        suffix = f" · 截至 {as_of}" if as_of else ""
        return f"来源 {n}：{title}{suffix}\n"

    def to_list(self) -> list[dict[str, object]]:
        return list(self.sources)
