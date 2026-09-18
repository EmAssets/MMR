"""Pressure convergence — resultant-vector analysis of an office/arena, with a full
REASONING TRACE attached to every prediction.

The synthesis of four family mechanisms, made computable:
  * pressure model — magnitude = severity x credibility; phi-repair boosts, decay cuts;
    dilemma -> delay absorbs unresolved tension when nothing forces the clock
  * threshold (Sangama) — >=3 INDEPENDENT cross-domain pressures aligned on one outcome
    = convergence, the strongest directional signal; vectors sharing >50% of their
    source structure are ONE vector (the independence test)
  * mesh P8 (structural law) — total magnitude drives P(some transition) regardless of
    alignment; alignment determines destination confidence; high-tension resolutions
    arrive from the unmonitored dimension
  * loop dominance (feedback-loops paper) — fast pressures dominate short horizons,
    slow ones long horizons: the outcome distribution is horizon-dependent

TWO-STAGE BY DESIGN: an LLM extracts the pressure-vector table (judgment: sources,
directions, magnitudes, evidence — fed by the pressure_watch dynamics log where one
exists); then PLAIN CODE computes independence dedup, convergence counts, the resultant,
the tension index, and the two-horizon outcome distribution. The probability is
arithmetic over an auditable table, not an LLM's gut number — so when a prediction
misses, the post-mortem can point at the exact vector whose weight was wrong.

Artifacts per run: my-model/converge/<slug>.json (the complete reasoning trace)
+ <slug>.md (readable) + a ledger claim whose mechanism cites the trace. This is the
template for reasoning-traced predictions generally.

  python -m suites.pressure_converge --target "Chair of the my-model" \
      --question "September 2026 my-model rate decision"
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

from harness.openrouter import chat  # noqa: E402
from harness.actors import parse_json  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

def _models_dir(root):
    """Where THIS instance's model repos live.

    fleet.json may set models_dir to give the instance a private namespace;
    without it, models are siblings of the instance (the original layout).
    Two instances under one parent otherwise read each other's models.
    """
    try:
        import json as _json
        cfg = _json.load((root / "fleet.json").open(encoding="utf-8"))
        if cfg.get("models_dir"):
            return (root / cfg["models_dir"]).resolve()
    except Exception:
        pass
    return root.parent


TOOLS = _models_dir(ROOT)
from harness.fleet import DECISION_REPO
RDIR = TOOLS / (DECISION_REPO or "decision-model")

SEVERITY = {"low": 1.0, "med": 2.0, "high": 3.0}
TS_FACTOR = {"short": {"fast": 1.0, "medium": 0.6, "slow": 0.3},
             "long": {"fast": 0.3, "medium": 0.8, "slow": 1.0}}
TOTAL_BANDS = [(2.0, "low"), (5.0, "moderate"), (8.0, "high"), (99.0, "saturated")]


def credibility_from_demonstration(demonstrated: str, today: str) -> tuple[float, str]:
    """Derive credibility from WHEN the consequence last actually landed.

    This is phi-attenuation as the pressure model states it: a stake announced
    but never demonstrated decays, and enforcement events are repair. v1 asked
    the LLM for this number directly, which put a gut number in the one place
    the module docstring promises arithmetic over an auditable table.

    The bands are coarse on purpose. A finer curve would imply we can tell a
    9-month-old demonstration from an 11-month-old one, and we cannot.
    """
    d = (demonstrated or "").strip().lower()
    # "never" ANYWHERE wins, and it is checked before any date is looked for.
    #
    # The models do not answer with a bare "never" -- they explain: "never --
    # law effective 2026-01-01, no AG enforcement action found", "never (only
    # preliminarily suspended 2026-04-27; no merits ruling)". Those are
    # undemonstrated stakes that happen to cite a date for when the POWER
    # arrived. Measured 2026-09-18: matching the date first gave all four such
    # vectors 0.85, the top band, which is the exact inverse of what they say.
    # Phi-attenuation is about whether the consequence LANDED, not whether the
    # authority exists.
    if not d or "never" in d or d in ("none", "n/a", "-", "not yet", "no"):
        # Not zero: an undemonstrated threat from a body that plainly could
        # impose it still moves behaviour. Just weak.
        return 0.25, "never demonstrated"
    m = re.search(r"(\d{4})-(\d{2})", d)
    if not m:
        return 0.35, "demonstration date unparseable (%s)" % demonstrated[:24]
    try:
        then = datetime.date(int(m.group(1)), int(m.group(2)), 1)
        now = datetime.date.fromisoformat(today)
    except ValueError:
        return 0.35, "demonstration date invalid (%s)" % demonstrated[:24]
    months = (now.year - then.year) * 12 + (now.month - then.month)
    if months < 0:
        return 0.35, "demonstration dated in the future (%s)" % demonstrated[:24]
    if months <= 12:
        return 0.85, "demonstrated %d months ago" % months
    if months <= 36:
        return 0.60, "demonstrated %d months ago" % months
    if months <= 120:
        return 0.40, "demonstrated %d months ago (stale)" % months
    return 0.25, "last demonstrated %d months ago (lapsed)" % months

VECTOR_PROMPT_V1 = """You have LIVE WEB ACCESS. Today is {today}. You are extracting a PRESSURE-VECTOR
TABLE for a resultant-vector analysis. Institutional analysis of a public office/arena — publicly
documented stakes only, never anyone's inner life.

