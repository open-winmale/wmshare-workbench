"""CLI 入口：``workbench``。

    workbench                    启动服务（有凭证→自有额度，无凭证→免注册真实数据）
    workbench --port 8788         指定端口
    workbench --version           打印版本
"""

from __future__ import annotations

import argparse
import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="workbench",
        description="wmshare 投研工作台（本地 · 零第三方运行依赖）")
    p.add_argument("--version", action="store_true", help="打印版本")
    p.add_argument("--port", type=int, default=8787, help="监听端口（默认 8787）")
    p.add_argument("--db", default=None,
                   help="SQLite 路径（默认 ~/.wmshare/workbench.db）")
    args = p.parse_args(argv)

    if args.version:
        print(f"workbench {__version__}")
        return 0

    from .bootstrap import run_server
    from .platform.store import Store

    store = Store(args.db) if args.db else None
    try:
        run_server(port=args.port, store=store)
    except ValueError as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
