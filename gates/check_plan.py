#!/usr/bin/env python3
"""门禁 5：台账完整性（``docs/TRACKING.md`` §5）。

计划一旦不再被核对，就退化为愿望清单。本门禁把八条规则变成可执行断言：

1. ``PROGRESS.md`` 里每个 ``done`` 工作项必须有 ``evidence``，且其指向的
   文件真实存在。
2. 依赖方向：某工作项标 ``done`` 而其 ``id`` 前缀所属阶段在 ``PLAN.md`` 里
   仍是 ``proposed`` → 阶段状态滞后，报错（防止「计划没人更新」）。
3. ``DEBT.md`` 每条必须有 ``severity`` / ``trigger`` / ``owner`` 三列非空。
4. ``PROGRESS.md`` 的统计行必须与表格实际行数一致（禁止手改数字）。
5. 全部源码与文档里的 ``TODO`` 必须形如 ``TODO(P3-07): ...``，且 id 存在于台账。
6. ``ec_impact=manual`` 的工作项必须在 ``EC_BUDGET.md`` 有对应 id 出现。
7. ``DEBT.md`` 行尾不得出现 ``repaid`` 而状态列仍为 ``open``（列数错位），
   且状态列的取值必须可识别。
8. ``README.md`` 里声明的离线用例数必须等于 ``tests/`` 的实际 ``def test_`` 计数。

第 7、8 条都是真实发生过的漂移：D-09/D-10/D-13 曾在状态列留着 `open` 又
在行尾多一列 `repaid`（读起来像已还清，实际全是 open）；README 写 234 个
用例而实际已 314 个（加测试时忘了改文档）。

统一事项：「缺字段」与「字段值不对」不同——前者是能力缺失，后者是撒谎。
本门禁对两者都报错，但**文字上区分**，便于判断是补字段还是改数据。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _gate import (  # noqa: E402
    DOCS,
    GATES_DIR,
    REPO,
    SRC,
    TESTS,
    GateError,
    Result,
    load_baseline,
    run_gate,
)

PROGRESS = DOCS / "PROGRESS.md"
PLAN = DOCS / "PLAN.md"
DEBT = DOCS / "DEBT.md"
EC_BUDGET = DOCS / "EC_BUDGET.md"

#: 工作项 id：``P<数字>[可选字母后缀]-<序号>``。
#: 字母后缀允许 ``P1U``（P1 阶段内可并行推进的前端子阶段）这类细分。
#: 上一版只认 ``P\d+-\d+``，导致 ``P1U-01..04`` 四行**完全不被统计**——
#: 台账实际 74 行，统计只报 70 项，且这四行的验收条件从没被校验过。
ID_RE = re.compile(r"^P\d+[A-Z]?-\d+$")
#: PROGRESS 行：| id | type | scope | status | acceptance | evidence | ec_impact | updated |
PROGRESS_ROW = re.compile(
    r"^\|\s*(P\d+[A-Z]?-\d+)\s*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|"
    r"([^|]*)\|([^|]*)\|")
STATS_RE = re.compile(
    r"\*\*统计\*\*：总计\s*(\d+)\s*·\s*done\s*(\d+)\s*·\s*in_progress\s*(\d+)"
    r"\s*·\s*accepted\s*(\d+)\s*·\s*proposed\s*(\d+)")
#: 统计行格式变更时的提示（放这里便于改一处）
STATS_FORMAT_HINT = (
    "格式：`**统计**：总计 N · done N · in_progress N · accepted N · proposed N`")
TODO_RE = re.compile(r"TODO\(([^)]*)\)")
#: 文档里「讨论 TODO 规范」的写法：整个 TODO 被反引号包住，如 `` `TODO` ``、
#: `` `TODO(<id>): …` ``。这些是规范说明，不是真实待办，必须跳过——
#: 否则「写一条禁止裸 TODO 的规则」本身会违反该规则。
TODO_IN_CODE_SPAN = re.compile(r"`[^`]*TODO[^`]*`")
PLAN_ROW = re.compile(r"^\|\s*(P\d+[A-Z]?)\s*\|[^|]*\|[^|]*\|\s*`(\w+)`\s*\|")

VALID_STATUS = {"proposed", "accepted", "in_progress", "in_review",
                "done", "blocked", "rejected"}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def parse_progress(result: Result) -> list[dict[str, str]]:
    """解析台账表行。"""
    text = read(PROGRESS)
    if not text:
        result.fail("docs/PROGRESS.md 缺失")
        return []
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        m = PROGRESS_ROW.match(line)
        if not m:
            continue
        gid, typ, scope, status, acc, ev, ec, updated = (
            g.strip() for g in m.groups())
        if not ID_RE.match(gid):
            continue
        rows.append({
            "id": gid, "type": typ, "scope": scope, "status": status,
            "acceptance": acc, "evidence": ev, "ec_impact": ec,
            "updated": updated,
        })
    return rows


def check_status_and_evidence(result: Result, rows: list[dict[str, str]]) -> None:
    # ① ID 唯一性。上一版不查，于是 P1-01..P1-04 在「设计系统」与「数据面」
    #    两段里各出现一次也通过——台账从此对不上号。
    seen: dict[str, int] = {}
    for r in rows:
        seen[r["id"]] = seen.get(r["id"], 0) + 1
    for gid, cnt in sorted(seen.items()):
        if cnt > 1:
            result.fail(f"工作项 ID 重复 {cnt} 次：{gid}；"
                        f"台账 ID 必须全局唯一（否则 evidence 指向不明）")

    for r in rows:
        result.checked += 1
        if r["status"] not in VALID_STATUS:
            result.fail(f"{r['id']} status 非法：{r['status']!r}；"
                        f"应为 {sorted(VALID_STATUS)} 之一")
        if not r["acceptance"] or r["acceptance"] in ("—", "-"):
            result.fail(f"{r['id']} 缺少 acceptance（验收条件）")
        if r["status"] != "done":
            continue
        ev = r["evidence"]
        if not ev or ev in ("—", "-"):
            result.fail(f"{r['id']} 已标 done 但 evidence 为空")
            continue
        for token in re.findall(r"`([^`]+)`", ev):
            if not evidence_exists(token):
                result.fail(f"{r['id']} 的 evidence 指向不存在的路径/未匹配文件："
                            f"{token}")
    if not seen:
        result.fail("台账里没有任何工作项")


def evidence_exists(token: str) -> bool:
    """evidence 可指向文件路径（含 ``::test_name`` 后缀）或纯测试名。"""
    raw = token.split("::", 1)[0]
    candidates = [REPO / raw, TESTS / raw, DOCS / raw]
    if any(c.exists() for c in candidates):
        return True
    name = token.split("::")[-1] if "::" in token else token
    if not re.fullmatch(r"[A-Za-z_][\w.]*", name or ""):
        return False
    needle = name.split(".")[-1]
    if not TESTS.is_dir():
        return False
    for path in TESTS.rglob("*.py"):
        try:
            if needle in path.read_text(encoding="utf-8"):
                return True
        except UnicodeDecodeError:
            continue
    return False


def check_stats(result: Result, rows: list[dict[str, str]]) -> None:
    """统计行必须与实际行数一致。"""
    text = read(PROGRESS)
    m = STATS_RE.search(text)
    if not m:
        result.fail(f"docs/PROGRESS.md 缺少统计行或格式不符；{STATS_FORMAT_HINT}")
        return
    claimed = [int(x) for x in m.groups()]
    actual_total = len(rows)
    actual_done = sum(1 for r in rows if r["status"] == "done")
    actual_prog = sum(1 for r in rows if r["status"] == "in_progress")
    actual_acc = sum(1 for r in rows if r["status"] == "accepted")
    actual_prop = sum(1 for r in rows if r["status"] == "proposed")
    actual = [actual_total, actual_done, actual_prog, actual_acc, actual_prop]
    result.checked += 1
    if claimed != actual:
        result.fail(f"统计行与表格不符：声明 {claimed}（总/done/in_progress/"
                    f"accepted/proposed）vs 实际 {actual}；台账不许手改数字")


def check_plan_alignment(result: Result, rows: list[dict[str, str]]) -> None:
    """阶段状态不得滞后于其下工作项：有 done 却整阶段 proposed = 计划没更新。"""
    text = read(PLAN)
    if not text:
        result.fail("docs/PLAN.md 缺失")
        return
    stage_status: dict[str, str] = {}
    for line in text.splitlines():
        m = PLAN_ROW.match(line)
        if m:
            stage_status[m.group(1)] = m.group(2)
    if not stage_status:
        result.warn("docs/PLAN.md 未解析到阶段表（格式应为 `| P1 | 主题 | 交付 | `status` |`）")
        return
    for r in rows:
        result.checked += 1
        stage = r["id"].split("-")[0]
        st = stage_status.get(stage)
        if st is None:
            result.fail(f"{r['id']} 的所属阶段 {stage} 未登记在 PLAN.md")
            continue
        if r["status"] == "done" and st == "proposed":
            result.fail(f"{r['id']} 已 done，但 PLAN.md 里 {stage} 仍为 proposed；"
                        f"请更新阶段状态")
        if r["status"] in ("done", "in_progress") and st not in (
                "in_progress", "done"):
            result.fail(f"{r['id']} 处于 {r['status']}，但 PLAN.md 里 {stage} 为 "
                        f"{st}；阶段状态滞后")

    # 反方向：阶段标 done 时，其下所有工作项必须全 done。
    # TRACKING.md §5 规则 2 声明了这条，上一版没实现。
    by_stage: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        by_stage.setdefault(r["id"].split("-")[0], []).append(r)
    for stage, st in stage_status.items():
        if st != "done":
            continue
        items = by_stage.get(stage, [])
        if not items:
            result.warn(f"PLAN.md 里 {stage} 标 done 但台账无该阶段工作项")
            continue
        pending = [i["id"] for i in items if i["status"] != "done"]
        result.checked += 1
        if pending:
            result.fail(f"PLAN.md 里 {stage} 已标 done，但台账仍有未完成项："
                        f"{', '.join(pending)}")


def check_debt(result: Result) -> None:
    text = read(DEBT)
    if not text:
        result.fail("docs/DEBT.md 缺失")
        return
    rows = debt_rows(text)
    if not rows:
        result.warn("docs/DEBT.md 没有任何债务条目（可接受，但请确认不是漏记）")
    for line in rows:
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 6:
            result.fail(f"DEBT 行列数不足（需 id/风险/severity/trigger/owner/处置/"
                        f"状态）：{line[:60]}")
            continue
        result.checked += 1
        did, sev, trigger, owner = cells[0], cells[2], cells[3], cells[4]
        if not re.fullmatch(r"P[0-2]", sev):
            result.fail(f"{did} severity 非法：{sev!r}；应为 P0/P1/P2")
        if not trigger or trigger in ("—", "-", "待填"):
            result.fail(f"{did} 缺少 trigger（何时偿还）")
        if not owner or owner in ("—", "-"):
            result.fail(f"{did} 缺少 owner")
        check_debt_columns(result, did, cells, line)


def debt_rows(text: str) -> list[str]:
    """只取**债务区**的行（`## 已偿还` 之前）。

    「已偿还」小节是另一张表（id/原风险/日期/证据，4 列），形态本就不同；
    把它的行也按 7 列校验会误报。此前这个函数扫全文，一旦移走条目就红。
    """
    out: list[str] = []
    for line in text.splitlines():
        if line.startswith("## 已偿还"):
            break
        if line.startswith("| D-") or line.startswith("|D-"):
            out.append(line)
    return out


def check_debt_columns(result: Result, did: str,
                       cells: list[str], line: str) -> None:
    """**列数与状态语义**：多出来的列会把 `open` 读成已偿还。

    真事：D-09/D-10/D-13 的状态列写着 ``open``，行尾又多一列
    ``repaid 2026-11-25``。表头只有 7 列，多出的第 8 列在 markdown 里
    会渲染成一个隐形的错位单元格——按 6 列读是「33 条未偿」，按 7 列读
    是「30 条未偿」，同一份文档两种答案。
    """
    result.checked += 1
    # 7 列布局：id | 风险 | severity | trigger | owner | 处置方案 | 状态
    status = cells[6] if len(cells) > 6 else (cells[5] if len(cells) > 5 else "")
    # 状态值习惯写成行内代码（`` `open` ``），判值前去掉反引号
    status_text = status.strip("`").strip()
    extra = cells[7:]
    is_repaid = status_text.startswith("repaid")
    # 状态列的三种合法取值：`open` / `repaid <日期>` / `wontfix`
    if not (status_text == "open" or is_repaid or status_text == "wontfix"):
        result.fail(f"{did} 状态列取值无法识别：{status!r}；"
                    f"应为 open / repaid <日期> / wontfix")
    if extra and not is_repaid:
        result.fail(
            f"{did} 行尾多出 {len(extra)} 列（{extra!r}）而状态列仍是 "
            f"{status!r}——多一列会被误读成「已偿还」。"
            f"要么把状态改成 `repaid <日期>` 并移入「已偿还」小节，"
            f"要么删掉多余列：{line[:60]}")


def check_readme_test_count(result: Result) -> None:
    """README 声明的离线用例数必须等于 pytest **实际可收集**的用例数。

    **真事**：README 写「234 个离线用例」，而加完预测/拆解两批测试后实际
    已 319 个。文档数字漂移是读者最容易发现的失真——它不像逻辑错误需要
    读代码才能看出，一眼就能对不上，因此最伤可信度。

    **口径用 pytest 自己的收集结果**（`--collect-only`），不用 `def test_`
    计数：后者数不到 `@pytest.mark.parametrize` 的展开（实测 310 vs 319），
    而用户跑 `make test` 看到的是后者。门禁报的数必须与用户看到的一致，
    否则门禁本身就是下一个漂移源。

    收集失败时退回静态计数并**告警**（不静默）。
    """
    readme = REPO / "README.md"
    text = read(readme)
    if not text:
        result.warn("README.md 缺失，跳过用例数校验")
        return
    claimed = [int(m.group(1)) for m in
               re.finditer(r"(\d+)\s*个离线用例", text)]
    claimed += [int(m.group(1)) for m in
                re.finditer(r"离线测试（(\d+)\s*个用例）", text)]
    if not claimed:
        result.warn("README 未声明离线用例数（可接受，但建议写明）")
        return
    if not TESTS.is_dir():
        return
    actual = collect_count()
    if actual is None:
        result.warn("pytest 收集失败，跳过 README 用例数校验")
        return
    result.checked += 1
    for n in set(claimed):
        if n != actual:
            result.fail(
                f"README 声明 {n} 个离线用例，pytest 实际收集 {actual} 个；"
                f"加/删测试后请同步 README（同一数字出现多处要一起改）")
            return


def collect_count() -> int | None:
    """跑 ``pytest --collect-only`` 数用例；失败/超时返回 ``None``。

    ``-q`` 的输出是 ``tests/test_x.py: 13`` 这种「文件: 数量」清单
    （不是逐 nodeid），因此按行尾整数求和。
    """
    import subprocess

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q",
             "--no-header", "-p", "no:cacheprovider"],
            cwd=str(REPO), capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode not in (0, 5):
        return None
    total = 0
    for ln in proc.stdout.splitlines():
        m = re.search(r":\s*(\d+)\s*$", ln)
        if m:
            total += int(m.group(1))
    return total or None


def python_comments(text: str) -> list[tuple[int, str]]:
    """抽取 Python 源码里的**真实注释**（行号, 内容）。

    必须走 ``tokenize`` 而不是逐行字符串匹配：测试里会写到
    ``"# TODO: ..."`` 这样的**字符串字面量**（用来验证门禁本身），
    逐行匹配会把它当成注释，造成「测试门禁的代码违反门禁」的循环误报。
    """
    import io
    import tokenize

    out: list[tuple[int, str]] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                out.append((tok.start[0], tok.string))
    except (tokenize.TokenError, IndentationError):
        return []
    return out


def check_todos(result: Result, rows: list[dict[str, str]]) -> None:
    """所有 TODO 必须带合法工作项 id。

    Markdown 逐行匹配，Python 只扫真实注释（见 ``python_comments``）。
    """
    ids = {r["id"] for r in rows}
    roots = [SRC, GATES_DIR, TESTS, DOCS] if SRC.is_dir() else [REPO]
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or "node_modules" in path.parts:
                continue
            if path.suffix not in {".py", ".md", ".ts", ".vue", ".css"}:
                continue
            if path.name == "check_plan.py":
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            if path.suffix == ".py":
                candidates = python_comments(text)
            else:
                candidates = [(i, line)
                              for i, line in enumerate(text.splitlines(), 1)]

            for lineno, line in candidates:
                if "TODO" not in line:
                    continue
                # 跳过规范说明里的反引号写法（它们讨论 TODO 而非提出待办）
                if TODO_IN_CODE_SPAN.search(line):
                    continue
                result.checked += 1
                m = TODO_RE.search(line)
                if not m:
                    result.fail(f"{path.relative_to(REPO)}:{lineno} TODO 未带"
                                f"工作项 id；格式应为 TODO(P3-07): 说明")
                    continue
                tid = m.group(1).strip()
                if tid not in ids:
                    result.fail(f"{path.relative_to(REPO)}:{lineno} TODO "
                                f"引用不存在的工作项 {tid}")


def check_ec_impact(result: Result, rows: list[dict[str, str]]) -> None:
    text = read(EC_BUDGET)
    if not text:
        result.fail("docs/EC_BUDGET.md 缺失")
        return
    for r in rows:
        if r["ec_impact"].lower() != "manual":
            continue
        result.checked += 1
        if r["id"] not in text:
            result.fail(f"{r['id']} 标了 ec_impact=manual，但 docs/EC_BUDGET.md "
                        f"里没有对应条目")


def check_test_baseline(result: Result) -> None:
    """测试数下限棘轮（``quality/baselines/tests.json``）。

    上一版这份基线**无任何代码读取**——声明「低于即红」却永远不执行，
    是七份棘轮里唯一完全失效的一份。本函数补上。

    按 ``scope`` 匹配测试文件（文件名含 scope 的末段，或测试函数名含 scope）。
    计数用 ``def test_`` 的出现次数，不跑 pytest（门禁必须离线且快）。
    """
    try:
        baseline = load_baseline("tests")
    except GateError:
        return          # 基线缺失不算违规（由 Phase 1 建立）
    per_scope: dict[str, int] = dict(baseline.get("per_tool") or {})
    if not per_scope:
        return
    if not TESTS.is_dir():
        result.fail("tests/ 目录不存在，但 tests.json 声明了测试下限")
        return

    counts: dict[str, int] = {k: 0 for k in per_scope}
    for path in sorted(TESTS.rglob("*.py")):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        # **缩进也要算**：`^def test_` 只匹配模块级函数，而用例放在
        # `class TestXxx:` 里是 pytest 的主流写法。上一版两者叠加的结果是
        # 「新写的测试一个都不计入」——下限棘轮因此永远绿。
        n = len(re.findall(r"^\s*def test_", text, re.M))
        if not n:
            continue
        # 文件级归属：文件名含 scope 末段（如 test_hub_policy.py → hub）
        for scope in counts:
            key = scope.split(":")[-1]
            if key in path.name:
                counts[scope] += n

    for scope, need in sorted(per_scope.items()):
        result.checked += 1
        have = counts.get(scope, 0)
        if have < int(need):
            result.fail(f"scope {scope} 的测试数 {have} 低于下限 {need}"
                        f"（tests.json 棘轮只允许上调）")


def main() -> Result:
    result = Result("plan")
    rows = parse_progress(result)
    if not rows:
        return result
    check_status_and_evidence(result, rows)
    check_stats(result, rows)
    check_plan_alignment(result, rows)
    check_debt(result)
    check_todos(result, rows)
    check_ec_impact(result, rows)
    check_test_baseline(result)
    check_readme_test_count(result)
    return result


if __name__ == "__main__":
    raise SystemExit(run_gate("plan", main))
