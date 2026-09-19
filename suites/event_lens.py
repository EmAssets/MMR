"""One event, read through each model's OWN entities — what did each actor do, per lens.

The arena asks models to argue. This asks something narrower and more literal:
each model in this fleet watches a DIFFERENT set of entities (`watch.json`), so
the same news lands on different objects. `ai-influence-chain` watches draft-text
and dockets. `ai-public-backlash` watches sentiment-polls and state-enactments.
`ai-pressure` watches three named labs and a regulator.

So "what happened" is not one answer. It is one answer per registry, and the
DIFFERENCES between them are the finding: an event that shows up on four
registries is operating at a different scale than one that shows up on one.

For each model this records, per entity it actually watches:

  * did this event touch this entity at all (many will not -- that is data)
  * what OBSERVABLE ACTION did the entity take, from public behaviour
  * what future does that action only make sense in
  * what role the actor takes in that future
  * the floor of the emergence ladder the action operates on

Interiority is banned, as everywhere in this fleet: "this action only makes sense
if X" is a claim about an action and is allowed; "they believe X" is not.

    python -m suites.event_lens --event arena/cases/meta-coxon-resignation.md \\
        --models pressure-model,ai-influence-chain,ai-public-backlash
    python -m suites.event_lens --event <file> --panel meta-coxon-resignation
    python -m suites.event_lens --compare <slug>     # the cross-lens table
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


def _load_env() -> None:
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_env()

from harness.openrouter import chat  # noqa: E402
from harness.actors import parse_json  # noqa: E402


def _models_dir(root):
    try:
        cfg = json.loads((root / "fleet.json").read_text(encoding="utf-8"))
        if cfg.get("models_dir"):
            return (root / cfg["models_dir"]).resolve()
    except Exception:
        pass
    return root.parent


TOOLS = _models_dir(ROOT)
ODIR = ROOT / "lenses"
TODAY = datetime.date.today().isoformat()

LENS_PROMPT = """Today is {today}. You are reading ONE event through ONE model's own
registry of watched entities. You are not asked what you think happened. You are asked
what happened TO THESE ENTITIES, and nothing else.

THE MODEL AND ITS MECHANISM:
{mechanism}

THE ENTITIES THIS MODEL WATCHES — these and no others:
{entities}

THE EVENT:
{event}

FOR EACH ENTITY ABOVE, in order, report:

- touched: true/false — did this event actually reach this entity? MOST ENTITIES IN
  MOST EVENTS ARE NOT TOUCHED. false is the common and correct answer, and a lens that
  reports every entity touched is not a lens, it is a horoscope. If false, say so and
  move to the next; do not invent a connection.
- action: the OBSERVABLE act this entity took in response — something dated and public.
  If the entity is an abstract object the model tracks (a draft text, a docket, a poll
  series) rather than an actor, report what measurably changed about it, or "no
  measurable change".
- implied_future: the future in which that act makes sense. Phrase it as "this act
  only makes sense if ___". Never as what anyone believes, wants or fears.
- implied_role: the part this entity takes in that future — gatekeeper, claimant,
  witness, instrument, obstacle, bystander. One word plus a short clause.
- floor: which level of the emergence ladder the ACT operates on, and why:
  E8 minds · E9 cultures/memeplexes · E10 institutions with enforcement ·
  E11 organizations acting coherently · E12 states · E13 civilizations
  The floor of the act, not the floor of its subject matter. A blog post about
  state policy is an E9 act about an E12 subject.

THEN, about the lens itself:

- reached: how many of this model's entities the event actually reached
- verdict: does this event fall INSIDE this model's domain, at its EDGE, or OUTSIDE it?
  Outside is a respectable answer and is more useful than a stretched reading.
- what_this_lens_cannot_see: the part of this event that is structurally invisible
  from these entities. Be specific about what is missing, not modest in general.

DISCIPLINE: no claims about intent, belief, fear or desire — for any actor, including
ones you think are obvious. An act plus the future it presupposes is the whole output.

Return ONLY JSON:
{"model":"{slug}","entity_reads":[{"entity":"...","touched":true,"action":"...",
"implied_future":"...","implied_role":"...","floor":"E10","floor_because":"..."}],
"reached":0,"verdict":"inside|edge|outside","what_this_lens_cannot_see":"..."}"""


def mechanism_of(slug: str) -> tuple[str, list]:
    """The model's own words, and the entities it actually watches."""
    d = TOOLS / slug
    md = d / "MODEL.md"
    text = md.read_text(encoding="utf-8", errors="replace") if md.exists() else ""
    # The mechanism as the model states it: the first substantive block. Kept
    # short deliberately -- the lens is supposed to read through the mechanism,
    # not to re-litigate the whole document.
    head = "\n".join(text.splitlines()[:40])[:2200]
    ents = []
    w = d / "watch.json"
    if w.exists():
        try:
            cfg = json.loads(w.read_text(encoding="utf-8"))
            ents = cfg.get("entities", []) or []
        except ValueError:
            ents = []
    return head, ents


