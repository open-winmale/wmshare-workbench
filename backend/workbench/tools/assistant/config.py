"""AI 助手的模型配置：环境变量 > ``~/.wmshare/credentials.env`` > 默认值。

**密钥纪律与 wmshare 凭证同源**：只走环境变量或 ``~/.wmshare/credentials.env``，
不入仓库、不入日志、不回显原文（只给尾 4 位）。

三个键（任何 OpenAI 兼容端点都行；默认值以 DeepSeek 为示例）：

- ``WMSHARE_LLM_BASEURL``  默认 ``https://api.deepseek.com``
- ``WMSHARE_LLM_API_KEY``  必填才能启用助手（未配置时工具给引导，不报错砸脸）
- ``WMSHARE_LLM_MODEL``    默认 ``deepseek-chat``

辅助键：``WMSHARE_LLM_MAX_EC``（单轮取数预算，默认 5000）、
``WMSHARE_LLM_TIMEOUT``（秒，默认 180）。

**为什么不复用 ``platform/credentials.py`` 的解析器**：分层规则
（``check_layers``）不允许 tools 直接 import platform；这里的文件解析
刻意保持最小（只认 ``KEY=VALUE`` / ``export KEY=VALUE`` / 引号 / 注释）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

__all__ = ["LLMConfig", "load_config", "redacted"]

DEFAULT_BASEURL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_MAX_EC = 5_000
DEFAULT_TIMEOUT_S = 180
DEFAULT_CRED_PATH = Path.home() / ".wmshare" / "credentials.env"

_KEYS = ("WMSHARE_LLM_BASEURL", "WMSHARE_LLM_API_KEY", "WMSHARE_LLM_MODEL",
         "WMSHARE_LLM_MAX_EC", "WMSHARE_LLM_TIMEOUT")


@dataclass(frozen=True)
class LLMConfig:
    """一次装配、处处只读的模型配置。``api_key`` 为空 = 未启用。"""

    base_url: str
    api_key: str
    model: str
    max_ec: int
    timeout_s: int

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


def load_config(*, env: dict[str, str] | None = None,
                cred_path: Path | None = None) -> LLMConfig:
    """装配配置。``env`` 传入时**只看它**（测试隔离）；否则看真实环境。"""
    source = {k: (env or os.environ).get(k, "") for k in _KEYS}
    # 文件只兜底「环境变量没给的键」——env 显式传入时（测试）同样兜底，
    # 但显式给的空串不算「没给」（用户可能刻意想置空）
    for key, value in _read_env_file(cred_path or DEFAULT_CRED_PATH).items():
        if not source.get(key):
            source[key] = value
    return LLMConfig(
        base_url=(source.get("WMSHARE_LLM_BASEURL") or DEFAULT_BASEURL).rstrip("/"),
        api_key=(source.get("WMSHARE_LLM_API_KEY") or "").strip(),
        model=source.get("WMSHARE_LLM_MODEL") or DEFAULT_MODEL,
        max_ec=_int_or(source.get("WMSHARE_LLM_MAX_EC"), DEFAULT_MAX_EC),
        timeout_s=_int_or(source.get("WMSHARE_LLM_TIMEOUT"), DEFAULT_TIMEOUT_S),
    )


def redacted(config: LLMConfig) -> dict[str, object]:
    """脱敏视图（appinfo / 引导卡用）：绝不回显 key 原文。"""
    host = urlparse(config.base_url).netloc or config.base_url
    return {
        "configured": config.configured,
        "base_host": host,
        "model": config.model,
        "key_tail": config.api_key[-4:] if config.api_key else "",
        "max_ec": config.max_ec,
    }


def _int_or(raw: str | None, default: int) -> int:
    try:
        return int(raw) if raw else default
    except (TypeError, ValueError):
        return default


def _read_env_file(path: Path) -> dict[str, str]:
    """最小 KEY=VALUE 解析（支持 ``export`` 前缀 / 引号 / ``#`` 注释）。"""
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key in _KEYS and value:
            out[key] = value
    return out
