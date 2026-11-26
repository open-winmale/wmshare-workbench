#!/usr/bin/env python3
"""门禁 8：文档内相对链接必须指向真实存在的文件（P6-03）。

只校验**相对路径链接**（含图片）：README / AGENTS / docs 里的
``[文本](target)`` 与 ``![alt](src)``，去掉锚点后按所在文件目录解析，
文件或目录不存在即 FAIL。外链（http/https/mailto）与纯锚点跳过——
外链的死活交给运行时，离线门禁不联网。

为什么值得一个门禁：文档链接坏掉是最廉价的腐烂——改个文件名、挪个
目录，十处引用没人点就没人知道。兄弟仓的经验是「文档引用全部受门禁
校验」（README 里的 ``cli.*`` 调用、``$指标码`` 都有门禁），链接是
同一条纪律的最低配版本。

代码围栏（```` ``` ````）内的内容不扫——示例文本里的假链接不是链接。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _gate import DOCS, FRONTEND, REPO, Result, rel, run_gate  # noqa: E402

#: 链接目标：群 1=路径（去锚点前），群 2=是否图片（不区分用途，留作扩展）。
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
#: 扫描面：根级 markdown + docs/ 全部。frontend 的 README 属构建面，不扫。
SCAN_ROOTS: tuple[Path, ...] = (
    REPO / "README.md",
    REPO / "AGENTS.md",
    REPO / "CONTRIBUTING.md",
    DOCS,
    FRONTEND / "README.md",
)
SKIP_PREFIXES = ("http://", "https://", "mailto:", "#")


def markdown_files() -> list[Path]:
    """根级散文件 + docs/ 递归，存在的才扫。"""
    files: list[Path] = []
    for entry in SCAN_ROOTS:
        if entry.is_file():
            files.append(entry)
        elif entry.is_dir():
            files.extend(sorted(entry.rglob("*.md")))
    return files


def strip_code_fences(lines: list[str]) -> list[tuple[int, str]]:
    """跳过围栏内的行（成对 ``` 之间），返回 (行号, 文本)。"""
    out: list[tuple[int, str]] = []
    fenced = False
    for no, line in enumerate(lines, start=1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            out.append((no, line))
    return out


def check_file(path: Path, result: Result) -> None:
    """单文件：逐条相对链接验证存在性，失败定位到 文件:行。"""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        result.warn(f"{rel(path)} 读取失败，跳过：{exc}")
        return
    for no, line in strip_code_fences(text.splitlines()):
        for match in LINK_RE.finditer(line):
            # 计数口径统一：每条链接都算「检查过」（外链/锚点只跳过验证，
            # 不是没看见）；只有相对路径才做存在性校验
            result.checked += 1
            target = match.group(1)
            if target.startswith(SKIP_PREFIXES):
                continue
            bare = target.split("#", 1)[0]
            if not bare:
                continue
            resolved = (path.parent / bare).resolve()
            if not resolved.exists():
                result.fail(f"{rel(path)}:{no} 链接目标不存在：{target}")


def main() -> int:
    result = Result(name="docs_links")

    files = markdown_files()
    if not files:
        result.fail("没有任何 markdown 文件可扫（扫描面配置错了？）")
        return run_gate("docs_links", lambda: result)

    for path in files:
        check_file(path, result)

    return run_gate("docs_links", lambda: result)


if __name__ == "__main__":
    sys.exit(main())
