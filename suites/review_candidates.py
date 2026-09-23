"""Put candidate models in front of the challenge panel before any repo exists.

`explore_gaps --filter` checks FORM: is there a date, an actor, a switch-off
answer, a rival. It cannot check whether the mechanism is real, whether the
claim is already true, or whether a boring explanation covers it. Those are
judgements, and the fleet already has a body for them -- the mandatory challenge
panel from `brainstorm`: devil's advocate, base-rate librarian, simplicity
judge.

Running `brainstorm` once per candidate would be 47 runs. This reviews them in
GROUPS, which is also better review: a panel seeing eight candidates together
can say "three of these are the same claim" and "this one is already true",
neither of which is visible one at a time.

THE VERDICTS, and what each means for the candidate:

  BUILD     the mechanism is real, the claim is not already settled, and a
            boring explanation does not cover it
  MERGE     it duplicates another candidate in the group; the panel names which
  SHARPEN   worth building, but the observable or the rival needs work; the
            panel says what specifically
  DROP      already true, unfalsifiable in practice, or the base rate makes it
            uninformative

A candidate the panel cannot fault is not thereby good -- it is unfaulted, which
is weaker. The panel is asked to say so rather than inventing an objection.

  python -m suites.review_candidates --group 8
  python -m suites.review_candidates --group 8 --min-strength 2
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "explore"
TODAY = datetime.date.today().isoformat()

PANEL = """You are a CHALLENGE PANEL reviewing candidate forecasting models
before any of them is built. Three challengers sit on this panel and you must
answer as all three:

  DEVIL'S ADVOCATE — what is the strongest case that this candidate is wrong,
  or that its mechanism is not what produces the observable?

  BASE-RATE LIBRARIAN — what normally happens in this reference class? If the
  observable resolves the predicted way most of the time anyway, the claim
  carries no information when it lands.

  SIMPLICITY JUDGE — is there a boring explanation (incentives, timing, cost,
  incompetence, regulation that already exists) that produces the same
  observable without the stated mechanism?

THE CANDIDATES, reviewed as a group so you can see duplication between them:
{block}

For EACH candidate return a verdict:

  "BUILD"    the mechanism is real, the claim is not already settled, and a
             boring explanation does not cover it
  "MERGE"    it duplicates another candidate in this group — name which
  "SHARPEN"  worth building, but the observable or rival needs work — say what
  "DROP"     already true, unfalsifiable in practice, or the base rate makes it
             uninformative

RULES:
- A candidate you cannot fault is UNFAULTED, not good. Say so plainly rather
  than inventing an objection to look rigorous.
- If two candidates would resolve on the same real-world event, that is a MERGE
  even if their mechanisms are worded differently.
- Never assert what any person or company believes, wants or fears.
- If the claim is ALREADY TRUE as of {today}, that is a DROP and you must say
  what makes it already true.

Return STRICT JSON:
{{
 "reviews": [
  {{"slug": "<candidate slug>",
    "verdict": "BUILD|MERGE|SHARPEN|DROP",
    "devils_advocate": "<the strongest case against, 1-2 sentences>",
    "base_rate": "<what normally happens in this reference class>",
    "simpler": "<the boring explanation, or 'none found'>",
    "merge_with": "<slug, or null>",
    "sharpen": "<what specifically to change, or null>",
    "unfaulted": true|false}}
 ],
 "group_note": "<anything visible only across the group — duplication, a shared assumption, a gap none of them covers>"
}}"""


def block_for(cands: list) -> str:
    out = []
    for c in cands:
        out.append(
            "- slug: %s\n  mechanism: %s\n  observable: %s\n  resolve_by: %s\n"
            "  rival: %s\n  switch_off: %s"
            % (c.get("slug"), (c.get("mechanism") or "")[:240],
               (c.get("observable") or "")[:240], c.get("resolve_by"),
               (c.get("rival") or "")[:160], (c.get("switch_off") or "")[:160]))
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Challenge-panel review of candidates.")
    ap.add_argument("--group", type=int, default=8, help="candidates per panel")
    ap.add_argument("--min-strength", type=int, default=0)
    ap.add_argument("--batch", type=int, default=2, help="panels run concurrently")
    ap.add_argument("--model", default="auto")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    f = OUT / "candidates.kept.json"
    if not f.exists():
        raise SystemExit("no kept candidates — run explore_gaps --filter first")
    cands = json.loads(f.read_text(encoding="utf-8"))["candidates"]
    if a.min_strength:
        before = len(cands)
        cands = [c for c in cands if c.get("strength", 0) >= a.min_strength]
        print("  %d of %d candidates at strength >= %d"
              % (len(cands), before, a.min_strength))

    # Group BY REGION where possible: duplication is likeliest inside a region,
    # and a panel that sees a whole region at once can say "these eight are
    # three claims", which is the finding worth having.
    by_region = collections.defaultdict(list)
    for c in cands:
        by_region[c.get("region", "?")].append(c)
    groups = []
    for region, rows in by_region.items():
        for i in range(0, len(rows), a.group):
            groups.append((region, rows[i:i + a.group]))

    from suites import arena as A
    A._load_env()
    print("[review] %d candidates -> %d panel(s) of <=%d"
          % (len(cands), len(groups), a.group))

    reviews, notes = [], []
    for i in range(0, len(groups), a.batch):
        chunk = groups[i:i + a.batch]
        prompts = [PANEL.format(block=block_for(rows), today=TODAY)
                   for _r, rows in chunk]
        labels = [r.split(" · ")[0][:40] for r, _rows in chunk]
        print("\n  panel %d-%d/%d: %s"
              % (i + 1, min(i + a.batch, len(groups)), len(groups), ", ".join(labels)))
        bodies = A._call_many(a.model, prompts, a.dry_run,
                              on_done=lambda j, b: print("    reviewed: %s" % labels[j]))
        for (region, _rows), b in zip(chunk, bodies):
            if b.get("_error") or b.get("_unparsed"):
                print("    ! %s" % str(b.get("_error") or "unparsed")[:70])
                continue
            for r in (b.get("reviews") or []):
                r["region"] = region
                reviews.append(r)
            if b.get("group_note"):
                notes.append({"region": region, "note": b["group_note"]})
        counts = collections.Counter(r.get("verdict") for r in reviews)
        print("    running: %s" % dict(counts))

    by_slug = {c["slug"]: c for c in cands}
    for r in reviews:
        c = by_slug.get(r.get("slug"))
        if c:
            r["strength"] = c.get("strength")
            r["title"] = c.get("title")

    out = OUT / "reviews.json"
    out.write_text(json.dumps({"generated": TODAY, "reviews": reviews,
                               "group_notes": notes}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    counts = collections.Counter(r.get("verdict") for r in reviews)
    print("\n  VERDICTS: %s" % dict(counts))
    unf = sum(1 for r in reviews if r.get("unfaulted"))
    print("  unfaulted (not the same as good): %d" % unf)
    print("  -> %s" % out)


if __name__ == "__main__":
    main()
