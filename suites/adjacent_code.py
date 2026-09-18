"""Code a tool against the adjacent-possible test — web-grounded, one case per run.

THE TEST, and the only one this model needs: switch the tool off. If what remains
is the same activity, slower or dearer, that is SUBSTITUTION. If the activity
stops making sense, the tool made a new possibility viable — a DEPENDENT CATEGORY.

Each run researches ONE tool and writes `adjacent-possible/cases/<slug>.json`:
capability date, first substitution, first dependent category, the gap between
them, and the four structural questions the model's consequences turn on. Every
date carries a source or the field stays empty — an uncited date is a guess, and
a guess in a date field is the one thing this model cannot survive.

    python -m suites.adjacent_code --tool "GPS in consumer devices"
    python -m suites.adjacent_code --tool "Containerised shipping" --counter
    python -m suites.adjacent_code --score      # the bets, over every coded case

WHY --counter EXISTS. A sample containing only cases that fit is evidence about
the sampler, not about the world. `--counter` marks a case as sought BECAUSE it
looked likely to violate the bets, and `--score` reports the counter-sought
subset separately. A run of cases that all confirm, none of which was chosen to
break the pattern, is reported as what it is: unfalsified, not corroborated.
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

from harness.openrouter import chat  # noqa: E402
from harness.actors import parse_json  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _load_env() -> None:
    """Load .env before any chat() call.

    Without this the backend setting in .env is invisible, chat() falls through
    to OpenRouter, and returns empty text with 'OPENROUTER_API_KEY not set' --
    which looks exactly like a model that answered nothing. Both arena.py and
    grade_claims.py carry this same note because the same omission bit them
    first; this file made the identical mistake on its first run.
    """
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            import os
            os.environ.setdefault(k.strip(), v.strip())


_load_env()


def _models_dir(root):
    try:
        cfg = json.loads((root / "fleet.json").read_text(encoding="utf-8"))
        if cfg.get("models_dir"):
            return (root / cfg["models_dir"]).resolve()
    except Exception:
        pass
    return root.parent


TOOLS = _models_dir(ROOT)
RDIR = TOOLS / "adjacent-possible"
TODAY = datetime.date.today().isoformat()

CODE_PROMPT = """You have LIVE WEB ACCESS. Today is {today}. Code ONE historical tool
against a specific test. Research it; do not answer from memory alone.

THE TOOL: {tool}

THE TEST — apply it literally, it is the whole instrument:
  Switch the tool off. If what remains is the SAME ACTIVITY, only slower or more
  expensive, that is SUBSTITUTION. If the activity itself stops making sense — not
  degraded, incoherent — that is a DEPENDENT CATEGORY.

  A refrigerator without electricity is not an inconvenient icebox; it is not a
  refrigerator. That is a dependent category. An electric lamp without electricity
  is a worse lamp, and lamps already existed. That is substitution.

WHAT TO FIND, each with a date and a source you actually consulted:

1. capability_date — when the capability became practically available (not first
   demonstrated in a lab: available enough to build on).
2. first_substitution — the earliest notable product doing an OLD job by the new
   mechanism. Name it, date it, say what it replaced.
3. first_dependent_category — the earliest category that FAILS the switch-off test:
   remove the tool and the activity is incoherent. Name it, date it, and state
   WHICH ACTIVITY becomes incoherent. If you cannot name the incoherent activity,
   this is substitution and you must say so rather than stretching.
4. components — the independently-created capabilities the dependent category
   required. For each: was it built FOR this category, or for something unrelated?
5. last_key_person — who supplied the final missing component, and who is popularly
   CREDITED with the category. Same person or not?
6. displaced — did the new category measurably reduce the viability of an older
   practice within ~25 years? Name the practice and the evidence.
7. became_substrate — did the category itself become infrastructure that later
   categories assume? Name a later category that assumes it.

DISCIPLINE:
- A date with no source is worse than no date. Leave it empty and say why.
- Do not smooth the case to fit the test. If the tool produced NO dependent
  category, or produced one almost immediately, that is a real and interesting
  answer — say so plainly. Cases that break the pattern are the valuable ones.
- Popular-history claims ("X invented Y") are frequently wrong about the last
  component. Check who supplied the missing piece, not who is on the plaque.

