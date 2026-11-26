"""AI 助手离线测试：循环/预算/来源账/门/端点/存储，全部 FakeLLM 零网络。

**这组测试抓的是单 agent 的不变量**：

- 工具循环能被脚本化的假模型驱动（取数轮 → 成稿轮）；
- 工具面按数据域分组，口径全文按需 ``read_skill``；
- 预算与轮数上限必须在「模型不听话一直要取数」时兜得住；
- 来源账由宿主编号，模型只见「来源 n：」前缀；
- chat 的两道门（数据源 / 模型）在进 agent 之前拦住。
"""

from __future__ import annotations

import json
import time
import pathlib

import pytest
from shape_data import shape_for
from workbench.bootstrap import build_context
from workbench.client.fetchers import FakeFetcher
from workbench.platform.store import Store


# ================================================================ 假模型

class ScriptedLLM:
    """按脚本应答的假 ``chat_stream``。``{"tool": id, "args": {...}}`` 表示
    一次工具调用；``{"text": ...}`` 表示最终回答（经 text_delta 流出）。"""

    def __init__(self, turns: list[dict]):
        self.turns = list(turns)
        self.calls: list[dict] = []

    def __call__(self, config, *, system, messages, tools, on_event):
        self.calls.append({"system": system, "messages": list(messages)})
        item = self.turns.pop(0) if self.turns else {"text": "（脚本已耗尽）"}
        if "tool" in item:
            return [{"id": f"c{len(self.calls)}", "name": item["tool"],
                     "arguments": json.dumps(item.get("args") or {})}]
        on_event({"type": "text_delta", "text": item.get("text", "")})
        return []


@pytest.fixture()
def scripted(monkeypatch):
    def _install(turns):
        fake = ScriptedLLM(turns)
        monkeypatch.setattr("workbench.tools.assistant.llm.chat_stream", fake)
        return fake

    return _install


@pytest.fixture()
def ctx(tmp_path: pathlib.Path):
    return build_context(fetcher=FakeFetcher(resolver=shape_for),
                         store=Store(tmp_path / "t.db"))


@pytest.fixture()
def llm_env(monkeypatch, tmp_path):
    """配置好的模型环境 + 转写目录隔离（不写真实 ~/.wmshare）。"""
    monkeypatch.setenv("WMSHARE_LLM_API_KEY", "test-key-1234")
    monkeypatch.delenv("WMSHARE_LLM_BASEURL", raising=False)
    monkeypatch.delenv("WMSHARE_LLM_MODEL", raising=False)
    from workbench.tools.assistant import jobs

    monkeypatch.setattr(jobs, "TRANSCRIPT_DIR", tmp_path / "transcripts")


# ================================================================ 单元

class TestLedger:
    def test_numbers_from_one_and_dedupes(self):
        from workbench.tools.assistant.ledger import SourceLedger

        ledger = SourceLedger()
        assert ledger.add(kind="行情", title="快照 · sym=600519") == 1
        assert ledger.add(kind="行情", title="日K · sym=600519") == 2
        assert ledger.add(kind="行情", title="快照 · sym=600519") == 1, "同键去重"
        assert len(ledger.to_list()) == 2

    def test_cap_24(self):
        from workbench.tools.assistant.ledger import MAX_SOURCES, SourceLedger

        ledger = SourceLedger()
        for i in range(MAX_SOURCES + 3):
            n = ledger.add(kind="x", title=f"证据{i}")
            if i < MAX_SOURCES:
                assert n == i + 1
            else:
                assert n is None, "超上限必须返回 None（模型据此收束）"

    def test_prefix_format(self):
        from workbench.tools.assistant.ledger import SourceLedger

        ledger = SourceLedger()
        n = ledger.add(kind="行情", title="现价 · 600519", as_of="2026-11-27")
        text = ledger.prefix_for(n, "现价 · 600519", "2026-11-27")
        assert text.startswith("来源 1：现价 · 600519 · 截至 2026-11-27")


class TestConfig:
    def test_env_priority_and_defaults(self, monkeypatch, tmp_path):
        """隔离真实 ~/.wmshare：文件兜底指向 tmp（None=文件不存在）。"""
        from workbench.tools.assistant import config
        from workbench.tools.assistant.config import load_config

        monkeypatch.setattr(config, "DEFAULT_CRED_PATH", tmp_path / "none.env")
        cfg = load_config(env={"WMSHARE_LLM_API_KEY": "abc"})
        assert cfg.configured
        assert cfg.model == "deepseek-chat", "未给模型名时用默认"
        assert cfg.max_ec == 5000

    def test_credentials_file_parsed(self, tmp_path):
        from workbench.tools.assistant.config import load_config

        env_file = tmp_path / "credentials.env"
        env_file.write_text(
            'export WMSHARE_LLM_API_KEY="file-key"\n'
            "# 注释\n"
            "WMSHARE_LLM_MODEL=kimi-k2\n", encoding="utf-8")
        cfg = load_config(env={}, cred_path=env_file)
        assert cfg.api_key == "file-key"
        assert cfg.model == "kimi-k2"

    def test_redacted_never_echoes_key(self):
        from workbench.tools.assistant.config import LLMConfig, redacted

        view = redacted(LLMConfig(base_url="https://api.deepseek.com",
                                  api_key="sk-secret-tail", model="m",
                                  max_ec=1, timeout_s=1))
        assert "sk-secret-tail" not in json.dumps(view)
        assert view["key_tail"] == "tail"


