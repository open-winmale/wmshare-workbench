#!/usr/bin/env python3
"""工作台启动入口。

把 ``backend/`` 注入 ``sys.path`` 后转交 ``workbench.__main__``。
之所以不要求 ``pip install -e .``：本地工具的第一要求是 clone 下来就能跑
（见 docs/ARCHITECTURE.md「为什么不套 src/」）。

用法::

    python run.py --port 8787
"""

from __future__ import annotations

import sys
from pathlib import Path

#: 仓库根 → backend/ 才是包所在，注入后 ``import workbench`` 可用。
BACKEND = Path(__file__).resolve().parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def main(argv: list[str] | None = None) -> int:
    from workbench.__main__ import main as entry
    return entry(argv)


if __name__ == "__main__":
    raise SystemExit(main())
