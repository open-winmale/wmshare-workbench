"""单端口 HTTP 服务：API + 静态产物同源，只绑 ``127.0.0.1``。

**为什么用标准库 ``ThreadingHTTPServer`` 而不是 FastAPI**：``dependencies = []``
是产品价值的一部分（clone 下来就能跑）。``wmshare-tools`` 与 ``fin-extract``
同此选择。代价是自己实现路由与 MIME，收益是零安装负担。

**静态托管七条**（``docs/ARCHITECTURE.md`` §5，逐条对应本文件实现）：

1. ``/api/*`` 前缀优先匹配，不参与静态托管
2. ``/`` → ``static/index.html``，``Cache-Control: no-cache``（**不是 ``no-store``**：
   ``no-cache`` = 可缓存但必须重验证；``no-store`` = 禁止存储，会让每次刷新都重新下载）
3. ``/assets/*`` → 文件名含 hash，``immutable`` 长缓存
4. 路径穿越防御：``resolve()`` 后断言仍在根内（``commonpath`` 比较），
   **不是**只取末段——取末段会丢掉子目录结构
5. MIME 用显式字典，不用 ``mimetypes``（后者行为依赖操作系统注册表）
6. ``static/index.html`` 不存在 → 返回 HTML 提示页（``platform/not_built.py``），
   **HTTP 200 而非 500**（本地工具不该报服务器错误）
7. 每请求 ``is_file()`` 运行时探测，构建后刷新即生效、无需重启

**路由用 hash 模式**，所以**不需要 SPA fallback**——只需托管 ``/`` 与 ``/assets/*``。
"""

from __future__ import annotations

import json
import os
import posixpath
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from ..core.envelope import ENDPOINTS, error_envelope
from .not_built import NOT_BUILT_HTML

__all__ = ["ServerContext", "make_handler", "serve", "HOST", "DEFAULT_PORT"]

#: 只绑回环——本地工具不应对外可达（``DEBT.md`` D-07）。
HOST = "127.0.0.1"
DEFAULT_PORT = 8787

#: 静态产物的 MIME 白名单。显式列出，避免 ``mimetypes`` 依赖 OS 注册表
#: （``.js`` 在某些 Windows 上会解析成 ``text/plain``，导致模块脚本被拒执行）。
MIME: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".map": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


class ServerContext:
    """服务运行期需要的全部依赖（显式传入，不搞全局单例）。"""

    def __init__(
        self,
        *,
        store: Any,
        fetcher: Any,
        static_dir: Path,
        registry: dict[str, Callable[..., Any]],
        context: Any = None,
    ) -> None:
        self.store = store
        self.fetcher = fetcher
        self.static_dir = static_dir
        self.registry = registry
        #: 组合根注入的业务上下文（含 credentials / hub / auth_mode）。
        #: handler 拿到的是它，而不是本对象——这样 handler 不必知道 HTTP 层。
        self.context = context

    def routes(self) -> dict[tuple[str, str], Callable[..., Any]]:
        """``(method, path) -> handler``，直接从契约的 ``ENDPOINTS`` 派生。

        契约里声明而本轮尚未实现的端点**也登记**，由 :func:`_not_ready`
        返回可读的 501——比 404 诚实：告诉用户「这个功能存在，但还没接数据」，
        而不是让他以为路径写错了。
        """
        out: dict[tuple[str, str], Callable[..., Any]] = {}
        for slug, spec in ENDPOINTS.items():
            handler = self.registry.get(slug) or _not_ready(slug)
            out[(spec["method"], spec["path"])] = handler
        return out


def _not_ready(slug: str) -> Callable[..., Any]:
    """未实现端点的占位处理器（返回「未接数据源」空态信封）。"""

    def _handler(_ctx: Any, _params: dict[str, Any]) -> dict[str, Any]:
        from ..core.envelope import error_envelope

        return error_envelope(
            message=f"工具 {slug} 尚未接入数据源（P3/P4 阶段实现）",
            code="not_ready",
            action="config",
            meta={"slug": slug, "note": "端点已注册，业务逻辑待实现"},
        )

    return _handler


