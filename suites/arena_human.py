"""Arena, judged by a person instead of a blind model.

The arena's whole design is that an INDEPENDENT judge rules on minutes it cannot
trace to any MODEL.md. This module deliberately breaks that, because sometimes
the operator IS the judge -- they know the domain, they can see a panelist
bluffing, and they want the panel to argue against their call rather than a
model's. That is a legitimate use. It is also a different instrument, and the
entire job of this file is to make sure the two never get confused.

WHAT THE HUMAN JUDGE SEES, and the blind judge does not:

  * which model said what -- every minute is labelled with its slug
  * all of it at once, with time to think
  * possibly the real outcome, if the case is historical

So a human-judged run is marked `human_judged: true`, its ruling is signed by
`human-judge` rather than `independent-judge`, and `--score` REFUSES it. Scoring
would measure whether the operator knew the answer, and the number would land in
the same column as blind scores.

WHAT IS UNCHANGED, and must stay unchanged:

  * the panel rounds. argue_cycle() is the same function run() calls, so the
    claims and defences are produced identically. That is what keeps the two
    modes comparable AS PANELS even though the judging differs.
  * public-before-seen. Round 1 is still written before any panelist sees
    another's minute.
  * the hash chain. A human ruling is a minute like any other and chains the
    same way; tamper-evidence does not care who ruled.
  * the disagreement metric, and the shared-source echo warning. One LLM over
    one corpus converges for reasons that have nothing to do with the world,
    and a human judge does not fix that.

THE STATE MACHINE. A person may take hours, and the cockpit server restarts, so
nothing lives in memory:

  --start   writes the case, runs cycle 1's panel rounds, writes
            awaiting-judge.json, and STOPS.
  --rule    records the operator's ruling as a signed minute, then either runs
            the next cycle's panel rounds and stops again, or finalises.
  --status  what is waiting.

  python -m suites.arena_human --start --title "..." --brief-file b.md \\
      --models pressure-model,ai-option-space --cycles 3
  python -m suites.arena_human --status
  python -m suites.arena_human --rule <run-id> --pick pressure-model \\
      --ruling "..." --because "..."
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from suites import arena as A

TODAY = datetime.date.today().isoformat()
HUMAN_SLUG = "human-judge"

# The premise line the panel is shown. A panelist told "a judge ruled X" when a
# person in fact picked X is arguing against the wrong authority.
PREMISE_SOURCE = "the OPERATOR's own ruling — a person, not a blind judge, who saw every model's name"


# ------------------------------------------------------------------ case file

def write_case(slug: str, title: str, brief: str, question: str,
               as_of: str = "") -> Path:
    """Write a scenario case file in the format scenario_cases() parses.

    Prefixed `u-` so a case authored in the cockpit is never mistaken for one of
    the curated cases that were written deliberately and reviewed.
    """
    d = A.ADIR / "cases"
    d.mkdir(parents=True, exist_ok=True)
    f = d / ("%s.md" % slug)
    if f.exists():
        raise SystemExit("case already exists: %s — pick another slug" % f)
    lines = ["# " + title.strip(), "as of: " + (as_of or TODAY)]
    if question.strip():
        lines.append("question: " + question.strip())
    lines += ["", brief.strip(), ""]
    f.write_text("\n".join(lines), encoding="utf-8")
    return f


def slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48]
    return "u-" + (s or "case")


# ------------------------------------------------------------------ state

def _state_path(run_id: str) -> Path:
    return A.ADIR / run_id / "awaiting-judge.json"


def _load_state(run_id: str) -> dict:
    f = _state_path(run_id)
    if not f.exists():
        raise SystemExit("no pending arena at %s (already finished, or never started)" % run_id)
    return json.loads(f.read_text(encoding="utf-8"))


def _save_state(run_id: str, st: dict) -> None:
    _state_path(run_id).write_text(json.dumps(st, ensure_ascii=False, indent=1),
                                   encoding="utf-8")


def make_progress(outdir: Path, panel: list, cycles: int):
    """A progress callback that writes live.json as each panelist lands.

    The UI polls a file rather than holding a connection, for the same reason
    the run state is on disk: this server restarts, and a run that is only
    observable through a live socket becomes invisible the moment it does.

    Writes are whole-file and best-effort. A progress file that failed to write
    must never take a real run down with it -- the record is the minutes, this
    is a status light.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    state = {"panel": [p["slug"] for p in panel], "cycles_planned": cycles,
             "cycle": 1, "round": 0, "total": len(panel), "finished": [],
             "started_at": datetime.datetime.now().isoformat(timespec="seconds"),
             "status": "arguing"}

    def _flush():
        try:
            (outdir / "live.json").write_text(
                json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass

    def progress(kind: str, info: dict):
        if kind == "round":
            state["cycle"] = info["cycle"]
            state["round"] = info["round"]
            state["total"] = info["total"]
            # a new round starts empty; the previous round's finishers are done
            state["finished"] = []
            state["waiting_on"] = list(info.get("waiting_on") or [])
            state["round_started_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        elif kind == "done":
            state["finished"].append({
                "slug": info["slug"],
                "at": datetime.datetime.now().isoformat(timespec="seconds"),
                "grip": info.get("grip"), "move": info.get("move"),
                "error": info.get("error"),
                "claim": info.get("claim") or "",
            })
            state["waiting_on"] = [s for s in state.get("waiting_on", [])
                                   if s != info["slug"]]
        _flush()

    _flush()
    return progress, state


def _clear_progress(outdir: Path, status: str = "awaiting-judge") -> None:
    f = outdir / "live.json"
    try:
        if f.exists():
            d = json.loads(f.read_text(encoding="utf-8"))
            d["status"] = status
            d["waiting_on"] = []
            f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    except (OSError, ValueError):
        pass


def _write_cycle(outdir: Path, cyc: int, minutes: list) -> None:
    cdir = outdir / ("cycle-%d" % cyc)
    cdir.mkdir(parents=True, exist_ok=True)
    with (cdir / "minutes.jsonl").open("w", encoding="utf-8") as fh:
        for m in minutes:
            fh.write(json.dumps(m, ensure_ascii=False) + "\n")


def _read_cycle(outdir: Path, cyc: int) -> list:
    f = outdir / ("cycle-%d" % cyc) / "minutes.jsonl"
    if not f.exists():
        return []
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]


# ------------------------------------------------------------------ start

def start(title: str, brief: str, question: str, models: list, cycles: int,
          dry: bool, model_hint: str, as_of: str = "", case_slug: str = "") -> str:
    if len(models) < 2:
        # One model cannot be argued with, and round 2 would show it an empty
        # board. Same floor the brainstorm endpoint already enforces.
        raise SystemExit("need at least 2 models: a panel of one has nobody to defend against")
    if not brief.strip():
        raise SystemExit("empty brief — the panel would have nothing to argue from")

    slug = case_slug or slugify(title)
    write_case(slug, title, brief, question, as_of)
    cases = A.all_cases()
    if slug not in cases:
        raise SystemExit("wrote the case but could not read it back: %s" % slug)
    case = cases[slug]

    panel = A.resolve_panel(slug, ",".join(models))
    if len(panel) < 2:
        raise SystemExit("resolved only %d of %d models — check the slugs"
                         % (len(panel), len(models)))

    run_id = "arena-%s-%s-human" % (slug, TODAY)
    outdir = A.ADIR / run_id
    outdir.mkdir(parents=True, exist_ok=True)

    print("[arena/human] case=%s  panel=%d  cycles=%d%s"
          % (slug, len(panel), cycles, "  (DRY RUN)" if dry else ""))
    print("   %s" % case["title"])
    for p in panel:
        print("     %-28s %-14s %s %s" % (p["slug"], p["kind"], p["version"], p["commit"]))

    prog, _ = make_progress(outdir, panel, cycles)
    minutes = A.argue_cycle(case, panel, 1, None, dry, model_hint,
                            case.get("stages") or [], "", PREMISE_SOURCE, prog)
    _write_cycle(outdir, 1, minutes)
    _clear_progress(outdir)

    st = {
        "spec": "arena-human-v1",
        "run_id": run_id, "case": slug, "case_title": case["title"],
        "question": case.get("question") or "What follows, and why?",
        "as_of": case["as_of"],
        "cycles_planned": cycles, "cycle": 1, "status": "awaiting-judge",
        "dry_run": bool(dry), "model_hint": model_hint,
        "panel": [{k: p[k] for k in ("slug", "title", "kind", "version", "commit")} for p in panel],
        "chain_head": minutes[-1]["minute_sha"] if minutes else "",
        "rulings": [],
        "started": TODAY,
    }
    _save_state(run_id, st)
    print("\n  cycle 1 argued. %d minutes await YOUR ruling." % len(minutes))
    print("  -> %s" % _state_path(run_id))
    print("\n  rule on it with:")
    print("    python -m suites.arena_human --rule %s --pick <slug> --ruling \"...\"" % run_id)
    return run_id


# ------------------------------------------------------------------ rule

def rule(run_id: str, pick: str, ruling: str, because: str, dry: bool,
         model_hint: str, confidence: float = 0.0, pivot: str = "",
         resolve_by: str = "") -> None:
    st = _load_state(run_id)
    if st.get("status") != "awaiting-judge":
        raise SystemExit("%s is not awaiting a ruling (status=%s)" % (run_id, st.get("status")))
    cyc = st["cycle"]
    outdir = A.ADIR / run_id
    minutes = _read_cycle(outdir, cyc)
    if not minutes:
        raise SystemExit("no minutes found for cycle %d" % cyc)

    slugs = [p["slug"] for p in st["panel"]]
    if pick and pick not in slugs:
        raise SystemExit("--pick %r is not on the panel: %s" % (pick, ", ".join(slugs)))
    if not ruling.strip() and not pick:
        raise SystemExit("a ruling needs either --pick (adopt a panelist's claim) "
                         "or --ruling (write your own)")

    # Picking a slug without writing a ruling adopts that panelist's own claim
    # verbatim, so the premise carried forward is the argument as the model made
    # it rather than a paraphrase of it.
    adopted = ""
    if pick:
        mine = next((m for m in minutes
                     if m["signed_by"] == pick and m["round"] == 2), None) or \
               next((m for m in minutes if m["signed_by"] == pick), None)
        if mine:
            adopted = str(mine["body"].get("claim") or mine["body"].get("revised_claim") or "")
    text = ruling.strip() or adopted
    if not text:
        raise SystemExit("could not read a claim from %r and no --ruling given" % pick)

    body = {
        "ruling": text,
        "because": because.strip(),
        "picked": pick or None,
        "adopted_verbatim": bool(pick and not ruling.strip()),
        "pivot": pivot.strip() or None,
        "resolve_by": resolve_by.strip() or None,
        # --report reads the pivot's date from pivot_resolves_by, so a ruling
        # that set only resolve_by printed as "undated". Same date, both names.
        "pivot_resolves_by": resolve_by.strip() or None,
        "pivot_source": "human-judge",
        "confidence": float(confidence) if confidence else None,
        # Stated in the body, not only in the payload, because a minute travels
        # on its own -- someone reading minutes.jsonl must see this too.
        "judged_by": "human",
        "NOT_BLIND": ["saw every model's name against its minute",
                      "read all minutes together",
                      "may already know the real outcome"],
    }
    who = {"slug": HUMAN_SLUG, "title": "Operator (human judge)",
           "version": "human-v1", "commit": "",
           "model_md_sha256": "", "model_md_bytes": 0, "tree_dirty": False}
    rmin = A._minute("ruling", who, cyc, 3, body, "", minutes[-1]["minute_sha"])
    minutes.append(rmin)
    _write_cycle(outdir, cyc, minutes)
    (outdir / ("cycle-%d" % cyc) / "ruling.json").write_text(
        json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")

    chain = A.verify_chain(minutes)
    dis = A.disagreement(minutes)
    st["rulings"].append({"cycle": cyc, "ruling": body,
                          "disagreement": dis, "minutes": len(minutes),
                          "chain": chain})
    st["chain_head"] = minutes[-1]["minute_sha"]
    print("[arena/human] cycle %d ruled%s" % (cyc, (" — adopted %s verbatim" % pick)
                                              if body["adopted_verbatim"] else ""))
    print("  %s" % text[:100])
    print("  disagreement: %d/%d distinct (ratio %.2f) · %d revised"
          % (dis["distinct_claims"], dis["panelists"], dis["distinct_ratio"], dis["revised"]))
    print("  chain: %s" % ("verified" if chain.get("ok") else str(chain.get("reason"))))

    if cyc >= st["cycles_planned"]:
        st["status"] = "finished"
        _save_state(run_id, st)
        _finalise(run_id, st)
        return

    # next cycle: the panel argues against the operator's ruling
    case = A.all_cases()[st["case"]]
    panel = A.resolve_panel(st["case"], ",".join(p["slug"] for p in st["panel"]))
    nxt = cyc + 1
    prog, _ = make_progress(outdir, panel, st["cycles_planned"])
    nminutes = A.argue_cycle(case, panel, nxt, text, dry or st.get("dry_run"),
                             model_hint or st.get("model_hint", "auto"),
                             case.get("stages") or [], st["chain_head"], PREMISE_SOURCE,
                             prog)
    _write_cycle(outdir, nxt, nminutes)
    _clear_progress(outdir)
    st["cycle"] = nxt
    st["chain_head"] = nminutes[-1]["minute_sha"] if nminutes else st["chain_head"]
    st["status"] = "awaiting-judge"
    _save_state(run_id, st)
    print("\n  cycle %d argued against your ruling. %d minutes await you."
          % (nxt, len(nminutes)))


# ------------------------------------------------------------------ finalise

def _finalise(run_id: str, st: dict) -> None:
    """Write arena.json in the same shape run() does, plus the human markers."""
    outdir = A.ADIR / run_id
    payload = {
        "spec": "arena-v2-signed", "run_id": run_id, "built": TODAY,
        "case": st["case"], "case_title": st["case_title"], "as_of": st["as_of"],
        "question": st["question"], "cycles": len(st["rulings"]),
        "dry_run": bool(st.get("dry_run")),
        "panel": st["panel"],
        "mode": "human-judged",
        # Top-level and unmissable. --score keys off this.
        "human_judged": True,
        "judge": {
            "slug": HUMAN_SLUG,
            "blind_to": [],
            "NOT_BLIND": ["saw every model's name against its minute",
                          "read all minutes together, with time to think",
                          "may already know the real outcome"],
            "consequence": ("This run is NOT comparable with a blind-judged run and "
                            "--score refuses it. The panel rounds are identical; the "
                            "judging is not."),
        },
        "signing": {
            "scheme": "sha256 content hash + minute hash chain",
            "attests": ["the MODEL.md bytes each model actually read",
                        "the exact prompt sent", "the response body",
                        "the order of minutes", "the timestamp of each minute"],
            "does_not_attest": ["WHO produced the record — that needs a private "
                                "key, and a timestamp is not a key",
                                "that a dirty working tree matched any commit",
                                "WHICH person ruled — 'human-judge' is a role, not "
                                "an identity"],
            "verify": "python -m suites.arena --report %s" % run_id,
        },
        "sealed_outcome_withheld": False,
        "origin_score": None,
        "rounds": st["rulings"],
        "note": ("Panel rounds are identical to a blind run -- same argue_cycle(), so "
                 "models still claim in public before seeing each other and defend under "
                 "challenge. The JUDGE was a person who saw the model names and every "
                 "minute. DISAGREEMENT is still logged: one LLM over one corpus converges "
                 "for reasons that have nothing to do with the world, and a human judge "
                 "does not fix that."),
    }
    (outdir / "arena.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    print("\n  -> %s" % (outdir / "arena.json"))
    print("  human-judged: --score will refuse this run, by design.")


# ------------------------------------------------------------------ status

def status(run_id: str = "") -> None:
    runs = []
    for d in sorted(A.ADIR.glob("arena-*-human"), reverse=True):
        f = d / "awaiting-judge.json"
        if f.exists():
            runs.append(json.loads(f.read_text(encoding="utf-8")))
    if run_id:
        runs = [r for r in runs if r["run_id"] == run_id]
    if not runs:
        print("[arena/human] nothing pending")
        return
    for st in runs:
        print("[%s] %s" % (st["status"], st["run_id"]))
        print("   %s" % st["case_title"])
        print("   cycle %d of %d · panel: %s"
              % (st["cycle"], st["cycles_planned"],
                 ", ".join(p["slug"] for p in st["panel"])))
        if st["status"] == "awaiting-judge":
            ms = _read_cycle(A.ADIR / st["run_id"], st["cycle"])
            for m in ms:
                if m["round"] == 2:
                    print("     %-26s %-8s %s"
                          % (m["signed_by"], m["body"].get("move", ""),
                             str(m["body"].get("claim", ""))[:60]))


def main() -> None:
    ap = argparse.ArgumentParser(description="Arena judged by a person, not a blind model.")
    ap.add_argument("--start", action="store_true")
    ap.add_argument("--title", default="")
    ap.add_argument("--brief", default="")
    ap.add_argument("--brief-file", default="")
    ap.add_argument("--question", default="")
    ap.add_argument("--as-of", default="")
    ap.add_argument("--models", default="")
    ap.add_argument("--cycles", type=int, default=2)
    ap.add_argument("--case-slug", default="")
    ap.add_argument("--rule", default="", metavar="RUN_ID")
    ap.add_argument("--pick", default="")
    ap.add_argument("--ruling", default="")
    ap.add_argument("--because", default="")
    ap.add_argument("--pivot", default="")
    ap.add_argument("--resolve-by", default="")
    ap.add_argument("--confidence", type=float, default=0.0)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--run", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--model", default="auto")
    a = ap.parse_args()

    if a.start:
        brief = a.brief
        if a.brief_file:
            brief = Path(a.brief_file).read_text(encoding="utf-8")
        if not a.title:
            raise SystemExit("--start needs --title")
        models = [s.strip() for s in a.models.split(",") if s.strip()]
        start(a.title, brief, a.question, models, a.cycles, a.dry_run,
              a.model, a.as_of, a.case_slug)
    elif a.rule:
        rule(a.rule, a.pick, a.ruling, a.because, a.dry_run, a.model,
             a.confidence, a.pivot, a.resolve_by)
    else:
        status(a.run)


if __name__ == "__main__":
    main()