TARGET: {target}
QUESTION (the decision/outcome space): {question}

RECENT MONITORED DYNAMICS (from the standing pressure monitor; use and extend via the web):
{dynamics}

Extract EVERY significant pressure currently bearing on the target with respect to the question.
For each vector:
- id: v1, v2, ...
- source_form: who/what installs it (a named market, statute, party, electorate, press, foreign
  power, allied institution, military, technology constraint)
- domain: market | state-legal | party-political | electorate | press | foreign | institutional |
  military | technological
- pushes_toward: which OUTCOME it pushes (use short outcome labels; be consistent)
- severity: low | med | high  (what is lost/gained if defied/obeyed)
- credibility: 0.0-1.0 — has the consequence been DEMONSTRATED recently (phi-repair events raise
  it; lapsed/undemonstrated threats lower it). Cite the demonstration or its absence.
- timescale: fast (days-weeks) | medium (months) | slow (years)
- evidence: one dated line
- overlaps: list of other vector ids sharing >50% of their source structure with this one
  (same underlying coalition/balance-sheet/command chain counted twice is a double-count)

Then:
- outcomes: MUTUALLY EXCLUSIVE resolutions of the question — concrete decisions/actions one of
  which will actually happen (not desiderata, themes, or qualities), PLUS "delay/no-change"
  always. Every vector's pushes_toward MUST be one of these outcome labels.
- forcing_deadline: true/false — is there a date by which a decision is structurally forced
  (a scheduled meeting/vote/expiry)? Name it if true.
- unmonitored_dimensions: 1-2 dimensions orthogonal to the pressures above where a resolving
  surprise could arrive (the analytical blind spot).
- novel_regime: true if this pressure combination has no clear historical precedent.

Return ONLY JSON:
{"vectors":[{"id":"v1","source_form":"...","domain":"...","pushes_toward":"...",
"severity":"low|med|high","credibility":0.0,"timescale":"fast|medium|slow",
"evidence":"...","overlaps":[]}],
"outcomes":["...","delay/no-change"],
"forcing_deadline":false,"deadline":"YYYY-MM-DD or empty",
"unmonitored_dimensions":["..."],"novel_regime":false}"""


# ---------------------------------------------------------------------------
# v2 — a pressure must name its consequence.
#
# WHY THIS EXISTS. Measured 2026-09-18 over 105 extracted vectors: 72% of the
# AI-domain ones and 84% of the older imported ones cited evidence that named no
# consequence at all. They were FACTS -- a bill unreleased, a task force filing
# nothing, an agency missing a deadline, a group "reported to be resisting" --
# weighted by the arithmetic as if they were stakes.
#
# That is not what the pressure model means by pressure. P6 is explicit: a form
# broadcasts "proposition S -> loss lambda if violated", and the agent carries a
# branch weighted by the installer's credibility. No nameable loss, no branch.
# So v2 splits the old free-text `evidence` into the tuple P6 actually requires
# and makes `consequence` mandatory: a vector that cannot fill it is a fact
# about the world, not a pressure on the target, and is excluded.
#
# Credibility is no longer asked for. v1 let the model hand back a number
# (median 0.60, range 0.15-0.90) in the one place the docstring promised
# arithmetic over an auditable table. v2 asks instead for `demonstrated` -- the
# date the consequence last actually landed, or "never" -- and derives
# credibility from it in code, which is phi-attenuation as the model states it:
# a stake announced but never demonstrated decays, and enforcement events are
# repair. The model's own guess is kept alongside as `credibility_llm` so a
# postmortem can ask which was better.
# ---------------------------------------------------------------------------
VECTOR_PROMPT = """You have LIVE WEB ACCESS. Today is {today}. You are extracting a PRESSURE-VECTOR
TABLE for a resultant-vector analysis. Institutional analysis of a public office/arena — publicly
documented stakes only, never anyone's inner life.

