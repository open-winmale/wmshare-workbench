"""AI 助手工具清单契约：清单即契约，上游改名这里先红。

**防编造**（最高优先级规则「先查已有指标再写代码」的助手版）：
``registry.json`` 里的每个 target 必须在 wmshare 目录里真实存在；
facade 的 (ns, method) 必须真实可达；params 名必须 ⊆ 目录声明的参数名。
SDK 未安装时整组诚实跳过（CI 装 ``.[data]`` 真跑）——与 ``test_hub`` 同款。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from workbench.tools.assistant import executor
from workbench.tools.assistant.skills import load_skills

REGISTRY_PATH = (Path(__file__).resolve().parent.parent
                 / "backend" / "workbench" / "tools" / "assistant" / "registry.json")

VALID_COSTS = {"auto", "medium", "high", "local"}
VALID_KINDS = {"call", "facade", "local"}


def _entries() -> list[dict]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["tools"]


class TestRegistryShape:
    def test_tools_present_and_capped_per_domain(self):
        entries = _entries()
        assert len(entries) >= 10, "清单是助手的数据面，不该是空壳"
        by_domain: dict[str, list] = {}
        for entry in entries:
            by_domain.setdefault(entry["domain"], []).append(entry)
        for domain, group in by_domain.items():
            assert len(group) <= 6, f"{domain} 域工具过多（注意力稀释上限 6）"

    def test_required_fields(self):
        for entry in _entries():
            assert entry["id"] and entry["domain"]
            assert entry["kind"] in VALID_KINDS, entry["id"]
            assert entry["target"], entry["id"]
            assert entry.get("cost") in VALID_COSTS, entry["id"]
            assert entry.get("evidence"), entry["id"]
            assert isinstance(entry.get("params", []), list)

    def test_ids_unique(self):
        ids = [e["id"] for e in _entries()]
        assert len(ids) == len(set(ids))

    def test_every_domain_has_skill(self):
        """清单里的每个域都要有 SKILL.md（域口径纪律），反之亦然。"""
        skill_ids = {s.id for s in load_skills()}
        for domain in {e["domain"] for e in _entries()}:
            assert domain in skill_ids, f"域 {domain} 缺 skills/{domain}/SKILL.md"

    def test_dividend_detail_is_history_not_snapshot(self):
        """用户实锤回归：问「分红明细」必须取明细接口，不能用股息快照冒充。"""
        by_id = {e["id"]: e for e in _entries()}
        detail, yield_ = by_id["dividend_history"], by_id["dividend_yield"]
        assert detail["target"] == "dividend.history"
        assert detail["kind"] == "facade"
        assert yield_["target"] == "bonus.snapshot"
        assert all(e["target"] != "dividend.snapshot" for e in _entries()), \
            "dynamic 快照不是分红明细"

    def test_llm_tools_have_json_schema_shape(self):
        for domain in ("market", "fundamental"):
            for tool in executor.to_llm_tools(executor.tools_for_domain(domain)):
                assert set(tool) >= {"name", "description", "parameters"}
                assert tool["parameters"]["type"] == "object"

    def test_llm_tools_use_schema_standard_types(self):
        """参数类型必须是 JSON Schema 标准值——``int`` 这类目录惯用名
        会被严格校验的供应商（智谱 1210 实测）整请求拒掉。"""
        valid = {"string", "integer", "number", "boolean", "array", "object"}
        for entry in _entries():
            for tool in executor.to_llm_tools([entry]):
                for prop in tool["parameters"]["properties"].values():
                    assert prop["type"] in valid, (entry["id"], prop["type"])


class TestTargetsAgainstCatalog:
    """对照 wmshare 真实目录——上游改名/删接口时这组先红。"""

    pytest.importorskip("wmshare", reason="wmshare SDK 未安装（pip install '.[data]' 后生效）")

    def _catalog(self):
        import wmshare

        return wmshare.load()

    def test_call_targets_exist(self):
        cat = self._catalog()
        for entry in _entries():
            if entry["kind"] != "call":
                continue
            fn = cat.function(entry["target"])  # 不存在会抛错 → 用例红
            declared = {p["name"] for p in entry.get("params") or []}
            upstream = {p["name"] for p in (fn.get("params") or [])}
            # 上游必填参数必须被清单声明（否则执行器必然缺参）
            upstream_required = {p["name"] for p in (fn.get("params") or [])
                                 if p.get("required")}
            assert upstream_required <= declared, \
                f"{entry['target']}: 上游必填 {upstream_required - declared} 未声明"

    def test_facade_methods_exist(self):
        import wmshare

        client = wmshare.Client.from_env(market="cn")
        for entry in _entries():
            if entry["kind"] != "facade":
                continue
            ns = getattr(client, entry["ns"])
            assert getattr(ns, entry["method"], None) is not None, \
                f"{entry['ns']}.{entry['method']} 不存在（清单编造？）"