class TestLlmSse:
    def _fake_resp(self, lines, status=200):
        class Resp:
            def __init__(self):
                self.status = status
                self._lines = [l.encode() for l in lines]

            def __iter__(self):
                return iter(self._lines)

            def close(self):
                pass

        return Resp()

    def test_text_delta_and_tool_call_assembly(self, monkeypatch):
        from workbench.tools.assistant import llm

        def sse(delta: dict) -> str:
            return "data: " + json.dumps(
                {"choices": [{"delta": delta}]}, ensure_ascii=False)

        args_part1 = json.dumps({"sym": "600519"}, ensure_ascii=False)[:-1]
        args_part2 = ', "limit": 30}'
        lines = [
            sse({"content": "你好"}),
            sse({"tool_calls": [{"index": 0, "id": "c9",
                                 "function": {"name": "kline_bars",
                                              "arguments": args_part1}}]}),
            sse({"tool_calls": [{"index": 0,
                                 "function": {"arguments": args_part2}}]}),
            "data: [DONE]",
        ]
        events: list[dict] = []
        monkeypatch.setattr(llm, "urlopen",
                            lambda req, timeout: self._fake_resp(lines))
        cfg = type("C", (), {"model": "m", "base_url": "https://x",
                             "api_key": "k", "timeout_s": 5})()
        calls = llm.chat_stream(cfg, system="s", messages=[], tools=None,
                                on_event=events.append)
        assert {"type": "text_delta", "text": "你好"} in events
        assert len(calls) == 1 and calls[0]["name"] == "kline_bars"
        assert json.loads(calls[0]["arguments"]) == {"sym": "600519", "limit": 30}

    def test_status_maps_to_actions(self):
        from workbench.tools.assistant.llm import _transport_error

        def http_error(code):
            exc = Exception("x")
            exc.code = code  # type: ignore[attr-defined]
            return exc

        assert _transport_error(http_error(401)).action == "config"
        assert _transport_error(http_error(402)).action == "topup", \
            "余额不足是终态，不能映射成可重试"
        assert _transport_error(http_error(429)).action == "retry"
        assert _transport_error(RuntimeError("boom")).action == "retry"


class TestExecutor:
    def test_validate_arguments_coerces_and_rejects(self):
        entry = {"id": "t", "params": [
            {"name": "sym", "type": "string", "required": True, "desc": ""},
            {"name": "limit", "type": "int", "required": False, "default": 30},
        ]}
        from workbench.tools._shared import ToolError
        from workbench.tools.assistant import executor

        assert executor.validate_arguments(entry, {"sym": 600519}) == {
            "sym": "600519", "limit": 30}
        with pytest.raises(ToolError):
            executor.validate_arguments(entry, {})

    def test_screener_guard_applied(self, ctx):
        from workbench.tools.assistant import executor

        entry = next(e for e in executor.load_registry()
                     if e["id"] == "screener_query")
        text, _evidence, _as_of = executor.execute(
            ctx, entry, {"where": "$PE_TTM < 15", "limit": 5})
        sent = dict(ctx.fetcher.calls[-1][1])
        assert sent["where"] == "($PE_TTM < 15) && $PE_TTM > 0", \
            "助手执行器必须与选股页同口径（非负守卫）"
        assert text

    def test_compact_truncates_honestly(self):
        from workbench.tools.assistant import executor

        rows = [{"i": i} for i in range(50)]
        text = executor._compact(rows)
        assert "共 50 行" in text and "前 10 行" in text
        blob = "x" * 5000
        assert "截断" in executor._compact(blob)

    def test_as_of_reads_dataframe_tail(self):
        """门面行表（DataFrame）的截至日取末行——来源芯片不该空白。"""
        from workbench.tools.assistant import executor

        class DF:
            def to_dict(self, orient):
                assert orient == "records"
                return [{"date": "2025-01-02"}, {"ex_date": "2026-06-26"}]

        assert executor._rows_as_of(DF()) == "2026-06-26"

        from workbench.tools._shared import as_of_of
        assert as_of_of({"quote_date": "2026-11-26"}) == "2026-11-26"

    def test_compact_keeps_latest_rows_for_time_series(self):
        """日K/分红明细按日期升序——必须留最近的行，否则「最近走势」答成旧数据。"""
        from workbench.tools.assistant import executor

        rows = [{"date": f"2026-01-{i:02d}", "v": i} for i in range(1, 31)]
        text = executor._compact(rows, 10)
        assert "最近 10 行" in text
        assert '"date": "2026-01-30"' in text
        assert '"date": "2026-01-01"' not in text