def _safe_join(root: Path, route: str) -> Path | None:
    """把 URL 路径安全地映射到 ``root`` 下的真实文件。

    用 ``resolve()`` + ``commonpath`` 比较，而不是「只取末段」：
    末段方案会丢掉子目录（``/assets/x/y.js`` 全变成 ``y.js``），
    且对 ``..`` 的处理依赖调用方记得做。

    返回 ``None`` 表示越界或非法。

    **Windows 上要防两类异常**（POSIX 不会发生，故易漏）：``/C:/Windows/x`` 的
    盘符会让 ``root / rel`` 丢弃 ``root``（``ntpath.join`` 语义），随后
    ``commonpath`` 抛 ``ValueError: Paths don't have the same drive``——只捕
    ``OSError`` 会让异常逃出请求处理器。故同时捕 ``ValueError``。
    """
    rel = posixpath.normpath(route).lstrip("/")
    if rel.startswith("..") or rel in ("", "."):
        return None
    # 盘符（C:）、反斜杠、NTFS 备用数据流（a.js:Zone.Identifier）：正常资源名不含
    if ":" in rel or "\\" in rel or "\x00" in rel:
        return None
    candidate = (root / rel).resolve()
    try:
        root_resolved = root.resolve()
        if os.path.commonpath([str(candidate), str(root_resolved)]) != str(root_resolved):
            return None
    except (OSError, ValueError):
        return None
    return candidate


