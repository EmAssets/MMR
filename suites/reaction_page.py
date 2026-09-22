"""Turn a blast_radius output into the shape the published reaction page reads.

blast_radius writes `responded_to` / `evidence`; the page reads `to` / `ev`.
That divergence is not worth "fixing" in either place -- the extractor's names
are right for a record and the page's are right for a renderer -- so it is
translated once, here, rather than by hand per case.

Source tier is assigned from the case file's own Sources section: a node whose
evidence traces to a primary transcript or the issuing body is `primary`, two
or more independent outlets is `reported`, anything else `single`. It is never
guessed upward; unknown means `single`, which renders hollow and says so.

  python -m suites.reaction_page --case unga81-ai --title "..." --out out.json
  python -m suites.reaction_page --all --out garden/../asset-index.json
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

ROOT = Path(__file__).resolve().parents[1]
RDIR = ROOT / "arena" / "cases" / "reaction"


def case_sources(slug: str) -> list:
    """URLs from the case file's Sources section, so tiers are read not guessed."""
    f = RDIR / ("%s.md" % slug)
    if not f.exists():
        return []
    t = f.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^##\s*Sources?\b(.*)$", t, re.M | re.S)
    return re.findall(r"https?://[^\s)]+", m.group(1) if m else "")


def tier_for(node: dict, sources: list) -> str:
    """primary | reported | single, from what the ACT can be traced to.

    TWO DIFFERENT THINGS, and conflating them was a real bug here. `inferred`
    on a node means the EDGE was reasoned rather than quoted -- "Trump was
    answering the debate Rahman opened" is an inference even though the speech
    itself is a UN transcript. Source tier is about the ACT, not the edge.

    Downgrading every inferred edge to `single` published nine UN-transcript
    acts as single-sourced, which is exactly backwards: the acts are as well
    evidenced as anything gets. The edge's own uncertainty is already carried
    by the `inferred` flag, which the page renders separately.
    """
    off = [u for u in sources if re.search(r"//(www\.)?[a-z0-9.-]*\b(un|europa|gov|who|nato)\.",
                                           u)]
    if off:
        return "primary"
    return "reported" if len(sources) >= 2 else "single"


def convert(slug: str, title: str = "", center: str = "") -> dict:
    f = RDIR / ("%s.blast.json" % slug)
    if not f.exists():
        raise SystemExit("no blast file: %s" % f)
    d = json.loads(f.read_text(encoding="utf-8"))
    src = case_sources(slug)
    nodes = []
    for n in d.get("nodes", []):
        nodes.append({
            "id": n["id"],
            "label": n.get("label") or n["id"],
            "kind": n.get("kind") or "artifact",
            "date": n.get("date") or "",
            "to": n.get("responded_to"),
            "src": tier_for(n, src),
            "act": n.get("act") or "",
            "ev": n.get("evidence") or "",
            "refs": [[u.split("//", 1)[-1].split("/")[0], u] for u in src[:4]],
            **({"inferred": True} if n.get("inferred") else {}),
        })
    return {
        "spec": "reaction-layers-v1",
        "case": slug,
        "title": title or d.get("title") or slug,
        "updated": datetime.date.today().isoformat(),
        "center": center or d.get("center") or next(
            (n["id"] for n in nodes if not n["to"]), nodes[0]["id"] if nodes else ""),
        "nodes": nodes,
        "note": d.get("note", ""),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="blast_radius output -> page data.")
    ap.add_argument("--case", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--center", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    d = convert(a.case, a.title, a.center)
    print("[page] %s — %d nodes, centre %s" % (d["case"], len(d["nodes"]), d["center"]))
    tiers = {}
    for n in d["nodes"]:
        tiers[n["src"]] = tiers.get(n["src"], 0) + 1
    print("  tiers: %s" % ", ".join("%s=%d" % kv for kv in sorted(tiers.items())))
    if a.out:
        Path(a.out).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print("  -> %s" % a.out)


if __name__ == "__main__":
    main()
