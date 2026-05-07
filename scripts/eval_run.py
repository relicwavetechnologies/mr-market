"""Phase-2 golden eval runner.

Drives the golden query suite (`tests/golden_queries.yaml`) through the live
`/chat` SSE endpoint. For each prompt we:

  1. POST to /chat and consume every SSE event.
  2. Materialise a small `RunResult` (intent, tools called, blocked flag,
     final assistant text, guardrail metadata, latency).
  3. Evaluate every assertion declared on the YAML entry.
  4. Print a per-prompt PASS/FAIL line and a summary at the end.
  5. Optionally dump a markdown transcript (`--transcript path.md`) of every
     (prompt, response) pair — convenient for syncing to the Lark wiki so
     reviewers can read the actual demo answers.

Exits 0 if pass-rate ≥ ``--pass-min`` (default 75 / 80), else 1.

Usage:
    uv run python -m scripts.eval_run                              # default
    uv run python -m scripts.eval_run --pass-min 80                # require all
    uv run python -m scripts.eval_run --filter q43 q44             # subset
    uv run python -m scripts.eval_run --base http://localhost:8001
    uv run python -m scripts.eval_run --transcript .context/eval-transcript.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

DEFAULT_BASE = "http://localhost:8001"
DEFAULT_YAML = Path(__file__).resolve().parent.parent / "tests" / "golden_queries.yaml"


# ---------------------------------------------------------------------------
# Run a single prompt against /chat and collect events
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class RunResult:
    id: str
    prompt: str
    intent: str | None = None
    ticker: str | None = None
    tools_called: list[str] = field(default_factory=list)
    final_message: str = ""
    blocked: bool = False
    overridden: bool = False
    disclaimer_injected: bool = False
    blocklist_rule_ids: list[str] = field(default_factory=list)
    latency_ms: int = 0
    error: str | None = None


async def run_prompt(client: httpx.AsyncClient, base: str, q: dict[str, Any]) -> RunResult:
    res = RunResult(id=str(q["id"]), prompt=str(q["prompt"]))
    started = time.perf_counter()

    try:
        async with client.stream(
            "POST",
            f"{base}/chat",
            json={"message": q["prompt"]},
            timeout=120.0,
        ) as resp:
            if resp.status_code != 200:
                res.error = f"HTTP {resp.status_code}"
                return res
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:") :].strip()
                try:
                    ev = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                _apply(ev, res)
    except Exception as e:  # noqa: BLE001
        res.error = f"{type(e).__name__}: {e!s}"
    finally:
        res.latency_ms = int((time.perf_counter() - started) * 1000)
    return res


def _apply(ev: dict[str, Any], res: RunResult) -> None:
    t = ev.get("type")
    if t == "intent":
        res.intent = ev.get("intent")
        res.ticker = ev.get("ticker")
    elif t == "tool_call":
        res.tools_called.append(str(ev.get("name")))
    elif t == "guardrail":
        res.overridden = bool(ev.get("overridden"))
        res.disclaimer_injected = bool(ev.get("disclaimer_injected"))
        for h in ev.get("blocklist_hits") or []:
            rule = h.get("rule_id") if isinstance(h, dict) else None
            if rule:
                res.blocklist_rule_ids.append(rule)
    elif t == "done":
        res.final_message = str(ev.get("message") or "")
        res.blocked = bool(ev.get("blocked"))
    elif t == "error":
        res.error = ev.get("message")


# ---------------------------------------------------------------------------
# Assertion engine
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Assertion:
    label: str
    ok: bool
    detail: str = ""


def evaluate(q: dict[str, Any], r: RunResult) -> list[Assertion]:
    out: list[Assertion] = []

    if r.error:
        out.append(Assertion("no_error", False, r.error))
        return out

    if "intent" in q:
        out.append(
            Assertion(
                f"intent={q['intent']}",
                r.intent == q["intent"],
                f"got intent={r.intent!r}",
            )
        )

    if "tools_called" in q:
        expected = list(q["tools_called"] or [])
        actual_set = set(r.tools_called)
        if not expected:
            # Strict zero-tool assertion (used for refusal short-circuits).
            out.append(
                Assertion(
                    "tools=[] (no tools fired)",
                    len(r.tools_called) == 0,
                    f"got tools={r.tools_called}",
                )
            )
        else:
            # Subset semantics: every expected tool must have been called;
            # the model is allowed to call extras.
            missing = [t for t in expected if t not in actual_set]
            out.append(
                Assertion(
                    f"tools⊇{expected}",
                    not missing,
                    f"missing={missing} got={sorted(actual_set)}",
                )
            )

    if "blocked" in q:
        out.append(
            Assertion(
                f"blocked={q['blocked']}",
                bool(r.blocked) == bool(q["blocked"]),
                f"got blocked={r.blocked}",
            )
        )

    text = r.final_message
    for pat in q.get("must_contain") or []:
        ok = bool(re.search(pat, text, flags=re.IGNORECASE))
        out.append(Assertion(f"contains:{pat}", ok))

    for pat in q.get("must_not_contain") or []:
        m = re.search(pat, text, flags=re.IGNORECASE)
        out.append(
            Assertion(
                f"absent:{pat}",
                m is None,
                f"matched: {m.group(0)!r}" if m else "",
            )
        )

    if "disclaimer" in q:
        if q["disclaimer"]:
            # Accept either:
            #  - the Phase-1 guardrail-injected "factual" disclaimer, OR
            #  - the Phase-2 internal-tool framing emitted by the model itself
            #    ("AI analyst view — internal use only, not investment advice").
            text_low = r.final_message.lower()
            disclaimer_present = (
                r.disclaimer_injected
                or "factual" in text_low
                or "ai analyst view" in text_low
                or "not investment advice" in text_low
                or "internal use only" in text_low
            )
            out.append(Assertion("disclaimer_injected", disclaimer_present))

    return out


# ---------------------------------------------------------------------------
# CLI / main
# ---------------------------------------------------------------------------

# ANSI colours — disabled if not a TTY.
_C = sys.stdout.isatty()
G = "\033[32m" if _C else ""
R_ = "\033[31m" if _C else ""
Y = "\033[33m" if _C else ""
DIM = "\033[2m" if _C else ""
RST = "\033[0m" if _C else ""


def _short(s: str, n: int = 70) -> str:
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


async def main_async(args: argparse.Namespace) -> int:
    queries: list[dict[str, Any]] = yaml.safe_load(Path(args.yaml).read_text())
    if args.filter:
        wanted = set(args.filter)
        queries = [q for q in queries if q.get("id") in wanted]
    if args.limit:
        queries = queries[: args.limit]

    print(f"Running {len(queries)} prompt(s) against {args.base}\n")

    passed = 0
    rows: list[tuple[RunResult, list[Assertion], bool]] = []

    async with httpx.AsyncClient() as client:
        for i, q in enumerate(queries, 1):
            r = await run_prompt(client, args.base, q)
            checks = evaluate(q, r)
            ok = all(c.ok for c in checks)
            if ok:
                passed += 1
                tag = f"{G}PASS{RST}"
            else:
                tag = f"{R_}FAIL{RST}"
            rows.append((r, checks, ok))
            print(
                f"[{i:2d}/{len(queries)}] {tag}  {q['id']:<25} "
                f"{DIM}{r.latency_ms:5d} ms{RST}  {_short(q['prompt'])}"
            )

    print()
    failed_rows = [(r, c) for r, c, ok in rows if not ok]
    if failed_rows:
        print(f"{R_}=== FAILURES ==={RST}")
        for r, checks in failed_rows:
            print(f"\n{R_}{r.id}{RST}  prompt: {r.prompt}")
            print(f"  intent={r.intent}  ticker={r.ticker}  "
                  f"tools={r.tools_called}  blocked={r.blocked}  "
                  f"overridden={r.overridden}")
            print(f"  message: {_short(r.final_message, 120)}")
            for c in checks:
                if not c.ok:
                    print(f"    {R_}✗{RST} {c.label}  {DIM}{c.detail}{RST}")

    rate = passed / max(len(queries), 1)
    summary = f"{passed}/{len(queries)} passed  ({rate * 100:.1f}%)"
    bar = G if passed >= args.pass_min else R_
    print(f"\n{bar}=== {summary} ==={RST}\n")

    # Optional transcript dump for the wiki / demo.
    if args.transcript:
        out_path = Path(args.transcript)
        out_path.write_text(_render_transcript(rows, queries))
        print(f"transcript written to {out_path}")

    return 0 if passed >= args.pass_min else 1


def _render_transcript(
    rows: list[tuple[RunResult, list[Assertion], bool]],
    queries: list[dict[str, Any]],
) -> str:
    """Render every (prompt, response) as a markdown document. Format is
    intentionally chunky and human-readable — designed to be pasted into
    the Lark wiki for FinWin / investor review."""
    total = len(rows)
    passed = sum(1 for _, _, ok in rows if ok)

    # Group by section heading derived from the YAML's section headers.
    # We walk the queries in their listed order (rows is parallel) and
    # use the YAML id-prefix sections as our grouping convention.
    lines: list[str] = []
    lines.append("# Midas — Phase-2 Golden Eval Transcript")
    lines.append("")
    lines.append(
        f"**{passed}/{total} passed ({passed / total * 100:.1f}%).** "
        "Live run against `gpt-4o-mini` with the full Phase-2 stack: "
        "intent-based tool shortlist, internal-tool framing (warn-mode "
        "guardrails), Pinecone-backed RAG, NSE pledge drill-down."
    )
    lines.append("")
    lines.append(
        "Each entry shows the prompt, the routed intent + tools the model "
        "actually fired, latency, and the verbatim assistant response. "
        "Failures (if any) are marked at the entry header."
    )
    lines.append("")

    for (r, checks, ok), q in zip(rows, queries):
        tag = "✅ PASS" if ok else "❌ FAIL"
        lines.append(f"### {tag} · `{r.id}`")
        lines.append("")
        lines.append(f"**Prompt:** {r.prompt}")
        lines.append("")
        meta_bits = [
            f"intent=`{r.intent}`",
            f"ticker=`{r.ticker}`",
            f"tools=`{r.tools_called}`",
            f"blocked=`{r.blocked}`",
            f"latency=`{r.latency_ms} ms`",
        ]
        lines.append("`" + "` · `".join(b.strip("`") for b in meta_bits) + "`")
        lines.append("")
        if r.final_message:
            lines.append("**Response:**")
            lines.append("")
            lines.append("> " + r.final_message.replace("\n", "\n> "))
            lines.append("")
        if not ok:
            failed = [c for c in checks if not c.ok]
            if failed:
                lines.append("**Failed assertions:**")
                lines.append("")
                for c in failed:
                    detail = f" — {c.detail}" if c.detail else ""
                    lines.append(f"- `{c.label}`{detail}")
                lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description="Midas Phase-1 golden eval runner")
    p.add_argument("--base", default=DEFAULT_BASE, help="backend base URL")
    p.add_argument(
        "--yaml",
        default=str(DEFAULT_YAML),
        help="path to golden_queries.yaml",
    )
    p.add_argument(
        "--pass-min",
        type=int,
        default=75,
        help="minimum number of passing prompts (default 75 / 80)",
    )
    p.add_argument(
        "--filter",
        nargs="+",
        help="run only these prompt ids (e.g. --filter q01 q02_price_tcs)",
    )
    p.add_argument("--limit", type=int, help="run only the first N prompts")
    p.add_argument(
        "--transcript",
        help="write a markdown transcript of every (prompt, response) "
        "to this path — useful for syncing to the Lark wiki",
    )
    args = p.parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
