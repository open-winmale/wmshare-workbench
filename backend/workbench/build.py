"""前端产物的**跨平台**构建入口（不依赖 make / bash）。

    python -m workbench.build            # 构建到 workbench/static/
    python -m workbench.build --check    # 只校验产物完整（门禁/CI 用）
    python -m workbench.build --clean    # 清掉产物与 node_modules

**为什么要有这个模块**：``make web`` 需要 GNU make，Windows 默认没有；
而 ``cd frontend && npm ci && npm run build`` 是 POSIX 语法。把构建收进
纯 Python 后，三条命令在任何装了 Node 的机器上都能跑，且参数用列表形式
传给 ``subprocess``（不拼 shell 字符串，跨平台安全）。

**它不负责分发**。用户拿到的 wheel 应当**已含**前端产物（release workflow
构建好再打包），所以 ``pip install`` 的机器不需要 Node——这条边界与
``docs/ARCHITECTURE.md`` §4 的「用户不装 Node」一致。

**为什么构建前要清 ``build/lib``**：``python -m build`` 走的是
``build_py → install_lib → copy_tree``，它**只增不删**。上一次构建留在
``build/lib/workbench/static`` 里的旧 hash 文件会和这次的新文件一起进
wheel（实测：planted 的旧文件照样出现在 wheel 里）。界面看着正常，实际
混着两代产物——这类「看起来没坏」的残留最难发现，所以在这里物理清掉。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

__all__ = ["PACKAGE", "REPO", "STATIC", "main", "verify"]

#: 仓库根（本文件在 ``backend/workbench/`` 下）。
REPO = Path(__file__).resolve().parents[2]
PACKAGE = Path(__file__).resolve().parent
STATIC = PACKAGE / "static"
FRONTEND = REPO / "frontend"
#: ``python -m build`` 的中间目录；残留会污染下一个 wheel。
BUILD_LIB = REPO / "build" / "lib"

#: Node 最低版本（``frontend/package.json`` 的 engines 同款）。
NODE_MIN = "18.18"


def _npm() -> str:
    """定位 npm 可执行文件。Windows 上是 ``npm.cmd``，由 ``which`` 处理。"""
    for name in ("npm", "npm.cmd"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit(
        f"找不到 npm。构建前端需要 Node.js ≥ {NODE_MIN}：\n"
        "  https://nodejs.org/  （或用含界面的预构建 wheel，无需 Node）"
    )


def _run(args: list[str], *, cwd: Path) -> None:
    """跑一个外部命令；失败时抛出带上下文的退出。"""
    print(f"  $ {' '.join(args)}", flush=True)
    try:
        subprocess.run(args, cwd=str(cwd), check=True)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"命令失败（退出码 {exc.returncode}）：{' '.join(args)}") from None
    except FileNotFoundError:
        raise SystemExit(f"命令不存在：{args[0]}") from None


def _show(path: Path) -> str:
    """相对仓库根显示路径；不相关（如装在 site-packages）时显示绝对路径。"""
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def verify() -> list[str]:
    """产物完整性检查。返回问题列表（空 = 通过）。"""
    problems: list[str] = []
    index = STATIC / "index.html"
    if not index.is_file():
        problems.append(f"缺 {_show(index)}；先跑 `python -m workbench.build`")
    assets = STATIC / "assets"
    if not assets.is_dir():
        problems.append(f"缺 {_show(assets)}；前端产物不完整")
    elif not any(assets.iterdir()):
        problems.append(f"{_show(assets)} 是空目录；前端产物不完整")
    return problems


def _clean_build_lib() -> None:
    """清掉 ``build/lib``：``copy_tree`` 只增不删，旧产物会混进 wheel。"""
    if BUILD_LIB.is_dir():
        shutil.rmtree(BUILD_LIB)
        print(f"  清掉 {_show(BUILD_LIB)}（避免旧产物混入 wheel）")


def build() -> int:
    """构建前端产物到 ``workbench/static/``。"""
    if not (FRONTEND / "package.json").is_file():
        raise SystemExit(f"找不到前端工程：{FRONTEND}")
    npm = _npm()
    print("构建前端产物：", flush=True)
    # `npm ci` 严格按 lockfile 安装；没有 lockfile 时退化为 install
    _run(
        [npm, "ci"] if (FRONTEND / "package-lock.json").is_file() else [npm, "install"],
        cwd=FRONTEND,
    )
    _run([npm, "run", "build"], cwd=FRONTEND)

    problems = verify()
    if problems:
        for p in problems:
            print(f"FAIL {p}", file=sys.stderr)
        return 1
    n = len(list((STATIC / "assets").iterdir()))
    print(f"OK   前端产物就绪（{n} 个文件） → {_show(STATIC)}")
    return 0


def clean() -> int:
    """清掉构建产物与缓存（跨平台替代 ``rm -rf`` / ``find -exec``）。"""
    targets = [
        STATIC,
        FRONTEND / "node_modules",
        REPO / "build",
        REPO / "dist",
        REPO / ".pytest_cache",
        REPO / ".ruff_cache",
    ]
    for path in targets:
        if path.is_dir():
            shutil.rmtree(path)
            print(f"  删除 {_show(path)}")
    # 递归删 __pycache__（Path.rglob 不跟随符号链接，安全）
    for cache in REPO.rglob("__pycache__"):
        if ".git" in cache.parts or "node_modules" in cache.parts:
            continue
        shutil.rmtree(cache, ignore_errors=True)
    print("OK   已清理")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m workbench.build",
        description="构建前端产物到 workbench/static/（跨平台，不依赖 make）",
    )
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="只校验产物是否存在且完整（不构建）")
    mode.add_argument("--clean", action="store_true", help="清理构建产物与缓存")
    args = ap.parse_args(argv)

    if args.clean:
        return clean()
    if args.check:
        problems = verify()
        for p in problems:
            print(f"FAIL {p}", file=sys.stderr)
        if not problems:
            print("OK   前端产物完整")
        return 1 if problems else 0
    _clean_build_lib()
    return build()


if __name__ == "__main__":
    raise SystemExit(main())
