"""wmshare 投研工作台。

以 wmshare SDK 为数据层、以工作台为价值展现层的本地投研工具。

设计原则（见 ``docs/DESIGN_SYSTEM.md``）：口径优先于美观 · 不骗人 · 成本可见 ·
不替用户判断。

运行期零第三方依赖；wmshare 为可选运行时依赖，未安装时进入「未接入」态。
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
