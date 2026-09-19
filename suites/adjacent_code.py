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
   PIN IT. State the specific THRESHOLD EVENT you are dating from (a plant opening,
   a standard ratified, a product shipping, a patent expiring) with a source, AND
   name the plausible alternative anchor you REJECTED and why. Two coders dating
   "electric power" from Pearl Street 1882 versus the first AC system produce gaps
   differing by decades, and a number that swings on an unstated choice is not a
   measurement. `capability_anchor` and `capability_anchor_rejected` are required.
2. first_substitution — the earliest notable product doing an OLD job by the new
   mechanism. Name it, date it, say what it replaced.
3. TWO dependent categories, not one — this is the field most responsible for
   coders disagreeing, so it is split deliberately:

   earliest_dependent_category — the EARLIEST thing you can defend as failing the
     switch-off test, even if it is niche, small or contested.
   clearest_dependent_category — the one where the switch-off test is LEAST
     arguable, even if it arrived much later and is obvious in hindsight.

   They are often the same; when they differ, the spread between their dates is
   itself the finding and must not be collapsed into one number.

   For EACH: name it, date it, and state WHICH ACTIVITY becomes incoherent when
   the tool is removed — a concrete activity a person could be doing, not a
   diffuse social condition. "Synchronised national attention" is not an activity;
   "a household listening to a scheduled programme at the same hour as millions of
   others" is. If you cannot name the concrete activity, this is SUBSTITUTION and
   you must say so rather than stretching.

   If no category passes, set exists:false on both and say why.
4. components — the independently-created capabilities the dependent category
   required. For each: was it built FOR this category, or for something unrelated?
   Give each a `canonical` name: the short, standard name of the underlying tool
   ("GPS", "lithium-ion battery", "TCP/IP", "vacuum tube", "interchangeable parts")
   rather than a descriptive phrase, so the same component named in two different
   cases matches.
4b. last_key_component — of those components, WHICH ARRIVED LAST. The tool, not
   the person. This is the one the category was waiting for. Name it, date it,
   and say whether it was created for this purpose or for something unrelated.
   If several arrived together, say so and name the one you would defend.
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
"capability_anchor":"the threshold event dated, with source",
"capability_anchor_rejected":"the alternative anchor not used, and why",
"earliest_dependent_category":{"exists":true,"what":"...","date":"YYYY",
  "activity_that_collapses":"...","source":"..."},
"clearest_dependent_category":{"exists":true,"what":"...","date":"YYYY",
  "activity_that_collapses":"...","source":"..."},
"gap_years_earliest":0,"gap_years_clearest":0,
"components":[{"what":"...","canonical":"...","built_for_this":false,"note":"..."}],
"last_key_component":{"what":"...","canonical":"...","date":"YYYY","built_for_this":false,"source":"..."},
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
    for which in ("earliest", "clearest"):
        dep = _year((d.get("%s_dependent_category" % which) or {}).get("date"))
        if cap and dep:
            d["gap_years_%s" % which] = dep - cap
        else:
            d["gap_years_%s" % which] = None
    # `gap_years` stays as the headline number for compatibility with the first
    # 12 cases, and is the EARLIEST defensible one -- the conservative reading of
    # "how long until this made something new possible".
    d["gap_years"] = d.get("gap_years_earliest")
    ge, gc = d.get("gap_years_earliest"), d.get("gap_years_clearest")
    if isinstance(ge, int) and isinstance(gc, int):
        # The spread between the earliest and clearest reading is the coder's own
        # uncertainty, made visible instead of averaged away. A case where these
        # differ by decades is not a measurement, whatever its median.
        d["gap_spread"] = abs(gc - ge)
    else:
        d["gap_spread"] = None
    d["gap_basis"] = ("recomputed from capability_date and the earliest/clearest "
                      "dependent-category dates")
    d["sought_as_counterexample"] = bool(counter)
    d["coded_on"] = TODAY
    d["coded_by"] = model
    return d


def _year(s) -> int | None:
    m = re.search(r"(1[6-9]\d\d|20\d\d)", str(s or ""))
    return int(m.group(1)) if m else None