TARGET: {target}
QUESTION (the decision/outcome space): {question}

RECENT MONITORED DYNAMICS (from the standing pressure monitor; use and extend via the web):
{dynamics}

WHAT COUNTS AS A PRESSURE — read this before extracting anything.

A pressure is an INSTALLED STAKE: some installer has made it true that if the target does X, the
target loses something nameable. The test is one sentence:

    "If {target} ignores this, it loses ______ , and that has happened to someone on ______ ."

A FACT IS NOT A PRESSURE. These are all facts, and none belongs in the table on its own:
  - a bill that has not passed, or whose text is unreleased
  - an agency that missed a deadline, or has filed nothing
  - a group "reported to be resisting", lobbying, or expressing concern
  - a trend, a poll, a market movement, a stated preference or intention
  - anything happening to a DIFFERENT actor that only "indirectly reaches" this target

Each becomes a pressure only when you can name what THIS target forfeits by ignoring it. An
unreleased bill is not pressure; a committee chair who has killed two nominations over it is. If
you cannot name the loss, leave the row out. A short table of real stakes is the correct output;
padding it with news is the failure this format exists to prevent.

For each vector:
- id: v1, v2, ...
- source_form: WHO installs it — a named institution, statute, court, market, electorate, foreign
  power, counterparty. Not a topic, not a trend, not "public opinion" in the abstract.
- domain: market | state-legal | party-political | electorate | press | foreign | institutional |
  military | technological
- proposition: what the installer demands, stated so the target could VIOLATE it
  ("do not ship without pre-deployment disclosure", "keep rates above X", "do not export to Y")
- consequence: what the target actually loses if it violates — REQUIRED, and specific. A fine with
  a size, a blocked licence, an injunction, a lost contract, a seat, market access, a funding
  stream. "Reputational damage" or "political pressure" is not a consequence; name the mechanism.
- demonstrated: the date (YYYY-MM-DD) this consequence was LAST ACTUALLY IMPOSED on this target or
  a comparable one, or "never" if it has only ever been announced or implied. Be strict: a threat
  issued is not a demonstration; an enforcement action actually landed is.