def _dispatch_api(
    ctx: ServerContext,
    routes: dict[tuple[str, str], Any],
    method: str,
    route: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """API 分发：把 (method, route, params) 变成信封。

    抽成纯函数便于单测——不碰 socket。
    """
    handler = routes.get((method, route))
    if handler is None:
        if route in {p for (_m, p) in routes}:
            return error_envelope(
                message=f"{route} 不接受 {method} 请求",
                code="method_not_allowed",
                action="fix_input",
            )
        return error_envelope(
            message=f"未知端点：{route}；可用端点见 /api/tools",
            code="not_found",
            action="fix_input",
        )
    handler_ctx = getattr(ctx, "context", ctx)
    return handler(handler_ctx, params)


def _static_target(static: Path, route: str) -> tuple[Path | None, str]:
    """把 URL 解析成 (文件, MIME)。无文件或 MIME 不支持时返回 ``(None, 原因)``。"""
    if route in ("/", "/index.html"):
        index = static / "index.html"
        if not index.is_file():
            return None, "not_built"
        return index, MIME[".html"]
    target = _safe_join(static, route)
    if target is None or not target.is_file():
        return None, "missing"
    ctype = MIME.get(target.suffix.lower())
    if ctype is None:
        return None, "bad_mime"
    return target, ctype


def _status_for(payload: dict[str, Any]) -> int:
    """从信封的 ``meta.code`` 反推 HTTP 状态码。

    分发逻辑是纯函数（返回信封），状态码在这里统一映射——
    这样 ``_dispatch_api`` 可以离线单测，不必关心 HTTP。
    """
    if payload.get("ok") is not False:
        return HTTPStatus.OK
    code = payload.get("meta", {}).get("code")
    if code == "method_not_allowed":
        return HTTPStatus.METHOD_NOT_ALLOWED
    if code == "not_found":
        return HTTPStatus.NOT_FOUND
    if code == "bad_json":
        return HTTPStatus.BAD_REQUEST
    return HTTPStatus.OK


def _cache_header(route: str) -> str:
    """③ 带 hash 的 assets 长缓存；其余 must-revalidate。"""
    if route.startswith("/assets/"):
        return "public, max-age=31536000, immutable"
    return "no-cache"


class _Handler(BaseHTTPRequestHandler):
    """请求处理器基类：只做 socket 读写，业务交给纯函数。

    拆成模块级类（而非 ``make_handler`` 内的闭包）是为了让每个方法都能单独读、
    单独改；闭包版一路涨到 148 行/复杂度 24，门禁直接拦了。
    """

    server_version = "workbench"
    protocol_version = "HTTP/1.1"

    #: 由 ``make_handler`` 在子类上赋值
    ctx: ServerContext
    routes: dict[tuple[str, str], Any]

    # ---------------------------------------------------------------- 输出

    def _send(self, status: int, body: bytes, ctype: str, cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode()
        self._send(status, body, "application/json; charset=utf-8")

    def _send_html(self, status: int, html: str, cache: str = "no-cache") -> None:
        self._send(status, html.encode("utf-8"), "text/html; charset=utf-8", cache=cache)

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A002
        if args and str(args[0]).startswith("5"):
            super().log_message(fmt, *args)

    # ---------------------------------------------------------------- 路由

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_HEAD(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def _handle(self, method: str) -> None:
        route = urlparse(self.path).path
        if route.startswith("/api/"):
            self._serve_api(method, route)
        else:
            self._serve_static(route)

    # ---------------------------------------------------------------- API

    def _serve_api(self, method: str, route: str) -> None:
        try:
            params = self._read_params()
        except _HttpError as exc:
            self._send_json(exc.status, exc.payload)
            return
        payload = _dispatch_api(self.ctx, self.routes, method, route, params)
        self._send_json(_status_for(payload), payload)

    def _read_params(self) -> dict[str, Any]:
        if self.command == "GET":
            qs = parse_qs(urlparse(self.path).query)
            return {k: v[0] if len(v) == 1 else v for k, v in qs.items()}
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        return _parse_json_body(self.rfile.read(length))

    # ---------------------------------------------------------------- 静态

    def _serve_static(self, route: str) -> None:
        target, ctype = _static_target(self.ctx.static_dir, route)
        if target is None:
            self._serve_static_miss(route, ctype)
            return
        self._send(HTTPStatus.OK, target.read_bytes(), ctype, cache=_cache_header(route))

    def _serve_static_miss(self, route: str, reason: str) -> None:
        if reason == "not_built":
            # ⑥ 未构建不是服务器错误 → **200** + 构建指引
            self._send_html(HTTPStatus.OK, NOT_BUILT_HTML)
            return
        msg = {
            "bad_mime": f"不支持的文件类型：{Path(route).suffix}",
            "missing": f"资源不存在：{route}",
        }.get(reason, "前端尚未构建；请先在 / 查看构建指引")
        self._send_json(
            HTTPStatus.NOT_FOUND, error_envelope(message=msg, code="not_found", action="fix_input")
        )


def make_handler(ctx: ServerContext) -> type[BaseHTTPRequestHandler]:
    """把 ctx 绑到处理器子类上（每个服务实例一份，互不干扰）。"""
    routes = ctx.routes()
    return type("Handler", (_Handler,), {"ctx": ctx, "routes": routes})


def _parse_json_body(raw: bytes) -> dict[str, Any]:
    """解析 POST body；非法 JSON 抛 ``_HttpError``（带完整信封）。"""
    try:
        data = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        raise _HttpError(
            HTTPStatus.BAD_REQUEST,
            error_envelope(message="请求体不是合法 JSON", code="bad_json", action="fix_input"),
        ) from None
    if not isinstance(data, dict):
        raise _HttpError(
            HTTPStatus.BAD_REQUEST,
            error_envelope(message="请求体必须是 JSON 对象", code="bad_json", action="fix_input"),
        )
    return data


class _HttpError(Exception):
    """处理器内可直接抛的 HTTP 错误（携带完整信封）。"""

    def __init__(self, status: int, payload: dict[str, Any]) -> None:
        super().__init__(str(status))
        self.status = status
        self.payload = payload


def serve(ctx: ServerContext, *, host: str = HOST, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    """构造并绑定服务器（不阻塞；调用方决定 ``serve_forever`` 还是测试用）。"""
    if host != "127.0.0.1":
        # 硬约束：本地工具不对外可达（DEBT D-07）
        raise ValueError(f"只允许绑定 127.0.0.1，收到 {host!r}")
    return ThreadingHTTPServer((host, port), make_handler(ctx))