def score() -> None:
    """Report the model's consequences over every coded case.

    C1 is no longer a fixed window. The author's revision, 2026-09-18: as the
    stock of available components grows, the wait for the last key should get
    SHORTER, because more of the combination is already lying around when a new
    capability lands. That is a claim about a TREND, and a trend is a harder and
    more interesting bet than a constant -- a fixed ten-year threshold would be
    satisfied by a world where nothing changes.
    """
    cdir = RDIR / "cases"
    cases = []
    for f in sorted(cdir.glob("*.json")) if cdir.exists() else []:
        if f.name == "SAMPLE.json":
            continue
        try:
            cases.append(json.loads(f.read_text(encoding="utf-8")))
        except ValueError:
            continue
    if not cases:
        raise SystemExit("no coded cases yet -- run --tool first")

    # RELIABILITY GATE. Everything below is arithmetic over codings; if the
    # codings do not reproduce, the arithmetic measures the coder. This runs
    # first and says so before any bet is reported.
    dbl = [c for c in cases if "passes_agree" in c]
    agree = [c for c in dbl if c.get("passes_agree")]
    rel = (len(agree) / len(dbl)) if dbl else None

    print("[adjacent-possible] %d coded cases" % len(cases))
    print()
    if rel is None:
        print("RELIABILITY: unknown -- no case was double-coded. Run without --once.")
    else:
        print("RELIABILITY: %d/%d double-coded cases agree on verdict (%.0f%%)"
              % (len(agree), len(dbl), 100 * rel))
        gd = [c["gap_disagreement"] for c in dbl if isinstance(c.get("gap_disagreement"), int)]
        if gd:
            gd_s = sorted(gd)
            print("             gap disagreement between passes: median %d years, max %d"
                  % (gd_s[len(gd_s) // 2], max(gd_s)))
        if rel < 0.67:
            print()
            print("  !! BELOW THE DELETION CLAUSE THRESHOLD (two coders differing on more")
            print("     than a third of cases). The numbers below are reported for")
            print("     diagnosis only and DO NOT test the model. Fix the instrument.")
    print()

    def _capyear(c):
        m = re.search(r"(1[6-9]\d\d|20\d\d)", str(c.get("capability_date") or ""))
        return int(m.group(1)) if m else None

    pts = [(_capyear(c), c["gap_years"]) for c in cases
           if _capyear(c) and isinstance(c.get("gap_years"), int)]
    pts.sort()

    print("C1 (revised) THE WINDOW COMPRESSES: gap shrinks as capability arrives later.")
    if len(pts) < 6:
        print("     too few dated cases (%d) to read a trend" % len(pts))
    else:
        half = len(pts) // 2
        early, late = pts[:half], pts[half:]
        me = sorted(g for _, g in early)[len(early) // 2]
        ml = sorted(g for _, g in late)[len(late) // 2]
        print("     earlier half (capability %d-%d, n=%d): median gap %d years"
              % (early[0][0], early[-1][0], len(early), me))
        print("     later   half (capability %d-%d, n=%d): median gap %d years"
              % (late[0][0], late[-1][0], len(late), ml))
        # Deliberately crude: a rank correlation would imply a precision these
        # codings do not have. The direction is the claim; the magnitude is not.
        print("     direction: %s   (WRONG if the later half's median is HIGHER)"
              % ("COMPRESSING" if ml < me else "NOT compressing -- later half is %s" %
                 ("equal" if ml == me else "longer")))
        spreads = [c["gap_spread"] for c in cases if isinstance(c.get("gap_spread"), int)]
        if spreads:
            ss = sorted(spreads)
            print("     coder's own earliest-vs-clearest spread: median %d years"
                  % ss[len(ss) // 2])
            print("     (a trend smaller than this spread is not a trend)")
    print()

    same = [c for c in cases if c.get("same_person") is True]
    known = [c for c in cases if c.get("same_person") is not None]
    disp = [c for c in cases if (c.get("displaced") or {}).get("happened")]
    sub = [c for c in cases if (c.get("became_substrate") or {}).get("happened")]
    n = len(known) or 1
    print("C2  last key IS the credited person: %d/%d (%.0f%%)   (WRONG if > 50%%)"
          % (len(same), len(known), 100 * len(same) / n))
    print("C3  displaced an older practice within 25y: %d/%d (%.0f%%)   (WRONG if < 67%%)"
          % (len(disp), len(cases), 100 * len(disp) / len(cases)))
    print("C4  became substrate for a later category: %d/%d (%.0f%%)   (WRONG if < 50%%)"
          % (len(sub), len(cases), 100 * len(sub) / len(cases)))

    nodep = [c for c in cases
             if not ((c.get("earliest_dependent_category") or
                      c.get("first_dependent_category") or {}).get("exists"))]
    if nodep:
        print("      %d case(s) produced NO dependent category: %s"
              % (len(nodep), ", ".join(c["tool"][:26] for c in nodep)))
    print()
    if len(cases) < 30:
        print("NOTE: %d cases. A trend over this few is a shape, not a result."
              % len(cases))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", help="the tool/capability to code")
    ap.add_argument("--counter", action="store_true",
                    help="mark this case as sought BECAUSE it may break the bets")
    ap.add_argument("--score", action="store_true", help="report the bets over coded cases")
    ap.add_argument("--model", default="anthropic/claude-sonnet-4")
    ap.add_argument("--once", action="store_true",
                    help="single coding (default is two independent passes)")
    ap.add_argument("--skip-existing", action="store_true",
                    help="leave an already-coded tool alone (makes a batch resumable)")
    a = ap.parse_args()
    if a.score:
        return score()
    if not a.tool:
        ap.print_help()
        return
    cdir = RDIR / "cases"
    cdir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", a.tool.lower()).strip("-")[:60]
    out = cdir / f"{slug}.json"
    if a.skip_existing and out.exists():
        print("[skip] %s already coded" % a.tool)
        return

    # TWO INDEPENDENT PASSES BY DEFAULT.
    #
    # The 2026-09-18 agreement test found 50% verdict disagreement between two
    # codings of the same tool -- past the deletion clause's one-third threshold.
    # A single pass reports a number whose instability is invisible. Two passes
    # make the disagreement part of the record, so the scorer can refuse to
    # average over cases the coder cannot reproduce.
    d = code_one(a.tool, a.model, a.counter)
    if not a.once:
        d2 = code_one(a.tool, a.model, a.counter)
        agree = (d.get("verdict") == d2.get("verdict"))
        g1, g2 = d.get("gap_years"), d2.get("gap_years")
        d["second_pass"] = {
            "verdict": d2.get("verdict"), "gap_years": g1 if False else g2,
            "capability_anchor": d2.get("capability_anchor"),
            "earliest_dependent_category": d2.get("earliest_dependent_category"),
            "confidence": d2.get("confidence"),
        }
        d["passes_agree"] = bool(agree)
        d["gap_disagreement"] = (abs(g1 - g2) if isinstance(g1, int) and isinstance(g2, int)
                                 else None)

    (cdir / f"{slug}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    dep = d.get("earliest_dependent_category") or d.get("first_dependent_category") or {}
    print("[coded] %s%s" % (d["tool"], "  (counter-sought)" if a.counter else ""))
    print("  capability %s (%s)" % (d.get("capability_date"), str(d.get("capability_anchor"))[:58]))
    print("  earliest category %s = gap %s   clearest %s = gap %s   spread %s"
          % (dep.get("date") or "none", d.get("gap_years_earliest"),
             (d.get("clearest_dependent_category") or {}).get("date") or "none",
             d.get("gap_years_clearest"), d.get("gap_spread")))
    print("  verdict: %s (conf %s)" % (d.get("verdict"), d.get("confidence")))
    if not a.once:
        print("  second pass: %s  (verdict %s, gap diff %s)"
              % ("AGREES" if d.get("passes_agree") else "DISAGREES",
                 d["second_pass"]["verdict"], d.get("gap_disagreement")))
    if dep.get("activity_that_collapses"):
        print("  collapses: %s" % str(dep["activity_that_collapses"])[:92])
    print("  -> cases/%s.json" % slug)


if __name__ == "__main__":
    main()
