#!/usr/bin/env python3
"""门禁 3：设计令牌约束（``docs/DESIGN_SYSTEM.md`` §2、§13）。

三层校验：

1. **令牌齐全**：``tokens.js``/``tokens.css`` 里必须声明全部
   ``required_in_both_themes``（双主题各一套）与 ``required_any``。
   缺一个就意味着某组件会退化为硬编码色值。
2. **禁止裸色值**：除白名单文件外，``.vue`` / ``.css`` / ``.ts`` 中不得出现
   ``#rgb`` / ``#rrggbb`` / ``rgb(`` / ``rgba(`` / ``hsl(``。
3. **禁止非标像素**：``forbidden_px_values`` 里的值（7/13/18/22/26/34）不得出现在
   间距/圆角相关属性里——它们通常是「手调一下」的痕迹，会破坏 4px 节奏。

P0 阶段前端目录尚不存在，本门禁只校验基线自身的一致性（origin 覆盖率），
P1 落组件后自动开始校验真实文件。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _gate import FRONTEND, Result, load_baseline, rel, run_gate  # noqa: E402

HEX = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
#: Vue 的 ``<template #slot>`` / ``v-slot:slot`` 简写——**不是颜色**。
#:
#: 不加这条排除时，``#fee``（一个合法的槽位名，三字符全是 hex 字母）会被
#: 判成「裸色值」。这个误报会逼开发者把槽位改名（``#fee`` → ``#fee_amount``），
#: 而不是去修真正的问题——**误报的代价是规则被绕过**。
VUE_SLOT = re.compile(r"(?:<template\s+|v-slot:)#[A-Za-z][\w-]*")
FUNC_COLOR = re.compile(r"\b(?:rgba?|hsla?)\s*\(")
TOKEN_DECL = re.compile(r"--wb-([a-z0-9-]+)\s*:")
SPACING_PROP = re.compile(
    r"\b(?:margin|padding|gap|row-gap|column-gap|border-radius|"
    r"top|right|bottom|left|width|height)\b[^;{}]*?:\s*[^;{}]*"
    r"\b(\d+)px\b")


def declared_tokens(text: str) -> set[str]:
    """抽取文件中声明的 ``--wb-xxx`` 令牌名（不含前缀）。"""
    return set(TOKEN_DECL.findall(text))


#: 语义派生令牌：其 origin 归到对应基础色，不单独要求说明。
DERIVED_TOKENS = frozenset({
    "row-alt", "accent-bg", "up-bg", "down-bg", "seq-low", "seq-high",
})


def _has_origin(name: str, origin: dict) -> bool:
    """判断某令牌是否在 origin 中有说明。

    支持两种写法：精确键（``dur-base``）与区间键（``chart-1..12``）。
    """
    if name in origin:
        return True
    for key in origin:
        if ".." not in key:
            continue
        head, _, tail = key.partition("..")
        prefix = head.rstrip("0123456789").rstrip("-")
        if not name.startswith(prefix + "-"):
            continue
        try:
            idx = int(name[len(prefix) + 1:])
            hi = int(tail.strip().lstrip("-"))
            lo = int(head[len(prefix) + 1:]) if head[len(prefix) + 1:].isdigit() else 1
        except ValueError:
            continue
        if lo <= idx <= hi:
            return True
    return False


def check_baseline_integrity(result: Result, tokens: dict) -> None:
    """基线自洽：每个必需令牌都要有「移植/自定」说明。

    这是 ``DESIGN_SYSTEM.md`` §13 的落地：令牌一旦被消费，改它就是全局重构，
    所以每个令牌必须有人对其来源负责。
    """
    required = set(tokens.get("required_in_both_themes") or [])
    extra = set(tokens.get("required_any") or [])
    origin: dict = tokens.get("origin") or {}

    for name in sorted(required | extra):
        result.checked += 1
        if name in DERIVED_TOKENS:
            continue
        if not _has_origin(name, origin):
            result.warn(f"令牌 --wb-{name} 未在 origin 中说明移植/自定"
                        f"（DESIGN_SYSTEM §13 要求）")


#: 主题块选择器：暗色用 ``:root``，亮色用 ``[data-theme="daylight"]``。
THEME_BLOCKS = (
    ("obsidian", re.compile(r":root\s*\{")),
    ("daylight", re.compile(r"""\[data-theme=["']daylight["']\]\s*\{""")),
)


def split_theme_blocks(text: str) -> dict[str, str]:
    """按主题切分 ``tokens.css``，返回 ``{主题名: 块内文本}``。

    上一版只在全文里找一次令牌名，于是「只写在 ``:root`` 里」也能通过——
    而 ``required_in_both_themes`` 的语义恰恰是**两套主题都要有**。
    双主题缺一个的直接后果是切主题时该颜色不生效，落到浏览器默认值。
    """
    out: dict[str, str] = {}
    for name, pat in THEME_BLOCKS:
        m = pat.search(text)
        if not m:
            continue
        depth = 0
        start = m.end() - 1
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    out[name] = text[start + 1:i]
                    break
    return out


def check_token_file(result: Result, tokens: dict) -> None:
    """校验 ``tokens.css`` 里两套主题各自声明齐全。"""
    candidates = [FRONTEND / "src" / "styles" / "tokens.css",
                  FRONTEND / "src" / "styles" / "tokens.ts"]
    existing = [p for p in candidates if p.is_file()]
    if not existing:
        return

    required = list(tokens.get("required_in_both_themes") or [])
    extra = list(tokens.get("required_any") or [])
    for path in existing:
        text = path.read_text(encoding="utf-8")
        blocks = split_theme_blocks(text)
        result.checked += len(required) * 2 + len(extra)

        if not blocks:
            result.fail(f"{rel(path)} 未找到主题块；需同时声明 :root 与 "
                        f'[data-theme="daylight"]')
            continue

        for theme in ("obsidian", "daylight"):
            block = blocks.get(theme)
            if block is None:
                result.fail(f'{rel(path)} 缺少 {theme} 主题块'
                            f'（:root 或 [data-theme="daylight"]）')
                continue
            found = declared_tokens(block)
            for name in required:
                if name not in found:
                    result.fail(f"{rel(path)} 的 {theme} 主题缺少令牌 "
                                f"--wb-{name}（required_in_both_themes；"
                                f"缺了会导致切主题时该项回落到浏览器默认值）")

        found_all = declared_tokens(text)
        for name in extra:
            if name not in found_all:
                result.fail(f"{rel(path)} 缺少令牌 --wb-{name}")


def check_raw_values(result: Result, tokens: dict) -> None:
    """组件与样式中禁止裸色值 / 非标像素。"""
    if not FRONTEND.is_dir():
        return
    allowed = {str(p) for p in (tokens.get("allowed_raw_hex_files") or [])}
    forbidden_px = {int(v) for v in (tokens.get("forbidden_px_values") or [])}

    for path in sorted(FRONTEND.rglob("*")):
        if not path.is_file() or "node_modules" in path.parts:
            continue
        if path.suffix not in {".vue", ".css", ".scss", ".ts"}:
            continue
        key = rel(path)
        if key in allowed:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        result.checked += 1
        for i, line in enumerate(text.splitlines(), 1):
            # 先剥掉 Vue 槽位简写（`<template #fee>`），再找裸色值
            probe = VUE_SLOT.sub("", line)
            if HEX.search(probe) or FUNC_COLOR.search(probe):
                result.fail(f"{key}:{i} 出现裸色值；请改用 var(--wb-*) 令牌")
            m = SPACING_PROP.search(line)
            if m and int(m.group(1)) in forbidden_px:
                result.fail(f"{key}:{i} 出现非标像素 {m.group(1)}px；"
                            f"请用 4px 基准的 --wb-sp-* / --wb-r-*")


def main() -> Result:
    result = Result("tokens")
    tokens = load_baseline("tokens")
    check_baseline_integrity(result, tokens)
    check_token_file(result, tokens)
    check_raw_values(result, tokens)
    return result


if __name__ == "__main__":
    raise SystemExit(run_gate("tokens", main))
