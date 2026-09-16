"""Expert timeline — per commentator: what they said, what happened, how the view moved.

The fleet timeline answers "what is expected, by when". This answers a different
question the fleet could not previously ask: **who said what, when, and were
they right?**

Per commentator, in date order:

  SAID        every dated claim registered in ai-expert-calibration, with the
              source and the resolution criteria WE wrote (not theirs).
  HAPPENED    observed events from the fleet timeline that fall inside a claim's
              window and share its domain — the evidence accumulating against it
              while it is still open.
  MOVED       where the same commentator has spoken more than once, successive
              positions in order, so a changed view is visible as a change
              rather than being silently overwritten by the latest quote.
  CONFLICTS   claims explicitly registered as contradicting another
              commentator's, with the decider that settles them.

THREE DISCIPLINES, carried from ai-expert-calibration:

  * NOTHING IS GRADED HERE. Every claim is `open` until its date arrives. A
    commentator with no resolved claims has no track record, and this file says
    so rather than implying one from tone or prominence.
  * NO RETROSPECTIVE SCORING. Claims were registered with criteria before
    resolution. This module only reads them; it never adds or edits a claim.
  * WITHIN-TYPE ONLY. A unit-economics claim and a capability forecast are
    different difficulties. Accuracy is reported per domain, never pooled into
    a single "who is most reliable" number.

  python -m suites.expert_timeline --build
"""
from __future__ import annotations

import argparse
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


def _models_dir(root):
    try:
        cfg = json.load((root / "fleet.json").open(encoding="utf-8"))
        if cfg.get("models_dir"):
            return (root / cfg["models_dir"]).resolve()
    except Exception:
        pass
    return root.parent


TOOLS = _models_dir(ROOT)
BUILT = datetime.date.today().isoformat()

# domain -> which observed-event observers count as evidence for that domain.
# Kept explicit rather than inferred: a loose keyword match would attach
# irrelevant events to claims and manufacture the appearance of evidence.
DOMAIN_OBSERVERS = {
 "capability-trajectory": {"ai-frontier-cadence", "ai-rsi-timeline", "ai-scaling-orthodoxy",
                           "ai-capability-tracker"},
 "research-trajectory":   {"ai-rsi-timeline", "ai-scaling-orthodoxy"},
 "compute-economics":     {"ai-compute-concentration", "ai-compute-buildout", "ai-capex-signal"},
 "lab-economics":         {"ai-bubble-thesis", "ai-compute-concentration"},
 "lab-strategy":          {"ai-lab-revealed-priorities", "ai-frontier-cadence",
                           "lab-moves", "ai-pressure"},
 "china-policy":          {"ai-china-strategy", "ai-china-argument"},
 "geopolitics":           {"ai-us-policy-direction", "ai-china-strategy"},
 "policy":                {"ai-us-policy-direction", "ai-regulation-teeth",
                           "overton-tracker", "ai-pressure"},
 "cyber":                 {"ai-cyber-offense-defense", "ai-incident-severity",
                           "ai-oversight-lag"},
 "market-sentiment":      {"ai-bubble-thesis", "ai-public-backlash"},
 "labor":                 {"ai-labor-attribution"},
 "media":                 {"ai-public-backlash"},
 "engineering practice":  {"ai-labor-attribution"},
}


def load_timeline():
    f = ROOT / "timeline.json"
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("timeline", [])
    except ValueError:
        return []


