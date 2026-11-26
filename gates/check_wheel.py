#!/usr/bin/env python3
"""门禁 9：wheel 必须内含前端产物，且**必须是这次的产物**。

**这条门禁存在的原因**：`wmshare-tools` 的 `web_dist/` 被 gitignore 且未列入
`package-data`，结果是 `pip install` 拿到的包**既没有新 UI 也没有旧 UI**——
用户以为装了个界面，打开却什么都没有。本门禁把根因堵死。

**2026-11-26 修了三处静默缺陷**（都会让「门禁绿、产物错」）：

1. **陈旧 wheel 判绿**：原来只取 ``dist/`` 里 mtime 最新的 ``*.whl``，不检查它
   是否比 ``static/`` 新。实测本机 11-25 的旧 wheel 引用的还是
   ``index-4rRQcC-S.js``，而产物早已是 ``index-DjAHLk_6.js``——门禁照样 OK。
   现在要求 wheel 不早于 ``static/index.html``。
2. **不校验 index.html 引用的资源真在包里**：旧断言只看「有没有任意
   ``/static/assets/``」，hash 名对不上也能过。现在逐个解析 ``src``/``href``
   并断言在 namelist 里（能抓到 ``build/lib`` 残留这类「拷了一半」）。
3. **不挡源码树泄漏**：新增 ``frontend/``、``node_modules/`` 不得进包。

**不在 `make check` 里**：它需要先有 wheel，而 ``make check`` 是「clone 下来
零准备就能跑」的八个门禁。由 ``make wheel`` 与 CI/release 的 wheel job 调用。
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _gate import REPO, STATIC, Result, rel, run_gate  # noqa: E402

DIST = REPO / "dist"
#: ``index.html`` 里引用产物的两种写法（Vite 产 ``./assets/xxx-hash.js``）。
ASSET_RE = re.compile(r'(?:src|href)="\.?/?((?:assets/)[^"]+)"')


def pick_wheel(explicit: str) -> Path | None:
    """要校验的 wheel：``--wheel`` 优先，否则 ``dist/`` 里最新的那个。"""
    if explicit:
        return Path(explicit).expanduser().resolve()
    if not DIST.is_dir():
        return None
    wheels = sorted(DIST.glob("*.whl"), key=lambda p: p.stat().st_mtime)
    return wheels[-1] if wheels else None


def check_freshness(wheel: Path, result: Result) -> None:
    """wheel 不得比前端产物旧——否则校验的是上一轮构建。"""
    index = STATIC / "index.html"
    if not index.is_file():
        return  # 没产物时由 in-wheel 断言报错，这里不重复
    result.checked += 1
    if wheel.stat().st_mtime < index.stat().st_mtime:
        result.fail(
            f"{wheel.name} 比 {rel(index)} 旧——校验的是上一次构建的包。"
            f"改动前端后请重跑 `make wheel`"
        )


def check_assets(zf: zipfile.ZipFile, result: Result) -> str | None:
    """校验 index.html 引用的资源在包内。返回 index 成员名（可能为 None）。"""
    names = set(zf.namelist())
    index_name = next((n for n in names if n.endswith("workbench/static/index.html")), None)
    if index_name is None:
        return None
    prefix = index_name.rsplit("index.html", 1)[0]
    html = zf.read(index_name).decode("utf-8", "replace")
    result.checked += 1
    missing = [r for r in ASSET_RE.findall(html) if f"{prefix}{r}" not in names]
    if missing:
        shown = ", ".join(missing[:5]) + ("…" if len(missing) > 5 else "")
        result.fail(
            f"index.html 引用了包内不存在的资源：{shown}；产物只拷了一半（build/lib 残留？）"
        )
    return index_name


def main(argv: list[str] | None = None) -> Result:
    ap = argparse.ArgumentParser(description="断言 wheel 内含前端产物")
    ap.add_argument("--wheel", default="", help="指定 wheel 路径（默认 dist/ 最新）")
    args, _ = ap.parse_known_args(argv)

    result = Result("wheel")
    wheel = pick_wheel(args.wheel)
    if wheel is None or not wheel.is_file():
        result.fail(
            f"找不到 wheel（{args.wheel or rel(DIST) + '/*.whl'}）；"
            f"请先跑 `make wheel`（或 python -m build --wheel）"
        )
        return result

    result.checked += 1
    try:
        with zipfile.ZipFile(wheel) as zf:
            index_name = check_assets(zf, result)
            names = zf.namelist()
    except zipfile.BadZipFile:
        result.fail(f"{rel(wheel)} 不是合法 zip")
        return result

    check_freshness(wheel, result)

    result.checked += 1
    if index_name is None:
        result.fail(
            f"{wheel.name} 不含 workbench/static/index.html —— "
            f"用户安装后打开界面会看到空白。检查 pyproject.toml 的 package-data "
            f"是否覆盖 static/**，以及构建前是否跑过 `python -m workbench.build`"
        )

    for banned in ("node_modules", "frontend/"):
        result.checked += 1
        leaked = [n for n in names if banned in n]
        if leaked:
            result.fail(
                f"{wheel.name} 含 {banned}（{len(leaked)} 个条目）；"
                f"请在 package-data / include-package-data 里排除"
            )

    result.checked += 1
    if index_name and not any("workbench/static/assets/" in n for n in names):
        result.fail(
            f"{wheel.name} 有 index.html 但没有 static/assets/*；产物不完整（emptyOutDir 清掉了？）"
        )

    if STATIC.is_dir():
        result.checked += 1
        if not (STATIC / "index.html").is_file():
            result.warn("backend/workbench/static/ 存在但缺 index.html；本地构建可能不完整")
    return result


if __name__ == "__main__":
    raise SystemExit(run_gate("wheel", main))