class TestAgentLoop:
    def test_tool_round_then_answer(self, scripted, ctx):
        fake = scripted([
            {"tool": "kline_last_live", "args": {"sym": "600519"}},
            {"text": "现价见 [1]。"},
        ])
        from workbench.tools.assistant import agent, executor

        messages: list[dict] = [{"role": "user", "content": "600519 现在多少钱"}]
        entry = next(e for e in executor.load_registry()
                     if e["id"] == "kline_last_live")

        def execute_fn(name, args):
            assert name == "kline_last_live"
            text, _ev, _as_of = executor.execute(ctx, entry, args)
            return text, {"kind": "行情", "title": "现价", "detail": "", "as_of": ""}, None

        final, rounds = agent.run_turn(
            config=type("C", (), {"model": "m", "base_url": "x", "api_key": "k",
                                  "timeout_s": 5})(),
            system="s", messages=messages,
            tools=executor.to_llm_tools([entry]),
            execute_fn=execute_fn, on_event=lambda e: None)
        assert rounds == 1
        assert final == "", "最终文本经 text_delta 流出，返回值只在截停场景非空"
        roles = [m["role"] for m in messages]
        assert roles == ["user", "assistant", "tool"], "工具轮消息成对追加"
        assert "close" in fake.calls[-1]["messages"][-1]["content"], \
            "工具结果（紧凑化后）作为 tool 消息进入下一轮上下文"

    def test_hard_rounds_stop(self, scripted):
        scripted([{"tool": "kline_last_live", "args": {"sym": "600519"}}] * 50)
        from workbench.tools.assistant import agent

        final, rounds = agent.run_turn(
            config=type("C", (), {"model": "m", "base_url": "x", "api_key": "k",
                                  "timeout_s": 5})(),
            system="s", messages=[{"role": "user", "content": "q"}],
            tools=[], execute_fn=lambda n, a: ("数据", None, None),
            on_event=lambda e: None)
        assert rounds == agent.HARD_ROUNDS
        assert "上限" in final, "截停必须如实声明，不能装作自然结束"

    def test_stop_flag(self, scripted):
        scripted([{"tool": "kline_last_live", "args": {"sym": "600519"}}] * 50)
        from workbench.tools.assistant import agent

        final, _rounds = agent.run_turn(
            config=type("C", (), {"model": "m", "base_url": "x", "api_key": "k",
                                  "timeout_s": 5})(),
            system="s", messages=[{"role": "user", "content": "q"}],
            tools=[], execute_fn=lambda n, a: ("数据", None, None),
            on_event=lambda e: None, should_stop=lambda: True)
        assert "停止" in final


class TestRunner:
    def test_prompt_lists_all_domains(self):
        from workbench.tools.assistant import runner
        from workbench.tools.assistant.skills import load_skills

        prompt = runner.build_system_prompt(load_skills())
        assert "market（行情）" in prompt
        assert "meta（目录）" in prompt
        assert "read_skill" in prompt, "细口径按需读，不堆进系统提示"

    def test_tools_grouped_by_domain(self):
        from workbench.tools.assistant import runner
        from workbench.tools.assistant.skills import load_skills

        tools = runner.build_tools(load_skills())
        names = [t["name"] for t in tools]
        assert names[-2:] == ["read_skill", "catalog_search"], "宿主工具收尾"
        prices = [t for t in tools if t["name"] == "kline_last_live"][0]
        assert prices["description"].startswith("【行情】")
        assert "dividend_history" in names
        assert "dividend_yield" in names
        assert "kline_last_live" in names[:names.index("daily_basic")], \
            "工具数组按固定域序排列（行情在基本面之前）"

    def test_budget_gate_blocks_expensive_entry(self, ctx):
        """预估超预算的取数不执行——给模型「预算已用尽」的可读结果。"""
        ctx.fetcher.cost_estimate = lambda t, **p: {
            "ec_lo": 30_000, "ec_hi": 34_400, "model": "test"}
        from workbench.tools.assistant import runner
        from workbench.tools.assistant.ledger import SourceLedger
        from workbench.tools.assistant.skills import load_skills

        config = type("C", (), {"max_ec": 5000})()
        execute_fn = runner.make_execute_fn(
            ctx, config, SourceLedger(), load_skills())
        before = len(ctx.fetcher.calls)
        text, _ev, _cost = execute_fn("statements_income", {"symbol": "600519"})
        assert "预算" in text or "已用尽" in text
        assert len(ctx.fetcher.calls) == before, "超预算必须连请求都不发"

    def test_execute_numbers_sources(self, ctx):
        from workbench.tools.assistant import runner
        from workbench.tools.assistant.ledger import SourceLedger
        from workbench.tools.assistant.skills import load_skills

        ledger = SourceLedger()
        config = type("C", (), {"max_ec": 5000})()
        execute_fn = runner.make_execute_fn(ctx, config, ledger, load_skills())
        text, evidence, _cost = execute_fn("kline_last_live", {"sym": "600519"})
        assert text.startswith("来源 1：")
        assert evidence and evidence["kind"] == "行情"
        assert ledger.to_list()[0]["n"] == 1


