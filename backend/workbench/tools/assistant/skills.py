"""技能加载：SKILL.md 即数据——新技能 = 放文件即接上，零代码。

借鉴平台技能仓库的组织方式（frontmatter 元数据 + 正文纪律卡），
保留最小可移植子集：

```
skills/<domain>/SKILL.md
---
name: fundamental
display_name: 基本面
description: 财报 / 估值 / 分红等公司基本面数据（一行，系统提示的域卡片就显示它）
when_to_use: 用户问估值高低、赚钱能力、分红时
---

正文 = 该数据域的口径纪律（单位 / 分位 / 缺失语义 / 工具用法要点），
由 ``read_skill`` 按需读取。
```

**外置扩展**：``~/.wmshare/workbench/skills/<domain>/SKILL.md`` 覆盖同名内置
（或新增 id）——用户/后续版本扩展技能面不需要改代码。启动时扫描，
一轮对话内技能清单保持不变（保证系统提示字节稳定，吃供应商前缀缓存）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = ["Skill", "load_skills", "domain_cards"]

_BUILTIN_DIR = Path(__file__).resolve().parent / "skills"
#: 用户外置技能目录（覆盖同名内置 id）。
USER_SKILLS_DIR = Path.home() / ".wmshare" / "workbench" / "skills"


@dataclass(frozen=True)
class Skill:
    """一个数据域的口径纪律：frontmatter 元数据 + 正文。"""

    id: str
    display_name: str
    description: str
    when_to_use: str
    body: str
    path: str


def load_skills(extra_dir: Path | None = None) -> list[Skill]:
    """扫描内置 + 外置技能目录；外置同名 id 覆盖内置。

    解析失败的单个技能**跳过并保留其余**（一个坏文件不拖垮助手），
    跳过行为由调用方通过日志/测试观察——不在启动时静默吞。
    """
    merged: dict[str, Skill] = {}
    for base in (_BUILTIN_DIR, USER_SKILLS_DIR, *( [extra_dir] if extra_dir else [] )):
        for path in sorted(Path(base).glob("*/SKILL.md")):
            skill = _parse(path)
            if skill is not None:
                merged[skill.id] = skill
    return [merged[k] for k in sorted(merged)]


def domain_cards(skills: list[Skill]) -> str:
    """系统提示里的域卡片（每域一行：id + 用途 + 何时读全文）。"""
    lines = []
    for s in skills:
        use = f"；用于：{s.when_to_use}" if s.when_to_use else ""
        lines.append(f"- {s.id}（{s.display_name}）：{s.description}{use}")
    return "\n".join(lines)


def _parse(path: Path) -> Skill | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    head, _, body = text[3:].partition("---")
    meta: dict[str, str] = {}
    for line in head.splitlines():
        key, _, value = line.partition(":")
        key = key.strip()
        if key and value:
            meta[key] = value.strip()
    skill_id = meta.get("name") or path.parent.name
    return Skill(
        id=skill_id,
        display_name=meta.get("display_name") or skill_id,
        description=meta.get("description") or "",
        when_to_use=meta.get("when_to_use") or "",
        body=body.strip(),
        path=str(path),
    )
