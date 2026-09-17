"""Blindness tests for suites.arena.

The arena's whole claim is that the judge is independent. That claim is only
worth anything if it is enforced in code rather than asserted in a docstring, so
these tests intercept every prompt the arena would send and assert what is NOT
in them.

Two blindnesses, both load-bearing:

  1. The judge never sees a MODEL.md. If it did, it would be reasoning from the
     same mechanisms as the panel and would not be independent of them.
  2. Nobody -- panelist or judge -- sees the case's sealed outcome before the
     ruling. If they did, the run would be a fit, not a call.

A third check: every minute must be signed. An unsigned minute cannot be traced
to a model state, and the user asked specifically for signature by name, version
and commit.

  python -m suites.arena_test
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from suites import arena  # noqa: E402

CAPTURED: list[dict] = []


def fake_call(model_hint, prompt, dry):
    """Echo backend: records the prompt, returns a well-formed minute."""
    CAPTURED.append({"prompt": prompt})
    n = len(CAPTURED)
    return {
        "grip": "strong",
        "claim": "claim number %d, deliberately distinct" % n,
        "because": "mechanism step",
        "falsifier": "specific observation",
        "confidence": 0.4 + (n % 5) / 10.0,
        "blind_spot": "none stated",
        "move": "DEFEND" if n % 2 else "REVISE",
        "moved_by": None,
        "strongest_objection": "objection",
        "answer": "answer",
        "ruling": "ruling number %d" % n,
        "strongest_minute": "x",
        "weakest_minute": "y",
        "shared_assumption": None,
        "unresolved": "unresolved",
    }


def main() -> int:
    fails = []
    arena._call = fake_call  # intercept every LLM call
    CAPTURED.clear()

    case_slug = "openai-nov-2023"
    cases = arena.backtest_cases()
    if case_slug not in cases:
        print("FAIL: case %s not found" % case_slug)
        return 1
    case = cases[case_slug]

    # A meaningful test needs a real sealed outcome to look for.
    if not case["sealed_outcome"] or len(case["sealed_outcome"]) < 80:
        fails.append("case has no sealed outcome to withhold — test is vacuous")

    arena.run(case_slug, "attention-substrate,pressure-model,ai-pressure", 2, False, "test-model")

    print("\n=== captured %d prompts ===" % len(CAPTURED))

    # ---- blindness 1: the judge never sees a MODEL.md ----
    docs = {}
    for slug in ("attention-substrate", "pressure-model", "ai-pressure"):
        p = arena.TOOLS / slug / "MODEL.md"
        if p.exists():
            docs[slug] = p.read_text(encoding="utf-8", errors="replace")

    judge_prompts = [c["prompt"] for c in CAPTURED if c["prompt"].startswith("You are an INDEPENDENT JUDGE")]
    if not judge_prompts:
        fails.append("no judge prompt was produced")
    for jp in judge_prompts:
        for slug, doc in docs.items():
            # Look for distinctive long runs from the document body, not headers
            # (a title can legitimately appear via a minute's model_title field).
            body = [ln.strip() for ln in doc.splitlines()
                    if len(ln.strip()) > 90 and not ln.strip().startswith("#")]
            leaked = [ln for ln in body[:40] if ln[:80] in jp]
            if leaked:
                fails.append("JUDGE SAW MODEL.md text from %s: %r" % (slug, leaked[0][:70]))

    # ---- blindness 2: nobody sees the sealed outcome ----
    outcome = case["sealed_outcome"]
    probes = [ln.strip() for ln in outcome.splitlines() if len(ln.strip()) > 60][:12]
    for c in CAPTURED:
        for pr in probes:
            if pr[:60] in c["prompt"]:
                fails.append("SEALED OUTCOME LEAKED into a prompt: %r" % pr[:70])
                break

    # the word-level canary: the assessment's recalibration note must never appear
    if case["origin_score"]:
        for key in ("biggest_error", "recalibration", "reasoning_wins"):
            v = str(case["origin_score"].get(key, ""))[:50]
            if len(v) > 25 and any(v in c["prompt"] for c in CAPTURED):
                fails.append("ORIGIN ASSESSMENT (%s) leaked into a prompt" % key)

    # ---- signatures ----
    run_id = "arena-%s-%s" % (case_slug, arena.TODAY)
    mfile = arena.ADIR / run_id / "cycle-1" / "minutes.jsonl"
    if not mfile.exists():
        fails.append("no minutes written")
    else:
        rows = [json.loads(l) for l in mfile.read_text(encoding="utf-8").splitlines() if l.strip()]
        if not rows:
            fails.append("minutes file is empty")
        for r in rows:
            if not r.get("signed_by"):
                fails.append("unsigned minute: %s" % json.dumps(r)[:80])
        panel_rows = [r for r in rows if r["signed_by"] != arena.JUDGE_SLUG]
        unc = [r["signed_by"] for r in panel_rows if not r.get("model_commit")]
        if unc:
            print("  note: no commit hash for %s (repo may be uncommitted)" % ", ".join(sorted(set(unc))))
        print("  minutes: %d rows, %d signed by panelists, %d by the judge"
              % (len(rows), len(panel_rows), len(rows) - len(panel_rows)))

    # ---- premise carry-forward: cycle 2 must quote the judge, not the panel ----
    c2 = [c["prompt"] for c in CAPTURED if "PREMISE CARRIED FROM THE PREVIOUS CYCLE" in c["prompt"]]
    if not c2:
        fails.append("cycle 2 did not carry a premise forward")
    else:
        # the carried premise must be a RULING string, which in this fake backend
        # always begins "ruling number"
        if not any("ruling number" in p for p in c2):
            fails.append("cycle-2 premise was not the judge's ruling")
        else:
            print("  premise carry-forward: cycle 2 quotes the judge's ruling — correct")

    print()
    if fails:
        print("FAILED (%d):" % len(fails))
        for f in fails:
            print("  x %s" % f)
        return 1
    print("PASS — judge saw no MODEL.md; sealed outcome never entered any prompt;")
    print("       every minute signed; the judge's ruling carried to the next cycle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