class TestGatesAndEndpoints:
    def test_missing_source_gate(self, tmp_path):
        from workbench.bootstrap import build_context as bc
        from workbench.client.fetchers import MissingFetcher

        ctx = bc(store=Store(tmp_path / "m.db"), fetcher=MissingFetcher())
        from workbench.tools.assistant import handler

        env = handler.handle_chat(ctx, {"message": "你好"})
        assert env["ok"] is False
        assert env["meta"]["action"] == "config"
        assert "未接入" in env["meta"]["error"]

    def test_llm_unconfigured_gate(self, ctx, monkeypatch, tmp_path):
        monkeypatch.delenv("WMSHARE_LLM_API_KEY", raising=False)
        # 隔离真实 ~/.wmshare/credentials.env（本机已配真 key）
        from workbench.tools.assistant import config as llm_config
        monkeypatch.setattr(llm_config, "DEFAULT_CRED_PATH",
                            tmp_path / "none.env")
        from workbench.tools.assistant import handler

        env = handler.handle_chat(ctx, {"message": "你好"})
        assert env["ok"] is False
        assert env["meta"]["code"] == "llm_not_configured"
        assert "WMSHARE_LLM_API_KEY" in env["meta"]["error"], "引导必须写清键名"

    def test_chat_stream_stop_full_cycle(self, ctx, llm_env, scripted):
        """端到端（假模型）：chat → 轮询 → done；会话落库可读回。"""
        scripted([{"tool": "kline_last_live", "args": {"sym": "600519"}},
                  {"text": "现价见 [1]，不构成投资建议。"}])
        from workbench.tools.assistant import handler

        env = handler.handle_chat(ctx, {"message": "600519 现在多少钱"})
        assert env["ok"] is True
        job_id = env["data"]["job_id"]
        session_id = env["data"]["session_id"]
        deadline = time.time() + 5
        snap = {}
        while time.time() < deadline:
            snap = handler.handle_stream(ctx, {"job_id": job_id})["data"]
            if snap["status"] != "running":
                break
            time.sleep(0.05)
        assert snap["status"] == "done"
        assert "[1]" in snap["text"]
        assert snap["sources"], "宿主编号的来源账必须随消息给出"

        saved = ctx.store.get_assistant_session(session_id)
        assert saved is not None
        roles = [m["role"] for m in saved["messages"]]
        assert roles == ["user", "assistant"]

    def test_unknown_job_and_stop(self, ctx, llm_env):
        from workbench.tools.assistant import handler

        env = handler.handle_stream(ctx, {"job_id": "nope"})
        assert env["ok"] is False
        env = handler.handle_stop(ctx, {"job_id": "nope"})
        assert env["data"]["stopped"] is False

    def test_sessions_crud(self, ctx):
        from workbench.tools.assistant import handler

        ctx.store.save_assistant_session("sess001", "问茅台",
                                         [{"role": "user", "content": "hi"}])
        env = handler.handle_sessions(ctx, {})
        assert env["data"]["count"] == 1
        env = handler.handle_session(ctx, {"id": "sess001"})
        assert env["data"]["messages"][0]["content"] == "hi"
        env = handler.handle_session(ctx, {"id": "sess001", "action": "delete"})
        assert env["data"]["deleted"] is True
        assert ctx.store.get_assistant_session("sess001") is None

    def test_info_endpoint_zero_request(self, ctx, llm_env):
        from workbench.tools.assistant import handler

        before = len(ctx.fetcher.calls)
        env = handler.handle_info(ctx, {})
        assert env["ok"] is True
        assert env["data"]["assistant"]["configured"] is True
        assert env["data"]["assistant"]["key_tail"] == "1234"
        assert any(d["id"] == "market" for d in env["data"]["domains"])
        assert len(ctx.fetcher.calls) == before, "info 必须 Zero EC"

    def test_missing_session_read(self, ctx, llm_env):
        from workbench.tools.assistant import handler

        env = handler.handle_session(ctx, {"id": "ghost"})
        assert env["ok"] is False