def build() -> None:
    cdir = TOOLS / "ai-expert-calibration" / "claims"
    if not cdir.exists():
        raise SystemExit("no ai-expert-calibration/claims — nothing to build")

    observed = [r for r in load_timeline() if r.get("type") == "observed"]
    experts = []

    for f in sorted(cdir.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        claims = sorted(d.get("claims", []), key=lambda c: str(c.get("source_date", "")))
        rows = []
        for c in claims:
            dom = c.get("domain", "")
            obs_set = DOMAIN_OBSERVERS.get(dom, set())
            sd, rb = str(c.get("source_date", "")), str(c.get("resolve_by", ""))
            # events inside the claim's window, in its domain: evidence accruing
            # while the claim is still open. NOT a grade.
            ev = [{"date": e["date"], "item": e["item"][:200], "source": e.get("source", "")}
                  for e in observed
                  if e.get("observer") in obs_set and sd and e.get("date")
                  and sd <= e["date"] <= (rb or "9999")]
            rows.append({
                "id": c.get("id", ""),
                "said": c.get("quote", ""),
                "said_on": sd,
                "domain": dom,
                "resolve_by": rb,
                "status": c.get("status", "open"),
                "criteria": c.get("resolution_criteria", ""),
                "conflicts_with": c.get("conflicts_with"),
                "conditional_on": c.get("conditional_on"),
                "source": c.get("source", ""),
                "happened_since": ev,
                "days_to_resolve": (
                    (datetime.date.fromisoformat(rb) - datetime.date.fromisoformat(BUILT)).days
                    if rb and len(rb) == 10 else None),
            })

        # "moved": more than one dated statement means the view has a trajectory.
        # source_date is dirty by construction: some sources give only a year
        # ("2026"). Pad for sorting, but only measure a span when both ends are
        # full dates -- inventing a day to compute a day-count would be exactly
        # the false precision event_history warns about.
        dates = sorted({r["said_on"] for r in rows if r["said_on"]})
        full = [x for x in dates if len(x) == 10]
        moved = None
        if len(dates) > 1:
            moved = {"spoke_on": dates,
                     "span_days": ((datetime.date.fromisoformat(full[-1])
                                    - datetime.date.fromisoformat(full[0])).days
                                   if len(full) > 1 else None),
                     "note": ("Positions are listed in date order. A later claim that "
                              "contradicts an earlier one is a CHANGED VIEW and should be "
                              "recorded as such, not treated as a correction of the record.")}

        doms = sorted({r["domain"] for r in rows if r["domain"]})
        experts.append({
            "slug": f.stem,
            "commentator": d.get("commentator", f.stem),
            "role": d.get("role", ""),
            "registered": d.get("registered", ""),
            "note": d.get("note", ""),
            "domains": doms,
            "n_claims": len(rows),
            "n_open": sum(1 for r in rows if r["status"] == "open"),
            "n_resolved": sum(1 for r in rows if r["status"] != "open"),
            "n_conflicts": sum(1 for r in rows if r.get("conflicts_with")),
            "next_resolution": min([r["resolve_by"] for r in rows if r["resolve_by"]], default=""),
            "moved": moved,
            "claims": rows,
        })

    experts.sort(key=lambda e: (-e["n_claims"], e["commentator"]))

    # conflicts, paired both ways, with the decider from the claim itself
    conflicts = []
    seen = set()
    for e in experts:
        for c in e["claims"]:
            cw = c.get("conflicts_with")
            if not cw:
                continue
            key = tuple(sorted([e["slug"] + "/" + c["id"], cw]))
            if key in seen:
                continue
            seen.add(key)
            other_slug = cw.split("/")[0]
            other = next((x for x in experts if x["slug"] == other_slug), None)
            oc = None
            if other:
                oc = next((x for x in other["claims"] if cw.endswith(x["id"])), None)
            conflicts.append({
                "a": {"commentator": e["commentator"], "id": c["id"],
                      "said": c["said"], "said_on": c["said_on"]},
                "b": ({"commentator": other["commentator"], "id": oc["id"],
                       "said": oc["said"], "said_on": oc["said_on"]}
                      if other and oc else {"ref": cw}),
                "decider": c.get("criteria", ""),
                "resolve_by": c.get("resolve_by", ""),
            })

    payload = {
        "spec": "expert-timeline-v1",
        "built": BUILT,
        "note": ("Per commentator: what they SAID (dated, with our resolution criteria), "
                 "what HAPPENED inside each claim's window, whether their view MOVED across "
                 "statements, and which claims CONFLICT with another commentator's. "
                 "NOTHING IS GRADED — every claim is open until its date arrives, so no "
                 "commentator has a track record yet and this file does not imply one. "
                 "Accuracy is reported per domain when it exists: a unit-economics claim and "
                 "a capability forecast are different difficulties and must not be pooled."),
        "experts": len(experts),
        "claims": sum(e["n_claims"] for e in experts),
        "resolved": sum(e["n_resolved"] for e in experts),
        "conflicts": conflicts,
        "roster": experts,
    }
    out = ROOT / "expert_timeline.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    print("[expert-timeline] %d commentators · %d claims · %d resolved -> %s"
          % (len(experts), payload["claims"], payload["resolved"], out))
    for e in experts:
        sp = e["moved"]["span_days"] if e["moved"] else None
        m = (" · moved over %dd" % sp) if sp else (" · moved" if e["moved"] else "")
        cf = " · %d conflict" % e["n_conflicts"] if e["n_conflicts"] else ""
        print("    %-18s %d claims (%d open) · next %s%s%s"
              % (e["commentator"][:18], e["n_claims"], e["n_open"],
                 e["next_resolution"] or "—", m, cf))
    if conflicts:
        print("    %d registered conflict(s) between commentators" % len(conflicts))


def main():
    ap = argparse.ArgumentParser(description="Build the per-expert timeline.")
    ap.add_argument("--build", action="store_true")
    a = ap.parse_args()
    if not a.build:
        ap.print_help()
        return
    build()


if __name__ == "__main__":
    main()
