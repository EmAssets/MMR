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

# Every artifact this test writes is namespaced. Without this the test wrote to
# the same directory as a real run and silently destroyed it mid-flight.
TAG = "selftest"


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

    arena.run(case_slug, "attention-substrate,pressure-model,ai-pressure", 2, False, "test-model",
              run_tag=TAG)

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

    # ---- blindness 2b: the ORIGIN MODEL'S PREDICTION must not leak either ----
    # Found 2026-09-16: splitting only on "## Real outcome" left the origin's
    # own prediction in the brief, so the panel was paraphrasing an answer.
    for slug, c in arena.backtest_cases().items():
        for probe in ("3. OUTCOME", "CONFIDENCE & FALSIFIABILITY", "Strategy:",
                      "Reasoning:", "## Prediction"):
            if probe in c["brief"]:
                fails.append("ORIGIN PREDICTION LEAKED into %s brief: %r" % (slug, probe))
    leaked_live = [c["prompt"] for c in CAPTURED if "Sam Altman is formally rehired" in c["prompt"]]
    if leaked_live:
        fails.append("origin prediction text reached a live prompt")
    else:
        print("  origin prediction withheld from every brief and prompt — correct")

    # ---- signatures ----
    run_id = "arena-%s-%s-%s" % (case_slug, arena.TODAY, TAG)
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

    # ---- signing: content hash, tamper evidence, and the dirty-tree flag ----
    # These are the proof that the traceability claim is real. Without them
    # "every minute is signed" is a docstring assertion.
    rows = [json.loads(l) for l in mfile.read_text(encoding="utf-8").splitlines() if l.strip()]

    v = arena.verify_chain(rows)
    if not v.get("ok"):
        fails.append("fresh chain did not verify: %s" % v.get("reason"))
    else:
        print("  chain verifies over %d minutes, head %s" % (v["rows"], v["head"][:12]))

    missing = [r["signed_by"] for r in rows if not r.get("model_md_sha256")]
    if missing:
        fails.append("minutes with no MODEL.md content hash: %s" % sorted(set(missing)))
    else:
        print("  every minute carries a MODEL.md content hash (judge: prompt-template hash)")

    # TAMPER 1: alter a body. Its own hash and every later link must break.
    import copy
    bad = copy.deepcopy(rows)
    bad[1]["body"]["claim"] = "silently altered after the fact"
    vb = arena.verify_chain(bad)
    if vb.get("ok"):
        fails.append("TAMPERING WENT UNDETECTED — an edited body still verified")
    else:
        print("  tamper detected: edited body -> %s at row %d"
              % (vb.get("reason"), vb.get("row", -1)))

    # TAMPER 2: delete a minute. The chain must break at the join.
    bad2 = copy.deepcopy(rows)
    del bad2[2]
    vd = arena.verify_chain(bad2)
    if vd.get("ok"):
        fails.append("DELETION WENT UNDETECTED — a removed minute still verified")
    else:
        print("  tamper detected: removed minute -> %s" % vd.get("reason"))

    # TAMPER 3: reorder. Order is part of the record: who spoke before whom.
    bad3 = copy.deepcopy(rows)
    bad3[0], bad3[1] = bad3[1], bad3[0]
    vr = arena.verify_chain(bad3)
    if vr.get("ok"):
        fails.append("REORDERING WENT UNDETECTED")
    else:
        print("  tamper detected: reordered minutes -> %s" % vr.get("reason"))

    # ---- the dirty-tree gap this whole feature exists to close ----
    # Demonstrated 2026-09-16: editing ai-pressure/MODEL.md without committing
    # left the reported commit unchanged, so a minute could cite a commit whose
    # content was not what the model read.
    mdp = arena.TOOLS / "ai-pressure" / "MODEL.md"
    if mdp.exists():
        original = mdp.read_bytes()
        clean = arena.mechanism("ai-pressure")
        try:
            mdp.write_bytes(original + b"\n<!-- uncommitted edit, selftest -->\n")
            dirty = arena.mechanism("ai-pressure")
            if dirty["model_md_sha256"] == clean["model_md_sha256"]:
                fails.append("content hash did NOT change when MODEL.md was edited")
            elif dirty["commit"] != clean["commit"]:
                fails.append("test invalid: commit changed, so this is not the dirty-tree case")
            elif not dirty["tree_dirty"]:
                fails.append("tree_dirty was False for a modified MODEL.md")
            else:
                print("  dirty-tree gap closed: same commit %s, DIFFERENT content hash "
                      "(%s -> %s), tree_dirty=True"
                      % (clean["commit"], clean["model_md_sha256"][:8],
                         dirty["model_md_sha256"][:8]))
        finally:
            mdp.write_bytes(original)
        if arena.mechanism("ai-pressure")["model_md_sha256"] != clean["model_md_sha256"]:
            fails.append("failed to restore ai-pressure/MODEL.md after the dirty-tree test")

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

    # ---- candidate mode: the arena must NOT promote ----
    CAPTURED.clear()
    cands = arena.candidate_cases()
    if not cands:
        print("  note: quarantine is empty — candidate-mode test skipped")
    else:
        cslug = sorted(cands)[0]
        rulings = arena.TOOLS / "pattern-candidates" / "candidates" / "arena-rulings.json"
        before = rulings.read_text(encoding="utf-8") if rulings.exists() else None
        arena.run(cslug, "attention-substrate,pressure-model", 1, False, "test-model", run_tag=TAG)

        jp = [c["prompt"] for c in CAPTURED if c["prompt"].startswith("You are an INDEPENDENT JUDGE")]
        if not jp:
            fails.append("candidate mode produced no judge prompt")
        elif "MECHANISM" not in jp[0] or "RESEMBLANCE" not in jp[0]:
            fails.append("candidate mode used the backtest judge prompt")
        else:
            print("  candidate mode: judge asked mechanism-or-resemblance — correct")

        # the evaluator must never sit on a panel judging its own verdict
        payload = json.loads((arena.ADIR / ("arena-%s-%s-%s" % (cslug, arena.TODAY, TAG)) / "arena.json")
                             .read_text(encoding="utf-8"))
        if any(x["slug"] == "pattern-evaluator" for x in payload.get("panel", [])):
            fails.append("pattern-evaluator seated on a panel judging its own verdict")
        else:
            print("  candidate mode: pattern-evaluator excluded from the panel — correct")

        # the ruling must land in quarantine, unpromoted
        if not rulings.exists():
            fails.append("candidate ruling was not written back to quarantine")
        else:
            doc = json.loads(rulings.read_text(encoding="utf-8"))
            row = next((r for r in doc.get("rulings", []) if r.get("case") == cslug), None)
            if not row:
                fails.append("no ruling row for %s" % cslug)
            elif row.get("promoted") is not False:
                fails.append("ARENA PROMOTED A CANDIDATE — the gate leaked")
            else:
                print("  candidate mode: ruling recorded, promoted=False — the gate held")
            if before is None:
                rulings.unlink(missing_ok=True)
            else:
                rulings.write_text(before, encoding="utf-8")

        # verdicts.json is the evaluator's record; the arena must not touch it
        vf = arena.TOOLS / "pattern-evaluator" / "verdicts.json"
        vmt = vf.stat().st_mtime if vf.exists() else 0
        if vf.exists() and vmt > __import__("time").time() - 120:
            fails.append("arena modified pattern-evaluator/verdicts.json")
        else:
            print("  candidate mode: evaluator verdicts.json untouched — correct")

    import shutil
    for d in arena.ADIR.glob("arena-*-%s" % TAG):
        shutil.rmtree(d, ignore_errors=True)

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