def read_through(slug: str, event: str, model_hint: str) -> dict:
    head, ents = mechanism_of(slug)
    if not ents:
        return {"model": slug, "_error": "no entities in watch.json — nothing to read through"}
    elist = "\n".join(
        "- %s: %s" % (e.get("id") or e.get("name"), str(e.get("watch") or e.get("name") or ""))[:240]
        for e in ents)
    p = (LENS_PROMPT.replace("{today}", TODAY).replace("{mechanism}", head)
         .replace("{entities}", elist).replace("{event}", event)
         .replace("{slug}", slug))
    for _ in range(3):
        r = chat(model_hint, [{"role": "user", "content": p}],
                 temperature=0.2, max_tokens=2600)
        if getattr(r, "error", None):
            continue
        try:
            d = parse_json(r.text)
        except Exception:
            continue
        if d and d.get("entity_reads"):
            # Recount rather than trust: `reached` is the number the cross-lens
            # comparison turns on, and a model that has just listed ten entities
            # will sometimes report a count matching none of them.
            d["reached"] = sum(1 for x in d["entity_reads"] if x.get("touched"))
            d["entities_watched"] = len(ents)
            d["read_on"] = TODAY
            return d
    return {"model": slug, "_error": "lens read failed or unparseable"}


def compare(slug: str) -> None:
    f = ODIR / ("%s.json" % slug)
    if not f.exists():
        raise SystemExit("no lens run at %s" % f)
    p = json.loads(f.read_text(encoding="utf-8"))
    lenses = [l for l in p["lenses"] if not l.get("_error")]
    print("[event lens] %s" % p["event_name"])
    print("  %d lenses, %d usable" % (len(p["lenses"]), len(lenses)))
    print()
    print("  %-28s %-8s %-8s %s" % ("model", "reached", "verdict", "floors it read"))
    print("  " + "-" * 74)
    for l in sorted(lenses, key=lambda x: -x.get("reached", 0)):
        floors = sorted({str(e.get("floor")) for e in l["entity_reads"] if e.get("touched")})
        print("  %-28s %d/%-6d %-8s %s"
              % (l["model"], l.get("reached", 0), l.get("entities_watched", 0),
                 l.get("verdict", "?"), ", ".join(floors) or "-"))
    print()

    # THE CROSS-LENS FINDING. An actor that only one registry sees is operating
    # at that lens's scale; one that every registry sees is the event's centre of
    # gravity. This is the number the whole suite exists to produce.
    seen: dict = {}
    for l in lenses:
        for e in l["entity_reads"]:
            if not e.get("touched"):
                continue
            key = str(e.get("entity"))
            seen.setdefault(key, []).append((l["model"], str(e.get("floor")),
                                             str(e.get("implied_role"))[:48]))
    print("  entities touched, by how many lenses saw them:")
    for k, v in sorted(seen.items(), key=lambda kv: -len(kv[1])):
        print("   %d lens(es)  %-34s %s" % (len(v), k[:34],
                                            ", ".join("%s[%s]" % (m, f) for m, f, _ in v)[:76]))
    print()
    outside = [l["model"] for l in lenses if l.get("verdict") == "outside"]
    if outside:
        print("  OUTSIDE their domain (correct abstention): %s" % ", ".join(outside))
    print()
    print("  what each lens says it CANNOT see:")
    for l in lenses:
        print("   %-28s %s" % (l["model"], str(l.get("what_this_lens_cannot_see"))[:88]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", help="path to the event/case file")
    ap.add_argument("--models", help="comma-separated model slugs")
    ap.add_argument("--panel", help="reuse an arena SCENARIO_PANELS panel by case slug")
    ap.add_argument("--compare", help="print the cross-lens table for a saved run")
    ap.add_argument("--model", default="anthropic/claude-sonnet-4")
    a = ap.parse_args()
    if a.compare:
        return compare(a.compare)
    if not a.event:
        ap.print_help()
        return
    ev = Path(a.event)
    event = ev.read_text(encoding="utf-8", errors="replace")
    slugs = []
    if a.models:
        slugs = [s.strip() for s in a.models.split(",") if s.strip()]
    elif a.panel:
        from suites.arena import SCENARIO_PANELS
        slugs = SCENARIO_PANELS.get(a.panel, [])
    if not slugs:
        raise SystemExit("give --models or a --panel that exists")

    out = []
    for s in slugs:
        print("[lens] %s ..." % s, flush=True)
        d = read_through(s, event, a.model)
        if d.get("_error"):
            print("   %s" % d["_error"])
        else:
            print("   reached %d/%d entities, verdict %s"
                  % (d.get("reached", 0), d.get("entities_watched", 0), d.get("verdict")))
        out.append(d)
    ODIR.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", ev.stem.lower()).strip("-")[:60]
    (ODIR / ("%s.json" % slug)).write_text(
        json.dumps({"event_name": ev.stem, "event_file": str(ev), "read_on": TODAY,
                    "lenses": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n  -> lenses/%s.json" % slug)
    print("  compare with: python -m suites.event_lens --compare %s" % slug)


if __name__ == "__main__":
    main()