- pushes_toward: which OUTCOME it pushes (must be one of the outcome labels below, verbatim)
- severity: low | med | high  (the SIZE of that consequence relative to the target's resources)
- timescale: fast (days-weeks) | medium (months) | slow (years) — how quickly the installer can
  actually impose it, given its own procedure. A court with a motion pending is fast; a statute
  needing passage is slow.
- evidence: one dated, sourced line supporting the consequence and the demonstration date
- installed_via: the concrete instrument — a docket number, statute section, contract clause,
  scheduled vote, licence condition. If there is no instrument, the stake is probably not installed.
- overlaps: ONLY vectors sharing the SAME INSTALL CHAIN — the same statute, the same coalition, the
  same balance sheet, the same command structure. Two pressures that merely point the same way are
  NOT overlapping. Be conservative: list an id here only if a single decision by a single body
  would remove both at once.

Then:
- outcomes: MUTUALLY EXCLUSIVE resolutions of the question — concrete decisions/actions one of
  which will actually happen (not desiderata, themes, or qualities), PLUS "delay/no-change"
  always. Every vector's pushes_toward MUST be one of these outcome labels, spelled identically.
- forcing_deadline: true/false — is there a date by which a decision is structurally forced
  (a scheduled meeting/vote/expiry)? Name it if true.
- unmonitored_dimensions: 1-2 dimensions orthogonal to the pressures above where a resolving
  surprise could arrive (the analytical blind spot).
- novel_regime: true if this pressure combination has no clear historical precedent.
- excluded: facts you considered and LEFT OUT because no consequence could be named. List them —
  2-6 short lines, each with why. This is required output, not an afterthought: it is how a reader
  checks that the filter ran rather than that the web was thin.

Return ONLY JSON:
{"vectors":[{"id":"v1","source_form":"...","domain":"...","proposition":"...","consequence":"...",
"demonstrated":"YYYY-MM-DD|never","pushes_toward":"...","severity":"low|med|high",
"timescale":"fast|medium|slow","evidence":"...","installed_via":"...","overlaps":[]}],
"outcomes":["...","delay/no-change"],
"forcing_deadline":false,"deadline":"YYYY-MM-DD or empty",
"unmonitored_dimensions":["..."],"novel_regime":false,
"excluded":[{"fact":"...","why_not_a_pressure":"..."}]}"""


def dedup(vectors: list[dict]) -> tuple[list[dict], list[str]]:
    """Independence test: union overlapping vectors; keep the max-weight representative.
    Returns (kept, notes)."""
    parent = {v["id"]: v["id"] for v in vectors}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    byid = {v["id"]: v for v in vectors}
    # MUTUAL overlap only. Union-find is transitive; "shares an install chain"
    # is not. On 2026-09-17 a chain of individually defensible pairs
    # (v1-v3-v4-v9) merged BIS export controls, a head-of-state visit,
    # rare-earth retaliation and a competitor's market position into ONE vector,
    # then computed the resultant from it alone: p=1.00, tension 0.00.
    #
    # Requiring both directions does not make the merge non-transitive, but it
    # removes the one-sided links that formed most of that chain, and the
    # tripwire above catches what still gets through. Dropping transitivity
    # entirely needs a real similarity measure over source_form and is a larger
    # change than this file should carry today.
    for v in vectors:
        for o in v.get("overlaps", []):
            other = byid.get(o)
            if other is None:
                continue
            if v["id"] in (other.get("overlaps") or []):
                union(v["id"], o)
    groups: dict[str, list[dict]] = {}
    for v in vectors:
        groups.setdefault(find(v["id"]), []).append(v)
    kept, notes = [], []
    for root, grp in groups.items():
        if len(grp) == 1:
            kept.append(grp[0])
        else:
            best = max(grp, key=lambda v: SEVERITY.get(v.get("severity"), 1)
                       * float(v.get("credibility", 0.5)))
            kept.append(best)
            notes.append(f"merged {[v['id'] for v in grp]} -> {best['id']} "
                         f"(shared source structure; counted once)")
    return kept, notes


def validate_vectors(d: dict, today: str) -> dict:
    """Enforce v2's contract on the extracted table, in code.

    Three things the prompt asks for and nothing used to check. A prompt is a
    request; this is the part that makes it a rule.

      1. A vector with no `consequence` is dropped. Under P6 it is a fact about
         the world, not a stake on the target, and weighting it as pressure is
         the 72-84% error this version exists to fix.
      2. `credibility` is DERIVED from `demonstrated`. Whatever the model
         offered is preserved as `credibility_llm` so the two can be compared
         once claims resolve.
      3. `pushes_toward` must name one of the declared outcomes. A direction
         that matches no outcome silently contributed nothing to any bucket
         while still inflating the total-pressure band.

    Everything dropped is recorded in `d["rejected"]`, never discarded quietly:
    a short table of real stakes and a short table because the filter ate
    everything are different situations and must look different.
    """
    outs = [o for o in d.get("outcomes", []) if o]
    kept, rejected = [], []
    for v in d.get("vectors", []):
        cons = str(v.get("consequence") or "").strip()
        if not cons or cons.lower() in ("none", "n/a", "unclear", "unknown"):
            rejected.append({"id": v.get("id"), "source_form": v.get("source_form", "")[:90],
                             "why": "no consequence named — a fact, not an installed stake"})
            continue
        if outs and v.get("pushes_toward") not in outs:
            rejected.append({"id": v.get("id"), "source_form": v.get("source_form", "")[:90],
                             "why": "pushes_toward %r is not one of the declared outcomes"
                                    % str(v.get("pushes_toward"))[:40]})
            continue
        cred, why = credibility_from_demonstration(v.get("demonstrated"), today)
        if v.get("credibility") is not None:
            v["credibility_llm"] = v.get("credibility")
        v["credibility"] = cred
        v["credibility_basis"] = why
        kept.append(v)
    d["vectors"] = kept
    d["rejected"] = rejected
    return d


def tripwires(trace: dict, n_vectors: int) -> list:
    """Refuse-to-file conditions. Each one was an actual silent failure.

    A resultant-vector method that emits a certainty has not become confident;
    it has lost its vectors. Beijing, 2026-09-17: 14 vectors merged to 1 by a
    transitive dedup, p=1.00, tension 0.00, and a clean-looking chart. Nothing
    said anything was wrong, and the claim went to the ledger.
    """
    out = []
    for h in ("short", "long"):
        dist = (trace.get("horizons", {}).get(h) or {}).get("distribution", {})
        if dist and max(dist.values()) >= 0.95:
            out.append("%s horizon emits p>=0.95 — a resultant over several vectors "
                       "should not produce a certainty" % h)
    for note in trace.get("dedup_notes", []):
        m = re.search(r"merged \[([^\]]*)\]", note)
        if m and n_vectors:
            merged = len([x for x in m.group(1).split(",") if x.strip()])
            if merged > max(2, n_vectors // 2):
                out.append("dedup merged %d of %d vectors into one component — the "
                           "independence test is collapsing, not deduplicating"
                           % (merged, n_vectors))
    return out


def compute(d: dict) -> dict:
    vectors = d.get("vectors", [])
    kept, dedup_notes = dedup(vectors)
    outcomes = [o for o in d.get("outcomes", []) if o]
    if "delay/no-change" not in outcomes:
        outcomes.append("delay/no-change")
    trace = {"dedup_notes": dedup_notes, "horizons": {}}
    total_raw = sum(SEVERITY.get(v.get("severity"), 1) * float(v.get("credibility", 0.5))
                    for v in kept)
    band = next(b for cap, b in TOTAL_BANDS if total_raw < cap)
    for horizon in ("short", "long"):
        scores = {o: 0.0 for o in outcomes}
        steps = []
        for v in kept:
            w = (SEVERITY.get(v.get("severity"), 1)
                 * float(v.get("credibility", 0.5))
                 * TS_FACTOR[horizon].get(v.get("timescale"), 0.6))
            o = v.get("pushes_toward", "")
            tgt = o if o in scores else ("delay/no-change" if "delay" in o.lower() else o)
            if tgt not in scores:
                scores[tgt] = 0.0
                outcomes.append(tgt)
            scores[tgt] += w
            steps.append(f"{v['id']} {v['source_form'][:30]} -> '{tgt}': "
                         f"{SEVERITY.get(v.get('severity'),1):.0f}sev x "
                         f"{float(v.get('credibility',0.5)):.2f}cred x "
                         f"{TS_FACTOR[horizon].get(v.get('timescale'),0.6):.1f}ts = {w:.2f}")
        active = {o: s for o, s in scores.items() if o != "delay/no-change"}
        tot_active = sum(active.values()) or 1e-9
        top_o, top_s = max(active.items(), key=lambda kv: kv[1]) if active else ("?", 0)
        tension = 1.0 - top_s / tot_active
        # dilemma -> delay: unresolved tension mass flows to delay unless a deadline forces
        delay_bonus = tension * tot_active * (0.3 if d.get("forcing_deadline") else 1.0) * 0.5
        scores["delay/no-change"] += delay_bonus
        steps.append(f"tension={tension:.2f}; delay absorbs {delay_bonus:.2f} "
                     f"({'deadline forces -> x0.3' if d.get('forcing_deadline') else 'no forcing deadline'})")
        total = sum(scores.values()) or 1e-9
        dist = {o: round(s / total, 3) for o, s in sorted(scores.items(), key=lambda kv: -kv[1])}
        # convergence: independent domains aligned per outcome
        conv = {}
        for o in active:
            doms = {v.get("domain") for v in kept if v.get("pushes_toward") == o}
            conv[o] = len(doms)
        trace["horizons"][horizon] = {
            "steps": steps, "scores": {k: round(v, 3) for k, v in scores.items()},
            "tension_index": round(tension, 3), "distribution": dist,
            "convergence_domains": conv,
            "converged": [o for o, n in conv.items() if n >= 3]}
    trace["total_pressure"] = round(total_raw, 2)
    trace["pressure_band"] = band
    trace["structural_law_note"] = (
        f"total pressure {band} ({total_raw:.1f}): P(some transition) "
        + ("high regardless of destination confidence"
           if band in ("high", "saturated") else "moderate/low")
        + f"; resolving surprises likely from: {', '.join(d.get('unmonitored_dimensions', []))}")
    return trace


def render_md(target, question, d, trace, out_md: Path) -> None:
    L = [f"# Convergence trace — {target}", f"**Question:** {question}",
         f"Generated {datetime.date.today().isoformat()} · "
         f"total pressure **{trace['pressure_band']}** ({trace['total_pressure']}) · "
         f"novel regime: {d.get('novel_regime')}", "",
         "## Pressure vectors (post-dedup input to the arithmetic)"]
    kept_ids = {s.split()[0] for h in trace["horizons"].values() for s in h["steps"]
                if s and s[0] == "v"}
    for v in d["vectors"]:
        mark = "" if v["id"] in kept_ids else " *(merged away)*"
        L.append(f"- **{v['id']}** [{v['domain']}] {v['source_form']} → *{v['pushes_toward']}* · "
                 f"{v['severity']}/{v.get('credibility')}cred/{v.get('timescale')}{mark} — "
                 f"{v.get('evidence','')}")
    for n in trace["dedup_notes"]:
        L.append(f"- ⚖ {n}")
    for h in ("short", "long"):
        t = trace["horizons"][h]
        L += ["", f"## {h.capitalize()} horizon", "```"]
        L += t["steps"]
        L += ["```", f"tension index: {t['tension_index']}",
              "**Distribution:** " + " · ".join(f"{o} **{p:.0%}**"
                                                for o, p in t["distribution"].items()),
              ("**CONVERGED** (≥3 independent domains): " + ", ".join(t["converged"]))
              if t["converged"] else "_no ≥3-domain convergence — directional confidence capped_"]
    L += ["", f"## Structural-law note", trace["structural_law_note"],
          "", f"Unmonitored dimensions (butterfly watch): "
          + "; ".join(d.get("unmonitored_dimensions", []))]
    out_md.write_text("\n".join(L), encoding="utf-8")


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def run(target: str, question: str, model: str, horizon_days: int) -> None:
    today = datetime.date.today().isoformat()
    # feed the monitor's logged dynamics for this office, if any
    dyn = []
    lf = RDIR / "dynamics" / "log.jsonl"
    if lf.exists():
        for line in lf.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if target.lower() in r.get("office", "").lower():
                dyn.append(f"[{r.get('monitored')}] {r.get('kind')}: {r.get('what')} "
                           f"({r.get('installer_or_actor','')})")
    p = (VECTOR_PROMPT.replace("{today}", today).replace("{target}", target)
         .replace("{question}", question)
         .replace("{dynamics}", "\n".join(dyn[-15:]) or "(none logged)"))
    print(f"[converge] {target} :: {question}")
    d = None
    for _ in range(3):
        r = chat(model + ":online", [{"role": "user", "content": p}],
                 temperature=0.2, max_tokens=4000)
        d = parse_json(r.text) if not r.error else None
        if d and d.get("vectors"):
            break
        d = None
    if not d:
        raise SystemExit(f"vector extraction failed: {r.error or 'unparseable'}")

    raw_n = len(d.get("vectors", []))
    d = validate_vectors(d, today)
    if not d["vectors"]:
        raise SystemExit(
            "every extracted vector was rejected (%d of %d had no nameable "
            "consequence or an unknown direction). That is a finding about the "
            "question, not a table: either the target is under no installed "
            "pressure on it, or the question is not a decision. Nothing filed."
            % (len(d["rejected"]), raw_n))
    if d["rejected"]:
        print("  filtered: %d of %d candidate vectors were facts, not pressures"
              % (len(d["rejected"]), raw_n))
        for rj in d["rejected"][:6]:
            print("    - %s %s: %s" % (rj.get("id"), rj.get("source_form", "")[:52], rj["why"][:70]))

    trace = compute(d)
    trips = tripwires(trace, len(d["vectors"]))
    trace["tripwires"] = trips
    cdir = RDIR / "converge"
    cdir.mkdir(exist_ok=True)
    slug = slugify(question)
    full = {"target": target, "question": question, "generated": today,
            "extracted_by": model, "prompt_version": "v2-consequence",
            "input": d, "trace": trace}
    (cdir / f"{slug}.json").write_text(json.dumps(full, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    render_md(target, question, d, trace, cdir / f"{slug}.md")

    sh = trace["horizons"]["short"]
    top, p_top = next(iter(sh["distribution"].items()))
    print(f"  vectors: {len(d['vectors'])} ({len(trace['dedup_notes'])} merges) · "
          f"pressure {trace['pressure_band']} ({trace['total_pressure']}) · "
          f"tension {sh['tension_index']}")
    for o, pp in sh["distribution"].items():
        c = sh["convergence_domains"].get(o, 0)
        print(f"    {pp:.0%}  {o}" + (f"  [CONVERGED: {c} domains]" if o in sh["converged"] else
                                      (f"  ({c} domains)" if c else "")))
    print(f"  -> converge/{slug}.json + .md (full reasoning trace)")

    # A tripped wire means the arithmetic is not trustworthy for THIS run, so
    # the trace is kept (it is the evidence) and the CLAIM is refused. Filing it
    # anyway is what put a p=1.00 forecast in the ledger on 2026-09-17.
    if trips:
        print("\n  TRIPWIRE — no ledger claim filed:")
        for t in trips:
            print("    !! %s" % t)
        print("  the trace is kept at converge/%s.json as evidence about the run." % slug)
        return

    # ledger claim with the trace as its mechanism
    resolve_by = (d.get("deadline") or
                  (datetime.date.today() + datetime.timedelta(days=horizon_days)).isoformat())
    lpath = RDIR / "predict" / "ledger.json"
    led = json.load(lpath.open(encoding="utf-8"))
    led["rounds"] = led.get("rounds", 0) + 1
    led["predictions"].append({
        "entity": f"converge:{slug}"[:80], "name": f"{target} — {question}"[:90],
        "made_on": today, "resolve_by": resolve_by, "round": led["rounds"],
        "status": "open",
        "claim": f"Outcome of '{question}': {top}"[:250],
        "resolution_criteria": f"The observable decision/outcome by {resolve_by}; "
                               f"'{top}' as defined in the trace's outcome set",
        "confidence": p_top,
        "mechanism": f"pressure-convergence resultant: tension {sh['tension_index']}, "
                     f"pressure {trace['pressure_band']}, converged={sh['converged']}; "
                     f"full reasoning trace at converge/{slug}.json",
        "trace": f"converge/{slug}.json",
        # Which extractor made this call. The v1 prompt let facts through as
        # pressures; when these resolve, "which version predicted better" must
        # be answerable from the ledger alone.
        "prompt_version": "v2-consequence"})
    json.dump(led, lpath.open("w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"  -> ledger claim appended (p={p_top} '{top}', by {resolve_by})")


def main() -> None:
    ap = argparse.ArgumentParser(description="Resultant-vector pressure convergence with reasoning trace.")
    ap.add_argument("--target", required=True, help="office or arena")
    ap.add_argument("--question", required=True, help="the decision/outcome space")
    ap.add_argument("--model", default="anthropic/claude-sonnet-4")
    ap.add_argument("--horizon", type=int, default=45)
    a = ap.parse_args()
    from suites.grade_claims import _load_env
    _load_env()
    if not os.environ.get("OPENROUTER_API_KEY"):
        if os.environ.get("LLM_BACKEND") != "claude-code":
            raise SystemExit("OPENROUTER_API_KEY not set (or set LLM_BACKEND=claude-code)")
    run(a.target, a.question, a.model, a.horizon)


if __name__ == "__main__":
    main()