Return ONLY JSON:
{"tool":"...","capability_date":"YYYY or YYYY-MM","capability_source":"...",
"first_substitution":{"what":"...","date":"YYYY","replaced":"...","source":"..."},
"first_dependent_category":{"exists":true,"what":"...","date":"YYYY",
  "activity_that_collapses":"...","source":"..."},
"gap_years":0,
"components":[{"what":"...","built_for_this":false,"note":"..."}],
"last_key_person":"...","credited_person":"...","same_person":false,
"displaced":{"happened":true,"practice":"...","within_25y":true,"source":"..."},
"became_substrate":{"happened":true,"later_category":"...","source":"..."},
"verdict":"substitution-then-category | substitution-only | category-immediately",
"confidence":0.0,
"doubts":"what is weakest or most contested in this coding"}"""


def code_one(tool: str, model: str, counter: bool) -> dict:
    p = CODE_PROMPT.replace("{today}", TODAY).replace("{tool}", tool)
    d = None
    for _ in range(3):
        r = chat(model + ":online", [{"role": "user", "content": p}],
                 temperature=0.2, max_tokens=2600, research=True)
        if r.error:
            continue
        try:
            d = parse_json(r.text)
        except Exception:
            d = None
        if d and d.get("tool"):
            break
        d = None
    if not d:
        raise SystemExit("coding failed for %r" % tool)

    # Recompute the gap rather than trusting it: it is the number consequence 1
    # turns on, and a model that has just been asked for two dates will sometimes
    # hand back a difference that matches neither.
    cap = _year(d.get("capability_date"))
    dep = _year((d.get("first_dependent_category") or {}).get("date"))
    if cap and dep:
        d["gap_years"] = dep - cap
        d["gap_basis"] = "recomputed from capability_date and first_dependent_category.date"
    else:
        d["gap_years"] = None
        d["gap_basis"] = "not computable — a required date was uncited or absent"
    d["sought_as_counterexample"] = bool(counter)
    d["coded_on"] = TODAY
    d["coded_by"] = model
    return d


def _year(s) -> int | None:
    m = re.search(r"(1[6-9]\d\d|20\d\d)", str(s or ""))
    return int(m.group(1)) if m else None


def score() -> None:
    """Report the model's consequences over every coded case."""
    cdir = RDIR / "cases"
    cases = []
    for f in sorted(cdir.glob("*.json")) if cdir.exists() else []:
        try:
            cases.append(json.loads(f.read_text(encoding="utf-8")))
        except ValueError:
            continue
    if not cases:
        raise SystemExit("no coded cases yet — run --tool first")

    gaps = sorted(c["gap_years"] for c in cases if isinstance(c.get("gap_years"), int))
    med = gaps[len(gaps) // 2] if gaps else None
    same = [c for c in cases if c.get("same_person") is True]
    known_person = [c for c in cases if c.get("same_person") is not None]
    disp = [c for c in cases if (c.get("displaced") or {}).get("happened")]
    sub = [c for c in cases if (c.get("became_substrate") or {}).get("happened")]
    counters = [c for c in cases if c.get("sought_as_counterexample")]
    nodep = [c for c in cases if not (c.get("first_dependent_category") or {}).get("exists")]

    print("[adjacent-possible] %d coded cases (%d sought as counterexamples)"
          % (len(cases), len(counters)))
    print()
    print("C1  median capability->category gap: %s years   (WRONG if < 5)"
          % (med if med is not None else "n/a"))
    if gaps:
        print("      gaps: %s" % ", ".join(str(g) for g in gaps))
    n = len(known_person) or 1
    print("C2  last key IS the credited person: %d/%d (%.0f%%)   (WRONG if > 50%%)"
          % (len(same), len(known_person), 100 * len(same) / n))
    print("C3  displaced an older practice within 25y: %d/%d (%.0f%%)   (WRONG if < 67%%)"
          % (len(disp), len(cases), 100 * len(disp) / len(cases)))
    print("C4  became substrate for a later category: %d/%d (%.0f%%)   (WRONG if < 50%%)"
          % (len(sub), len(cases), 100 * len(sub) / len(cases)))
    if nodep:
        print("      %d case(s) produced NO dependent category: %s"
              % (len(nodep), ", ".join(c["tool"][:28] for c in nodep)))
    print()

    # The honesty line. A sample nobody tried to break is not evidence of a
    # pattern; it is evidence of a search. This is printed every time, including
    # (especially) when every bet passes.
    if not counters:
        print("NOTE: no case was sought as a counterexample. These bets are UNFALSIFIED,")
        print("      not corroborated — run --counter on tools you expect to break them.")
    else:
        cg = [c["gap_years"] for c in counters if isinstance(c.get("gap_years"), int)]
        print("Counter-sought subset (%d): gaps %s" % (len(counters), cg or "n/a"))
        print("      A bet that survives only outside this subset has not survived.")
    if len(cases) < 8:
        print("NOTE: %d cases is too few to move any of these bets. Treat as a pilot."
              % len(cases))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", help="the tool/capability to code")
    ap.add_argument("--counter", action="store_true",
                    help="mark this case as sought BECAUSE it may break the bets")
    ap.add_argument("--score", action="store_true", help="report the bets over coded cases")
    ap.add_argument("--model", default="anthropic/claude-sonnet-4")
    a = ap.parse_args()
    if a.score:
        return score()
    if not a.tool:
        ap.print_help()
        return
    d = code_one(a.tool, a.model, a.counter)
    cdir = RDIR / "cases"
    cdir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", a.tool.lower()).strip("-")[:60]
    (cdir / f"{slug}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    dep = d.get("first_dependent_category") or {}
    print("[coded] %s%s" % (d["tool"], "  (counter-sought)" if a.counter else ""))
    print("  capability %s -> dependent category %s = gap %s"
          % (d.get("capability_date"), dep.get("date") or "none", d.get("gap_years")))
    print("  verdict: %s (conf %s)" % (d.get("verdict"), d.get("confidence")))
    if dep.get("activity_that_collapses"):
        print("  collapses: %s" % str(dep["activity_that_collapses"])[:96])
    print("  -> cases/%s.json" % slug)


if __name__ == "__main__":
    main()
