"""End-to-end update loop for a tracked event — append a fact, re-read, diff the positions.

An event is not a thing you analyse once. New facts arrive, entities reposition,
and your own reading changes -- sometimes because the world moved and sometimes
because you ran the instrument again. Telling those two apart is the whole job
of this file.

THE STORE IS APPEND-ONLY. The case file's `## Chronology` is the source of
truth and only ever grows; every lens read is its own dated snapshot; every
arena run is its own tagged directory. Nothing is edited in place, so a
positioning history exists as a side effect rather than as a feature someone
has to maintain.

THE THREE LEVELS, each re-runnable by the same command:

  L0  entity positions   -- event_lens, per model's own registry.
                            position = (entity, read_on) -> act, role, floor,
                            credence read off the COST of the act
  L1  load-bearing floor -- arena, blind-judged; the pivot and which floor of
                            the emergence ladder it sits on
  L2  our own stability  -- the same case re-run with NO new facts. Whatever
                            moves is the noise floor, and no claimed change at
                            L0 or L1 smaller than it means anything.

L2 is not optional and is not a nicety. Measured in this repo: arena rulings
reproduce, per-minute rankings do not, and two codings of one historical case
agreed on 50% of verdicts. A diff that reports "the position moved because X
happened" without a noise floor beside it is unsupportable.

    python -m suites.event_update --case meta-coxon-resignation \\
        --add "2026-10-02 — Anthropic publishes evaluator MOU (url)"
    python -m suites.event_update --case meta-coxon-resignation --diff
    python -m suites.event_update --case meta-coxon-resignation --file-claim <run-id>
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
TODAY = datetime.date.today().isoformat()


def _models_dir(root):
    try:
        cfg = json.loads((root / "fleet.json").read_text(encoding="utf-8"))
        if cfg.get("models_dir"):
            return (root / cfg["models_dir"]).resolve()
    except Exception:
        pass
    return root.parent


TOOLS = _models_dir(ROOT)
CDIR = ROOT / "arena" / "cases"
LDIR = ROOT / "lenses"
ADIR = ROOT / "arena"

# The ladder's own axis definition, read from the map rather than restated here,
# so a change to the projection cannot silently disagree with this file.
def ladder() -> dict:
    try:
        d = json.loads((ROOT / "map" / "projections" / "em-ladder.v1.json")
                       .read_text(encoding="utf-8"))
        return d.get("axes", {}).get("vertical", {})
    except Exception:
        return {}


def add_fact(slug: str, fact: str) -> None:
    """Append one dated fact to the case's chronology. Never edits what is there.

    A correction to an earlier entry is appended as a new entry saying so. The
    same rule the ledgers follow: rewriting history makes a record that cannot
    be audited, and this record's whole purpose is being auditable.
    """
    f = CDIR / ("%s.md" % slug)
    if not f.exists():
        raise SystemExit("no case file at %s" % f)
    text = f.read_text(encoding="utf-8")
    if not re.match(r"^\s*\d{4}-\d{2}-\d{2}\s+[—-]", fact.strip()):
        print("  [warn] fact does not start with 'YYYY-MM-DD — '; appending anyway")
    m = re.search(r"^## Chronology.*$", text, re.M)
    if not m:
        raise SystemExit("case file has no '## Chronology' heading to append to")
    # insert at the END of the chronology section: before the next `## ` heading
    nxt = re.search(r"^## ", text[m.end():], re.M)
    cut = m.end() + (nxt.start() if nxt else len(text[m.end():]))
    entry = "\n- **%s** *(added %s)*\n" % (fact.strip(), TODAY)
    text = text[:cut].rstrip() + "\n" + entry + text[cut:]
    # bump `as of:` so downstream reads know the brief moved
    text = re.sub(r"^as of: \d{4}-\d{2}-\d{2}$", "as of: %s" % TODAY, text, count=1, flags=re.M)
    f.write_text(text, encoding="utf-8")
    print("  appended to %s and set as-of %s" % (f.name, TODAY))
    print("  next: re-read the event at all three levels ->")
    print("    python -m suites.event_lens --event %s --models <slugs> --tag %s" % (f, TODAY))
    print("    python -m suites.arena --case %s --tag %s" % (slug, TODAY))


def _positions(snap: Path) -> dict:
    """(entity -> reading) for one lens snapshot, flattened across lenses."""
    p = json.loads(snap.read_text(encoding="utf-8"))
    out = {}
    for l in p.get("lenses", []):
        if l.get("_error"):
            continue
        for e in l.get("entity_reads", []):
            if not e.get("touched"):
                continue
            out[(l["model"], str(e.get("entity")))] = e
    return out, p


def diff(slug: str) -> None:
    from suites.event_lens import snapshots
    snaps = snapshots(slug)
    lad = ladder()
    print("[event update] %s" % slug)
    if lad.get("meaning"):
        print("  ladder: %s" % lad["meaning"][:150])
    print()

    # ---- L2 FIRST. The noise floor gates everything printed after it. -------
    runs = sorted(ADIR.glob("arena-%s-*" % slug))
    rulings = []
    for r in runs:
        aj = r / "arena.json"
        if not aj.exists():
            continue
        d = json.loads(aj.read_text(encoding="utf-8"))
        ru = (d.get("rounds") or [{}])[-1].get("ruling", {})
        rulings.append({"run": r.name, "built": d.get("built"),
                        "pivot": str(ru.get("pivot") or ""), "src": ru.get("pivot_source"),
                        "by": ru.get("pivot_resolves_by"), "conf": ru.get("confidence"),
                        "sides": ru.get("minutes_by_side") or {},
                        "because": str(ru.get("pivot_because") or "")})
    # Group by the BRIEF, not by the calendar day. A rerun that crosses midnight
    # with no new facts is still a rerun of the same brief, and grouping on
    # `built` silently loses it -- which it did on the first run of this code.
    # The brief's identity is the case file's `as of:` plus its chronology length,
    # both of which `--add` bumps and nothing else changes.
    def brief_id() -> str:
        cf = CDIR / ("%s.md" % slug)
        if not cf.exists():
            return "?"
        t = cf.read_text(encoding="utf-8")
        m = re.search(r"^as of: (\d{4}-\d{2}-\d{2})", t, re.M)
        facts = len(re.findall(r"^- \*\*", t, re.M))
        return "%s/%dfacts" % (m.group(1) if m else "?", facts)

    bid = brief_id()
    groups = {}
    for r in rulings:
        # every run here argued the brief as it stands now unless a later --add
        # moved it; runs predating an --add are labelled by their own build date
        groups.setdefault(bid if r["built"] >= (bid.split("/")[0]) else r["built"], []).append(r)
    noise = [(d, v) for d, v in groups.items() if len(v) > 1]
    print("  L2 STABILITY — reruns of the SAME BRIEF (the noise floor)")
    if not noise:
        print("    none yet. Until the same brief has been argued twice, no movement")
        print("    below can be attributed to new information rather than resampling.")
    for d, v in noise:
        piv = {x["pivot"][:70] for x in v}
        print("    %s: %d runs, %d distinct pivot(s)" % (d, len(v), len(piv)))
        for x in v:
            print("      [%s] src=%-24s conf=%s" % (x["run"].split("-")[-1], x["src"], x["conf"]))
            print("          %s" % x["pivot"][:96])
        if len(piv) > 1:
            print("      -> THE PIVOT MOVES WITHOUT NEW INFORMATION. Treat any pivot")
            print("         change below as within noise unless it is larger than this.")
        else:
            print("      -> pivot stable across resampling; a later change is evidence.")
    print()

    # ---- L1 the load-bearing floor over time -------------------------------
    print("  L1 LOAD-BEARING FLOOR — one row per arena run")
    print("    %-22s %-10s %-24s %-6s %s" % ("run", "built", "pivot named by", "conf", "bearing"))
    for r in rulings:
        nb = sum(1 for v in r["sides"].values() if str(v).startswith("not-bear"))
        print("    %-22s %-10s %-24s %-6s %d/%d"
              % (r["run"][-22:], r["built"], r["src"], r["conf"],
                 len(r["sides"]) - nb, len(r["sides"])))
    if rulings:
        print("    latest pivot: %s" % rulings[-1]["pivot"][:110])
        print("    resolves: %s" % rulings[-1]["by"])
    print()

    # ---- L0 entity positions over time -------------------------------------
    print("  L0 ENTITY POSITIONS — %d lens snapshot(s)" % len(snaps))
    if len(snaps) < 2:
        print("    only one snapshot; nothing to diff yet.")
        cur, _ = _positions(snaps[-1]) if snaps else ({}, {})
        for (mdl, ent), e in sorted(cur.items()):
            print("    %-26s %-22s %-4s cred=%s" % (mdl[:24], ent[:20], e.get("floor"),
                                                    e.get("credence_implied")))
        return
    old, pold = _positions(snaps[-2])
    new, pnew = _positions(snaps[-1])
    print("    %s  ->  %s" % (snaps[-2].name, snaps[-1].name))
    keys = sorted(set(old) | set(new))
    moved = 0
    for k in keys:
        a, b = old.get(k), new.get(k)
        mdl, ent = k
        if a and not b:
            print("    -  %-24s %-20s no longer touched" % (mdl[:22], ent[:18]))
            moved += 1
        elif b and not a:
            print("    +  %-24s %-20s NEWLY touched  %-4s cred=%s"
                  % (mdl[:22], ent[:18], b.get("floor"), b.get("credence_implied")))
            moved += 1
        else:
            ca, cb = a.get("credence_implied"), b.get("credence_implied")
            fa, fb = a.get("floor"), b.get("floor")
            ra, rb = str(a.get("implied_role"))[:22], str(b.get("implied_role"))[:22]
            bits = []
            if isinstance(ca, (int, float)) and isinstance(cb, (int, float)) and abs(ca - cb) >= 0.05:
                bits.append("cred %.2f->%.2f" % (ca, cb))
            if fa != fb:
                bits.append("floor %s->%s" % (fa, fb))
            if ra != rb:
                bits.append("role %r->%r" % (ra, rb))
            if bits:
                print("    ~  %-24s %-20s %s" % (mdl[:22], ent[:18], "; ".join(bits)))
                moved += 1
    if not moved:
        print("    no position changed between these two snapshots.")
    print()
    print("  NOTE: the two snapshots above may differ because the world moved, or")
    print("  because the instrument was re-run. The L2 block is the only thing that")
    print("  tells you which. A change smaller than the noise floor is resampling.")


def file_claim(run_id: str) -> None:
    """Write the arena pivot into the graded ledger. This is the end of the loop.

    Until now nothing graded an arena ruling: the pivot carried a date and an
    observable and then sat in a JSON file nobody swept. The claim lands in the
    fleet's `decision_repo` -- the same destination pressure_converge writes to,
    so there is one rule for where computed claims go -- and that repo is in
    fleet.json's models[], which means INSTRUMENT_LEDGERS already covers it and
    grading_loop picks it up with no change to the loop.
    """
    f = ADIR / run_id / "arena.json"
    if not f.exists():
        raise SystemExit("no such run: %s" % run_id)
    d = json.loads(f.read_text(encoding="utf-8"))
    ru = (d.get("rounds") or [{}])[-1].get("ruling", {})
    if not ru.get("pivot") or not ru.get("pivot_resolves_by"):
        raise SystemExit("this run has no dated pivot -- nothing gradeable to file")
    cfg = json.loads((ROOT / "fleet.json").read_text(encoding="utf-8"))
    repo = cfg.get("decision_repo")
    if not repo:
        raise SystemExit("fleet.json has no decision_repo set -- nowhere to file")
    lp = TOOLS / repo / "predict" / "ledger.json"
    if not lp.exists():
        raise SystemExit("no ledger at %s (new_model does not create it -- see "
                         "analysis/CONVERGE_DEDUP_BUG_2026-09-17.md)" % lp)
    led = json.loads(lp.read_text(encoding="utf-8"))
    key = "arena-pivot:%s" % d["case"]
    if any(c.get("entity") == key and c.get("resolve_by") == ru["pivot_resolves_by"]
           for c in led["predictions"]):
        print("  already filed for %s by %s -- not duplicating"
              % (d["case"], ru["pivot_resolves_by"]))
        return
    chain = ((d.get("rounds") or [{}])[-1].get("chain") or {}).get("head", "")
    led["predictions"].append({
        "entity": key[:80],
        "name": ("arena pivot — %s" % d["case_title"])[:90],
        "made_on": TODAY, "resolve_by": ru["pivot_resolves_by"],
        "status": "open",
        "claim": str(ru.get("ruling"))[:250],
        "resolution_criteria": str(ru.get("pivot_observable") or ru.get("pivot"))[:400],
        "confidence": ru.get("confidence"),
        "mechanism": ("arena %s, judge %s, pivot named by %s; minutes chain head %s"
                      % (run_id, "scenario-v2-pivot", ru.get("pivot_source"), chain[:16])),
        "trace": "arena/%s/arena.json" % run_id,
        "prompt_version": "arena-pivot-v1"})
    lp.write_text(json.dumps(led, ensure_ascii=False, indent=2), encoding="utf-8")
    print("  filed -> %s/predict/ledger.json" % repo)
    print("    claim: %s" % str(ru.get("ruling"))[:96])
    print("    resolves %s, p=%s" % (ru["pivot_resolves_by"], ru.get("confidence")))
    print("  verify grading_loop sees it: python -m suites.grading_loop --dry")


def _bundle(slug: str, outdir: Path) -> list:
    """Assemble exactly what a reader of the article needs, and nothing else.

    What goes: the case file (the brief, including its chronology), every lens
    snapshot, every arena run's manifest and minutes, and a MANIFEST.md naming
    the commits each was produced from. What does NOT go: .env, the inbox
    (gitignored transcripts of other people's media), anything under povs/, and
    any file this function was not told about -- an allow-list, never a copy of
    a directory, because a publish step that copies whatever is lying around is
    how a credential leaves a machine.
    """
    import shutil
    outdir.mkdir(parents=True, exist_ok=True)
    sent = []

    def take(src: Path, rel: str):
        dst = outdir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        sent.append(rel)

    cf = CDIR / ("%s.md" % slug)
    if cf.exists():
        take(cf, "case/%s.md" % slug)
    for f in sorted((LDIR / slug).glob("*.json")) if (LDIR / slug).exists() else []:
        take(f, "lenses/%s" % f.name)
    for r in sorted(ADIR.glob("arena-%s-*" % slug)):
        if (r / "arena.json").exists():
            take(r / "arena.json", "arena/%s/arena.json" % r.name)
        for c in sorted(r.glob("cycle-*/minutes.jsonl")):
            take(c, "arena/%s/%s/minutes.jsonl" % (r.name, c.parent.name))

    import subprocess
    def head(d: Path) -> str:
        try:
            return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(d),
                                  capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            return "?"
    mani = []
    mani.append("# %s published bundle" % slug)
    mani.append("")
    mani.append("Built %s from MMR commit `%s`." % (TODAY, head(ROOT)))
    mani.append("")
    mani.append("Every reading here is v1 and dated: our model of these actors' models,")
    mani.append("built from what was publicly gatherable on the date each file carries.")
    mani.append("Nothing here is any actor's own claim about themselves.")
    mani.append("")
    mani.append("## Reproduce")
    mani.append("")
    mani.append("```bash")
    mani.append("python -m suites.event_lens --event case/%s.md --models <slugs>" % slug)
    mani.append("python -m suites.arena --case %s --tag <yours>" % slug)
    mani.append("python -m suites.event_update --case %s --diff" % slug)
    mani.append("```")
    mani.append("")
    mani.append("## Model versions these readings argued from")
    mani.append("")
    seen = set()
    for r in sorted(ADIR.glob("arena-%s-*" % slug)):
        aj = r / "arena.json"
        if not aj.exists():
            continue
        for x in json.loads(aj.read_text(encoding="utf-8")).get("panel", []):
            seen.add(x["slug"])
    for m in sorted(seen):
        d = TOOLS / m
        mani.append("- `%s` @ %s" % (m, head(d) if d.exists() else "?"))
    mani.append("")
    mani.append("## Files")
    mani.append("")
    for x in sent:
        mani.append("- `%s`" % x)
    (outdir / "MANIFEST.md").write_text("\n".join(mani) + "\n", encoding="utf-8")
    sent.append("MANIFEST.md")
    return sent


def publish(slug: str, target: str, dest: str, apply: bool) -> None:
    """Stage the bundle, then upload it. DRY BY DEFAULT.

    Publishing is outward-facing and effectively irreversible -- once a bundle
    is on a public bucket it may be cached, mirrored or indexed whatever happens
    afterwards. So this stages and prints the command, and uploads only with
    --apply. The staged directory is inspectable before anything leaves.
    """
    out = ROOT / "publish" / slug
    sent = _bundle(slug, out)
    print("[publish] staged %d file(s) -> %s" % (len(sent), out))
    for x in sent[:12]:
        print("    %s" % x)
    if len(sent) > 12:
        print("    ... and %d more" % (len(sent) - 12))

    # preflight: the repo's own share check, on the staged tree
    import subprocess
    bad = []
    for f in out.rglob("*"):
        if f.is_file():
            t = f.read_text(encoding="utf-8", errors="ignore")[:200000]
            for pat in (r"sk-or-v1-[A-Za-z0-9]{20,}", r"sk-ant-[A-Za-z0-9-]{20,}",
                        r"AIza[0-9A-Za-z_-]{30,}", r"ghp_[A-Za-z0-9]{30,}"):
                if re.search(pat, t):
                    bad.append(f.name)
    if bad:
        raise SystemExit("credential-shaped string in staged files: %s — NOT publishing"
                         % ", ".join(sorted(set(bad))))
    print("  preflight: no credential-shaped strings in the staged tree")

    if target == "gcs":
        cmd = ["gsutil", "-m", "rsync", "-r", "-d", str(out), dest.rstrip("/") + "/" + slug]
    elif target == "r2":
        cmd = ["npx", "wrangler", "r2", "object", "put", "--recursive",
               dest.rstrip("/") + "/" + slug, "--file", str(out)]
    else:
        raise SystemExit("--target must be gcs or r2")
    print("\n  command: %s" % " ".join(cmd))
    if not apply:
        print("  DRY RUN — nothing uploaded. Re-run with --apply to publish.")
        print("  Inspect %s first; a publish cannot be taken back once cached." % out)
        return
    r = subprocess.run(cmd, capture_output=True, text=True)
    print((r.stdout or "")[-1500:])
    if r.returncode != 0:
        print((r.stderr or "")[-1500:])
        raise SystemExit("upload failed (rc=%d)" % r.returncode)
    print("  uploaded.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--add", help="one dated fact to append to the chronology")
    ap.add_argument("--diff", action="store_true", help="positions over time, all 3 levels")
    ap.add_argument("--file-claim", dest="file_claim", help="arena run-id whose pivot to file")
    ap.add_argument("--publish", choices=["gcs", "r2"], help="stage + upload the bundle")
    ap.add_argument("--dest", default="", help="gs://bucket/path or <r2-bucket>/path")
    ap.add_argument("--apply", action="store_true",
                    help="actually upload (without it, --publish stages and prints only)")
    a = ap.parse_args()
    if a.publish:
        if not a.dest:
            raise SystemExit("--publish needs --dest (gs://bucket/path or bucket/path)")
        return publish(a.case, a.publish, a.dest, a.apply)
    if a.add:
        return add_fact(a.case, a.add)
    if a.file_claim:
        return file_claim(a.file_claim)
    if a.diff:
        return diff(a.case)
    ap.print_help()


if __name__ == "__main__":
    main()
