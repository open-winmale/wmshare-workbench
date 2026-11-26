"""凭证解析：本库 > 环境变量 > ``~/.wmshare/credentials.env``。

**为什么是本库最优先**：用户在页面上粘贴的 Key 是他**刚刚明确表达**的意图；
若被一个一年前写在 shell profile 里的环境变量盖掉，排查起来极其痛苦。

**为什么读写都在这层**：凭证是最敏感的数据，分散在多处会让「清干净」变成不可能。
写入走「临时文件 + ``os.replace``」原子替换，避免半写文件让服务起不来。
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "DEFAULT_CRED_PATH",
    "ENV_ID_KEYS",
    "ENV_SECRET_KEYS",
    "ResolvedCredentials",
    "read_credentials_file",
    "resolve",
    "write_credentials_file",
]

#: SDK 的凭证文件路径（与本项目同源，便于统一备份/清理）。
DEFAULT_CRED_PATH = Path.home() / ".wmshare" / "credentials.env"

#: 兼容 SDK 的新旧两套环境变量名。
ENV_ID_KEYS = ("WMSHARE_CLIENT_ID", "OPEN_PLATFORM_CLIENT_ID")
ENV_SECRET_KEYS = ("WMSHARE_CLIENT_SECRET", "OPEN_PLATFORM_CLIENT_SECRET")


@dataclass(frozen=True)
class ResolvedCredentials:
    """解析结果。``source`` 说明来源，便于 UI 显示「当前用的是哪套凭证」。"""

    client_id: str
    client_secret: str
    market: str = "cn"
    #: ``store`` / ``env`` / ``file`` / ``none``
    source: str = "none"

    @property
    def present(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def redacted(self) -> dict[str, Any]:
        """供 ``/api/appinfo`` 返回——**绝不返回 secret 原文**。"""
        return {
            "configured": self.present,
            "source": self.source,
            "client_id_tail": self.client_id[-4:] if self.client_id else "",
            "market": self.market,
        }


def _parse_env_file(text: str) -> dict[str, str]:
    """解析 ``KEY=VALUE`` 行；支持 ``export`` 前缀、``#`` 注释、引号。"""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def read_credentials_file(path: Path | None = None) -> dict[str, str]:
    """读凭证文件；不存在或不可读返回 ``{}``（不抛——缺文件是正常状态）。"""
    p = path or DEFAULT_CRED_PATH
    try:
        return _parse_env_file(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return {}


def write_credentials_file(client_id: str, client_secret: str,
                           market: str = "cn",
                           path: Path | None = None) -> Path:
    """原子写入凭证文件，权限 0600。

    先写同目录临时文件再 ``os.replace``：直接覆写的话，进程在写一半时被杀
    会留下一个残缺文件，服务下次启动就读不到凭证。
    """
    p = path or DEFAULT_CRED_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    body = (f"WMSHARE_CLIENT_ID={client_id}\n"
            f"WMSHARE_CLIENT_SECRET={client_secret}\n"
            f"WMSHARE_MARKET={market}\n")
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".cred-", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.chmod(tmp, 0o600)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return p


def _from_env(env: dict[str, str]) -> tuple[str, str]:
    cid = next((env[k] for k in ENV_ID_KEYS if env.get(k)), "")
    sec = next((env[k] for k in ENV_SECRET_KEYS if env.get(k)), "")
    return cid, sec


def _from_store(store: Any) -> ResolvedCredentials | None:
    """第一优先级：页面保存的凭证。"""
    if store is None:
        return None
    try:
        row = store.get_credentials()
    except Exception:  # noqa: BLE001 - 库读失败不该阻断启动
        return None
    if not (row and row.get("client_id") and row.get("client_secret")):
        return None
    return ResolvedCredentials(client_id=row["client_id"],
                               client_secret=row["client_secret"],
                               market=row.get("market") or "cn",
                               source="store")


def _from_env(environ: dict[str, str]) -> ResolvedCredentials | None:
    """第二优先级：环境变量。"""
    cid = next((environ[k] for k in ENV_ID_KEYS if environ.get(k)), "")
    sec = next((environ[k] for k in ENV_SECRET_KEYS if environ.get(k)), "")
    if not (cid and sec):
        return None
    return ResolvedCredentials(client_id=cid, client_secret=sec,
                               market=environ.get("WMSHARE_MARKET") or "cn",
                               source="env")


def _from_file(cred_path: Path | None) -> ResolvedCredentials | None:
    """第三优先级：``~/.wmshare/credentials.env``。"""
    data = read_credentials_file(cred_path)
    cid = next((data[k] for k in ENV_ID_KEYS if data.get(k)), "")
    sec = next((data[k] for k in ENV_SECRET_KEYS if data.get(k)), "")
    if not (cid and sec):
        return None
    return ResolvedCredentials(client_id=cid, client_secret=sec,
                               market=data.get("WMSHARE_MARKET") or "cn",
                               source="file")


def resolve(
    store: Any = None,
    *,
    env: dict[str, str] | None = None,
    cred_path: Path | None = None,
) -> ResolvedCredentials:
    """按优先级解析凭证：**本库 > 环境变量 > 凭证文件**。

    用户刚在页面上粘贴的 Key 必须赢过一年前写在 shell profile 里的环境变量
    ——否则「我明明换了 Key 怎么还是老的」会极难排查。

    **任何一级都要 id 与 secret 都齐才算命中**：只有一半视为未配置，
    因为 SDK 对半套凭证会抛 ``AuthError``。

    演示模式不走本函数（``bootstrap`` 直接构造空凭证），
    以免读到真实凭证让 ``/api/appinfo`` 显示 ``configured: true``。
    """
    environ = os.environ if env is None else env
    for candidate in (_from_store(store), _from_env(environ),
                      _from_file(cred_path)):
        if candidate is not None:
            return candidate
    return ResolvedCredentials(client_id="", client_secret="", source="none")
