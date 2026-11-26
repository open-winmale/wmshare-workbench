#!/usr/bin/env python3
"""门禁 8：wheel 必须内含前端产物（``docs/ARCHITECTURE.md`` §交付）。

**这条门禁存在的原因**：`wmshare-tools` 的 `web_dist/` 被 gitignore 且未列入
`package-data`，结果是 `pip install` 拿到的包**既没有新 UI 也没有旧 UI**——
用户以为装了个界面，打开却什么都没有。它的修复是在启动时加横幅提示，
根因（打包缺产物）仍在。

本门禁把根因堵死：构建 wheel 后断言 `static/index.html` 在包体内。
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _gate import REPO, STATIC, Result, rel, run_gate  # noqa: E402

DIST = REPO / "dist"


def latest_wheel() -> Path | None:
    if not DIST.is_dir():
        return None
    wheels = sorted(DIST.glob("*.whl"), key=lambda p: p.stat().st_mtime)
    return wheels[-1] if wheels else None


def main() -> Result:
    result = Result("wheel")
    wheel = latest_wheel()
    if wheel is None:
        result.fail("dist/ 下没有 wheel；请先跑 `make wheel`（或 python -m build）")
        return result

    result.checked += 1
    try:
        names = zipfile.ZipFile(wheel).namelist()
    except zipfile.BadZipFile:
        result.fail(f"{rel(wheel)} 不是合法 zip")
        return result

    index = [n for n in names if n.endswith("workbench/static/index.html")]
    result.checked += 1
    if not index:
        result.fail(
            f"{wheel.name} 不含 workbench/static/index.html —— "
            f"用户安装后打开界面会看到空白。"
            f"检查 pyproject.toml 的 package-data 是否覆盖 static/**，"
            f"以及构建前是否跑过 `make web`")

    # node_modules 绝不能进包（JupyterLab 明确同时排除，否则百 MB 级 wheel）
    result.checked += 1
    leaked = [n for n in names if "node_modules" in n]
    if leaked:
        result.fail(f"{wheel.name} 含 node_modules（{len(leaked)} 个条目）；"
                    f"请在 package-data 排除")

    # 静态产物应至少有一个 assets 文件（否则 index.html 引用的 JS 缺失）
    result.checked += 1
    has_assets = any("/static/assets/" in n for n in names)
    if index and not has_assets:
        result.fail(f"{wheel.name} 有 index.html 但没有 static/assets/*；"
                    f"产物不完整（是否 emptyOutDir 清掉了？）")

    if STATIC.is_dir():
        result.checked += 1
        if not (STATIC / "index.html").is_file():
            result.warn("backend/workbench/static/ 存在但缺 index.html；"
                        "本地构建可能不完整")
    return result


if __name__ == "__main__":
    raise SystemExit(run_gate("wheel", main))
