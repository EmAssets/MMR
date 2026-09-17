"""Arena — models claim in public, defend under challenge, and are judged blind.

The fleet's existing brainstorm asks each model to read an event through its own
mechanism, then synthesizes. It is ONE round and the synthesis is written by the
same process that wrote the lenses. Nothing is adversarial and nothing is scored.

This is different in four ways, and each is the point:

  PUBLIC        Every model's claim is written to minutes BEFORE it sees anyone
                else's. A model cannot quietly agree with the room.
  DEFENDED      Round 2 shows each model the others' minutes. It must either
                defend its claim against the strongest objection to it, or
                revise -- and say which, so a change of mind is visible as a
                change of mind rather than being overwritten.
  JUDGED BLIND  An independent judge sees ONLY the minutes. Never a MODEL.md,
                never the case's real outcome. It rules on the argument as
                argued. The ruling -- not the panel's consensus -- becomes the
                next cycle's premise, so the panel cannot simply agree its way
                to a conclusion.
  SCORED        On a BACKTEST case the real outcome exists and was sealed before
                the run. After the judge rules, the outcome is revealed and the
                ruling is scored against it. This is the only reality signal the
                fleet has before 2026-10-01.

SIGNED MINUTES. Every entry carries the model's slug, its MODEL.md version line,
and the git commit of its repo at the time it spoke. A claim is attributable to
a specific state of a specific model, so "the model changed its mind" and "the
model was edited" cannot be confused.

THE CONVERGENCE WARNING, which is the finding this instrument most likely
produces. This fleet is one LLM reading one corpus of 37 sources. Its models
will agree with each other quickly, and that agreement is evidence about the
corpus, not about the world. Every cycle therefore logs a DISAGREEMENT score,
and a run that converges by cycle 2 is reported as a shared-source echo rather
than a consensus. See `--report`.

  python -m suites.arena --list-cases
  python -m suites.arena --case openai-nov-2023 --panel auto --cycles 1
  python -m suites.arena --case openai-nov-2023 --cycles 3 --dry-run
  python -m suites.arena --report <run-id>
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
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
    """Load .env before any chat() call.

    Without this the backend setting in .env is invisible, chat() falls through
    to OpenRouter, and returns empty text with error 'OPENROUTER_API_KEY not
    set' -- which looks exactly like a model that answered nothing. The engine
    hit this before (see suites/grade_claims.py) and the same idiom is used here.
    """
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _models_dir(root: Path) -> Path:
    try:
        cfg = json.load((root / "fleet.json").open(encoding="utf-8"))
        if cfg.get("models_dir"):
            return (root / cfg["models_dir"]).resolve()
    except Exception:
        pass
    return root.parent


TOOLS = _models_dir(ROOT)
ADIR = ROOT / "arena"
TODAY = datetime.date.today().isoformat()

# The judge must not be a panelist, and must not be handed a mechanism to
# reason from. It rules on the minutes alone.
JUDGE_SLUG = "independent-judge"


# ---------------------------------------------------------------- cases

def backtest_cases() -> dict:
    """Backtest files are the only cases with a sealed, pre-written outcome.

    Each file has a prediction section, a `## Real outcome`, and usually a
    scored `## Assessment`. The outcome and assessment are SPLIT OFF here and
    never travel with the brief -- that split is what makes the run blind.
    """
    out = {}
    d = TOOLS / "attention-substrate" / "predict"
    for f in sorted(d.glob("backtest_*.md")):
        t = f.read_text(encoding="utf-8", errors="replace")
        slug = f.stem.replace("backtest_", "")
        head, outcome = t, ""
        if "## Real outcome" in t:
            head, rest = t.split("## Real outcome", 1)
            outcome = "## Real outcome" + rest
        title = head.splitlines()[0].lstrip("# ").strip()

        # WITHHOLD THE ORIGIN MODEL'S PREDICTION TOO.
        #
        # This was a real leak, found 2026-09-16: splitting only on "## Real
        # outcome" left `## Prediction` in the brief, and that section ends with
        # a numbered OUTCOME stating the origin's conclusion verbatim ("Sam
        # Altman is formally rehired..."). The panel was reading an answer and
        # paraphrasing it, so the first run's 90/100 accuracy partly measured
        # copying rather than reasoning.
        #
        # The brief is now the SETUP ONLY. Everything from the origin's
        # prediction onward travels with the sealed material, and a case whose
        # setup cannot be separated is marked so rather than silently shipped.
        origin_prediction = ""
        m_pred = re.search(r"^##+\s*Prediction\b", head, re.M)
        if m_pred:
            origin_prediction = head[m_pred.start():]
            head = head[:m_pred.start()]
        setup = head.strip()
        m = re.search(r"\(T=([^)]+)\)", title)
        prior = None
        jm = re.search(r"```json(.*?)```", outcome, re.S)
        if jm:
            try:
                prior = json.loads(jm.group(1))
            except ValueError:
                prior = None
        # A backtest file that is only a title plus a prediction leaves nothing
        # to brief with. Rather than hand the panel an empty case, synthesise
        # the minimum framing from the title and flag that the setup was thin.
        thin = len(setup) < 200
        if thin:
            setup = ("%s\n\nYou are reasoning as of %s. No further setup is "
                     "recorded in the case file; reason from what a well-informed "
                     "observer would have known at that date."
                     % (title, (m.group(1).strip() if m else "the case date")))

        out[slug] = {
            "slug": slug,
            "title": title,
            "as_of": (m.group(1).strip() if m else ""),
            "brief": setup,
            "sealed_outcome": (origin_prediction + "\n\n" + outcome).strip(),
            "origin_prediction_withheld": bool(origin_prediction),
            "thin_setup": thin,
            "origin_score": prior,
            "source": str(f),
        }
    return out


def candidate_cases() -> dict:
    """Survivors of pattern-evaluator, as arena cases.

    THE PIPELINE, and where the arena sits in it:

        pattern-candidates  proposes into quarantine
        pattern-evaluator   kills what is analogy rather than mechanism
        THE ARENA           argues each survivor's TRANSFER PREDICTION
        the operator        promotes, or does not

    The arena does NOT promote. `pattern-evaluator/MODEL.md` is explicit --
    "nothing leaves quarantine without passing here, and promotion is the
    operator's call even then" -- and its consequence 3 is falsified by any
    candidate leaving quarantine without a recorded transfer prediction. So the
    arena adds a gate; it never opens one. Rulings are written back INTO
    quarantine, and a human still decides.

    Only candidates with an evaluator verdict are eligible. Raw quarantine that
    has never faced the evaluator has not "passed here" and is not a case.
    """
    out = {}
    f = TOOLS / "pattern-evaluator" / "verdicts.json"
    if not f.exists():
        return out
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return out
    src = d.get("source", "")
    for i, v in enumerate(d.get("verdicts", []), 1):
        if str(v.get("verdict", "")).lower() == "killed":
            continue
        claim = str(v.get("claim", "")).strip()
        if not claim:
            continue
        slug = "cand-%02d" % i
        brief = (
            "A cross-layer pattern candidate that SURVIVED the pattern-evaluator.\n\n"
            "CLAIM:\n%s\n\n"
            "WHY THE EVALUATOR DID NOT KILL IT:\n%s\n\n"
            "THE BORING EXPLANATION IT HAD TO BEAT:\n%s\n\n"
            "TRANSFER PREDICTION ON RECORD:\n%s\n\n"
            "The question is NOT whether the claim is true. It is whether the pattern "
            "names a MECHANISM that carries between two levels of organisation, or a "
            "RESEMBLANCE that two levels share because they borrowed the same "
            "mathematics, the same describing language, or because a human found a "
            "shape in noise."
            % (claim, v.get("why", "(not recorded)"),
               v.get("boring", "(not recorded)"), v.get("transfer", "(none recorded)"))
        )
        out[slug] = {
            "slug": slug, "mode": "candidate",
            "title": "Candidate %d from %s" % (i, src or "quarantine"),
            "as_of": TODAY, "brief": brief,
            "sealed_outcome": "",          # a candidate has no outcome to seal
            "origin_score": None,
            "evaluator_transfer": v.get("transfer", ""),
            "source": str(f),
        }
    return out


def all_cases() -> dict:
    c = backtest_cases()
    for k, v in c.items():
        v.setdefault("mode", "backtest")
    c.update(candidate_cases())
    return c


# ---------------------------------------------------------------- panel

def mechanism(slug: str) -> dict | None:
    """One line describing what this model is FOR, from its own document.

    attribute_outcomes.MENU is empty in this instance, so the description is
    derived from the model's own headers. The parent theory models state no
    kind or domain, so their title carries the description instead -- recorded
    as `derived: title` rather than silently emitting an empty string.
    """
    p = TOOLS / slug / "MODEL.md"
    if not p.exists():
        return None
    t = p.read_text(encoding="utf-8", errors="replace")
    lines = t.splitlines()
    title = lines[0].lstrip("# ").strip() if lines else slug
    k = re.search(r"\*\*The kind:\*\*\s*(.+)", t)
    dm = re.search(r"\*\*The domain:\*\*\s*(.+)", t)
    kind = (k.group(1).strip() if k else "").split("(")[0].strip()
    dom = dm.group(1).strip() if dm else ""

    # A model with no "**The domain:**" header is not a model without a
    # mechanism -- the parent theory models (attention-substrate, pressure-model)
    # state theirs as prose under a thesis heading. Before this fallback they
    # were briefed with only their title, correctly answered "mechanism
    # unstated", and abstained: in the first cand-05 run two of three panelists
    # contributed nothing and the judge ruled on a single voice. That was a bug
    # in the briefing, not reticence in the models.
    thesis = ""
    if not dom:
        mm = re.search(r"^##+\s*(?:The core thesis|The hypothesis[^\n]*|Premises)\s*$",
                       t, re.M | re.I)
        if mm:
            para = t[mm.end():mm.end() + 700].strip().split("\n\n")[0]
            thesis = " ".join(para.split())[:420]

    return {
        "slug": slug,
        "title": title,
        "kind": kind or "unstated",
        "domain": dom,
        "derived": "headers" if dom else ("thesis" if thesis else "title"),
        "one_line": dom or thesis or title,
        "version": _version_line(t),
        "commit": _commit(slug),
    }


def _version_line(t: str) -> str:
    m = re.search(r"\(v([0-9][0-9.]*)\)", t[:400]) or re.search(r"[-—]\s*v([0-9][0-9.]*)", t[:400])
    return ("v" + m.group(1)) if m else ""


def _commit(slug: str) -> str:
    """Git commit of the model's repo, so a minute names a model STATE."""
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           cwd=str(TOOLS / slug), capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


# Panels are chosen per case rather than "all 43": a model with no grip on the
# case contributes noise, and every extra panelist is an extra LLM call.
AUTO_PANELS = {
    "openai-nov-2023": ["attention-substrate", "pressure-model", "ai-pressure",
                        "lab-moves", "ai-lab-revealed-priorities", "ai-option-space"],
    "twitter-musk": ["attention-substrate", "pressure-model", "overton-tracker",
                     "ai-public-backlash"],
    "brexit-2016": ["attention-substrate", "pressure-model", "overton-tracker"],
    "netflix-cable": ["attention-substrate", "ai-adoption-phases"],
    "craigslist-classifieds": ["attention-substrate", "ai-bubble-thesis"],
    "substack-media": ["attention-substrate", "ai-public-backlash"],
}


def resolve_panel(case: str, spec: str) -> list:
    if spec and spec != "auto":
        want = [s.strip() for s in spec.split(",") if s.strip()]
    elif case.startswith("cand-"):
        # A candidate case asks "mechanism or resemblance?", which is a question
        # about inference, not about any model's subject matter. The panel is
        # therefore the models that argue about structure. pattern-evaluator is
        # deliberately EXCLUDED: it already ruled, and re-seating it as a
        # panelist would let it confirm its own verdict.
        want = ["attention-substrate", "pressure-model", "pattern-candidates"]
    else:
        want = AUTO_PANELS.get(case, ["attention-substrate", "pressure-model"])
    panel, missing = [], []
    for s in want:
        m = mechanism(s)
        (panel.append(m) if m else missing.append(s))
    if missing:
        print("  [warn] not found, dropped from panel: %s" % ", ".join(missing))
    return panel


# ---------------------------------------------------------------- prompts

CLAIM = """You are the model "{title}" ({slug}), speaking in a public arena.

YOUR MECHANISM — the only thing you may reason from:
  kind: {kind}
  {one_line}

THE CASE (as of {as_of}):
{brief}

Answer ONLY through your own mechanism. If your mechanism has no grip on this
case, say so — "no grip" is a respectable answer and is better than a guess
dressed as an inference.

Return STRICT JSON, no prose outside it:
{{
 "grip": "strong" | "partial" | "none",
 "claim": "<your single falsifiable claim about what happens, one sentence>",
 "because": "<the mechanism step that produces it, 2-3 sentences>",
 "falsifier": "<the specific observation that would prove you wrong>",
 "confidence": <0.0-1.0>,
 "blind_spot": "<what your mechanism structurally CANNOT see about this case>"
}}"""

DEFEND = """You are the model "{title}" ({slug}) in round 2 of a public arena.

In round 1 you claimed:
{mine}

The other models claimed:
{others}

Now do ONE of two things, and name which:
 - DEFEND: your claim stands. State the strongest objection raised against it
   and why your mechanism survives it.
 - REVISE: you were wrong or incomplete. State what changed your mind — quote
   the specific other minute — and give your new claim.

Changing your mind is not a loss. Agreeing because everyone else agreed IS a
loss: if you revise, the reason must be an ARGUMENT, never a count of who said
what. If no one raised a real objection, DEFEND and say the objections were weak.

Return STRICT JSON:
{{
 "move": "DEFEND" | "REVISE",
 "claim": "<your claim now — unchanged if DEFEND>",
 "strongest_objection": "<the best argument against you, stated fairly>",
 "answer": "<why you survive it, or what it changed>",
 "moved_by": "<slug of the model that moved you, or null>",
 "confidence": <0.0-1.0>
}}"""

JUDGE = """You are an INDEPENDENT JUDGE. You have not seen any model's
documentation and you do not know which model is which beyond its name. You know
nothing about this case except what the minutes below contain.

THE QUESTION: {question}

THE MINUTES:
{minutes}

Rule on the ARGUMENT AS ARGUED. You are not scoring who sounds confident, and
you must not reward a claim for being popular — if four models agree because
they share an assumption, say so and treat it as ONE argument, not four.

Return STRICT JSON:
{{
 "ruling": "<your single best answer to the question, one sentence>",
 "because": "<what in the minutes decided it, 2-4 sentences>",
 "strongest_minute": "<slug whose argument was best, and why>",
 "weakest_minute": "<slug whose argument was weakest, and why>",
 "shared_assumption": "<an assumption multiple models relied on without arguing for it, or null>",
 "unresolved": "<what the minutes could not settle>",
 "confidence": <0.0-1.0>
}}"""


JUDGE_CANDIDATE = """You are an INDEPENDENT JUDGE. You have not seen any model's
documentation. You know nothing about this candidate except what the minutes
below contain.

THE QUESTION: {question}

THE MINUTES:
{minutes}

You are ruling on ONE thing: does this pattern name a MECHANISM that carries
between two levels of organisation, or is it a RESEMBLANCE?

A resemblance is not worthless, it is just not a law. Two systems look alike when
they borrowed the same mathematics, when the describing language is shared, or
when a human found a shape in noise. None of those transfers.

If four models agree because they share an assumption, that is ONE argument, not
four. Say so.

If you rule MECHANISM, you must supply the transfer prediction it produces: a
dated, checkable claim at the OTHER level. A mechanism that cannot produce one is
a resemblance with better vocabulary, and you should rule accordingly.

Return STRICT JSON:
{{
 "ruling": "MECHANISM" | "RESEMBLANCE" | "UNDECIDED",
 "because": "<what in the minutes decided it, 2-4 sentences>",
 "transfer_prediction": "<dated checkable claim at the other level, or null if not MECHANISM>",
 "resolve_by": "<YYYY-MM-DD for that prediction, or null>",
 "strongest_minute": "<slug and why>",
 "weakest_minute": "<slug and why>",
 "shared_assumption": "<assumption relied on without argument, or null>",
 "evaluator_should_have_killed": true|false,
 "unresolved": "<what the minutes could not settle>",
 "confidence": <0.0-1.0>
}}"""


# ---------------------------------------------------------------- llm

def _call(model_hint: str, prompt: str, dry: bool) -> dict:
    if dry:
        return {"_dry": True, "grip": "partial", "claim": "[dry-run] no LLM call made",
                "because": "", "falsifier": "", "confidence": 0.0, "blind_spot": "",
                "move": "DEFEND", "ruling": "[dry-run]", "strongest_minute": "",
                "weakest_minute": "", "shared_assumption": None, "unresolved": "",
                "answer": "", "moved_by": None, "strongest_objection": ""}
    from harness.openrouter import chat
    from harness.actors import parse_json
    r = chat(model_hint, [{"role": "user", "content": prompt}],
             temperature=0.3, max_tokens=1400)
    if getattr(r, "error", None):
        # A backend error is NOT an empty answer. Writing {} here would record
        # a model as having said nothing, which is a different fact entirely.
        return {"_error": str(r.error)[:300]}
    txt = getattr(r, "text", None) or getattr(r, "content", None) or ""
    if not str(txt).strip():
        return {"_error": "backend returned empty text"}
    try:
        return parse_json(txt)
    except Exception:
        m = re.search(r"\{.*\}", txt, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                pass
        return {"_unparsed": txt[:800]}


def _minute(kind: str, who: dict, cycle: int, rnd: int, body: dict) -> dict:
    """A signed minute. The signature is what makes the record auditable."""
    return {
        "cycle": cycle, "round": rnd, "type": kind,
        "signed_by": who.get("slug"),
        "model_title": who.get("title", ""),
        "model_version": who.get("version", ""),
        "model_commit": who.get("commit", ""),
        "at": datetime.datetime.now().isoformat(timespec="seconds"),
        "body": body,
    }


# ---------------------------------------------------------------- disagreement

def disagreement(minutes: list) -> dict:
    """How much did the panel actually differ this cycle?

    Deliberately crude and stated as such: distinct claim-stems, plus how many
    models moved, plus the confidence spread. A precise semantic measure would
    imply the arena can tell agreement from paraphrase, which it cannot. The
    number exists to catch the case this fleet is most prone to -- everyone
    agreeing because they read the same 37 sources.
    """
    r2 = [m for m in minutes if m["round"] == 2]
    claims = [str(m["body"].get("claim", ""))[:90].lower().strip() for m in r2]
    claims = [c for c in claims if c]
    distinct = len(set(claims))
    moved = sum(1 for m in r2 if str(m["body"].get("move", "")).upper() == "REVISE")
    confs = [m["body"].get("confidence") for m in r2 if isinstance(m["body"].get("confidence"), (int, float))]
    spread = (max(confs) - min(confs)) if len(confs) > 1 else 0.0
    n = max(1, len(claims))
    return {
        "panelists": len(r2),
        "distinct_claims": distinct,
        "distinct_ratio": round(distinct / n, 3),
        "revised": moved,
        "confidence_spread": round(spread, 3),
        "note": ("distinct_ratio near 1.0 = the panel genuinely disagreed. Near 1/n = it "
                 "converged. Convergence in an early cycle is NOT agreement about the world: "
                 "this fleet is one LLM over one corpus, so it is the expected result and is "
                 "evidence about the corpus."),
    }


# ---------------------------------------------------------------- run

def run(case_slug: str, panel_spec: str, cycles: int, dry: bool, model_hint: str,
        run_tag: str = "") -> None:
    cases = all_cases()
    if case_slug not in cases:
        raise SystemExit("unknown case %r — try --list-cases" % case_slug)
    case = cases[case_slug]
    mode = case.get("mode", "backtest")
    panel = resolve_panel(case_slug, panel_spec)
    if len(panel) < 2:
        raise SystemExit("need >=2 panelists, got %d" % len(panel))

    # run_tag namespaces test runs so a test can never overwrite a real run's
    # artifacts -- which it did once, silently, while a live run was in flight.
    run_id = "arena-%s-%s%s" % (case_slug, TODAY, ("-" + run_tag) if run_tag else "")
    outdir = ADIR / run_id
    outdir.mkdir(parents=True, exist_ok=True)

    print("[arena] case=%s  panel=%d  cycles=%d%s"
          % (case_slug, len(panel), cycles, "  (DRY RUN)" if dry else ""))
    print("   %s" % case["title"])
    for p in panel:
        print("     %-28s %-14s %s %s" % (p["slug"], p["kind"], p["version"], p["commit"]))

    if mode == "candidate":
        question = ("Does this cross-layer pattern name a MECHANISM that carries between "
                    "levels, or a RESEMBLANCE? If a mechanism, what dated prediction does "
                    "it produce at the other level?")
    else:
        question = "As of %s: what happens next, and why?" % (case["as_of"] or "the case date")
    premise = None
    all_cycles = []

    for cyc in range(1, cycles + 1):
        print("\n  -- cycle %d --" % cyc)
        minutes = []
        brief = case["brief"]
        if premise:
            brief += ("\n\nPREMISE CARRIED FROM THE PREVIOUS CYCLE (an independent judge's "
                      "ruling on the prior round's minutes — not a fact, and you may argue "
                      "against it):\n%s" % premise)

        # round 1 — claim, written before anyone sees anyone else
        for p in panel:
            body = _call(model_hint, CLAIM.format(
                title=p["title"], slug=p["slug"], kind=p["kind"],
                one_line=p["one_line"], as_of=case["as_of"], brief=brief), dry)
            minutes.append(_minute("claim", p, cyc, 1, body))
            print("     r1 %-26s grip=%-8s conf=%s" % (p["slug"], body.get("grip"), body.get("confidence")))

        # round 2 — defend or revise, now seeing the others
        board = "\n".join(
            "- [%s] %s" % (m["signed_by"], str(m["body"].get("claim", ""))[:220])
            for m in minutes if m["round"] == 1)
        for p in panel:
            mine = next((m for m in minutes if m["signed_by"] == p["slug"] and m["round"] == 1), None)
            others = "\n".join(l for l in board.splitlines() if not l.startswith("- [%s]" % p["slug"]))
            body = _call(model_hint, DEFEND.format(
                title=p["title"], slug=p["slug"],
                mine=json.dumps(mine["body"], ensure_ascii=False)[:700] if mine else "",
                others=others or "(no other minutes)"), dry)
            minutes.append(_minute("defence", p, cyc, 2, body))
            print("     r2 %-26s %-8s moved_by=%s" % (p["slug"], body.get("move"), body.get("moved_by")))

        # the judge — minutes only. No MODEL.md, no sealed outcome.
        jtext = "\n".join(
            "[%s | %s | commit %s | round %d] %s"
            % (m["signed_by"], m["model_version"] or "unversioned", m["model_commit"] or "uncommitted",
               m["round"], json.dumps(m["body"], ensure_ascii=False)[:600])
            for m in minutes)
        jtmpl = JUDGE_CANDIDATE if mode == "candidate" else JUDGE
        jbody = _call(model_hint, jtmpl.format(question=question, minutes=jtext), dry)
        judge_who = {"slug": JUDGE_SLUG, "title": "Independent judge", "version": "", "commit": ""}
        ruling = _minute("ruling", judge_who, cyc, 3, jbody)
        minutes.append(ruling)
        print("     JUDGE  %s" % str(jbody.get("ruling", ""))[:88])
        if jbody.get("shared_assumption"):
            print("     judge flags shared assumption: %s" % str(jbody["shared_assumption"])[:80])

        dis = disagreement(minutes)
        print("     disagreement: %d/%d distinct (ratio %.2f) · %d revised · spread %.2f"
              % (dis["distinct_claims"], dis["panelists"], dis["distinct_ratio"],
                 dis["revised"], dis["confidence_spread"]))

        cdir = outdir / ("cycle-%d" % cyc)
        cdir.mkdir(exist_ok=True)
        with (cdir / "minutes.jsonl").open("w", encoding="utf-8") as fh:
            for m in minutes:
                fh.write(json.dumps(m, ensure_ascii=False) + "\n")
        (cdir / "ruling.json").write_text(json.dumps(jbody, ensure_ascii=False, indent=1), encoding="utf-8")
        all_cycles.append({"cycle": cyc, "ruling": jbody, "disagreement": dis,
                           "minutes": len(minutes)})

        # the judge's ruling — NOT the panel's consensus — carries forward
        premise = jbody.get("ruling")

    payload = {
        "spec": "arena-v1", "run_id": run_id, "built": TODAY, "case": case_slug,
        "case_title": case["title"], "as_of": case["as_of"], "question": question,
        "cycles": len(all_cycles), "dry_run": bool(dry),
        "panel": [{k: p[k] for k in ("slug", "title", "kind", "version", "commit", "derived")} for p in panel],
        "judge": {"slug": JUDGE_SLUG,
                  "blind_to": ["every MODEL.md", "the case's sealed outcome",
                               "which model is which beyond its name"]},
        "sealed_outcome_withheld": bool(case["sealed_outcome"]),
        "origin_score": case["origin_score"],
        "rounds": all_cycles,
        "note": ("Models claim in public before seeing each other, defend or revise under "
                 "challenge, and are judged by a model that sees only the minutes. The judge's "
                 "ruling becomes the next cycle's premise. Every minute is signed with the "
                 "model's slug, version and repo commit. DISAGREEMENT is logged per cycle "
                 "because this fleet is one LLM over one corpus and will converge for reasons "
                 "that have nothing to do with the world."),
    }
    payload["mode"] = mode
    (outdir / "arena.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n  -> %s" % (outdir / "arena.json"))

    if mode == "candidate":
        _record_candidate_ruling(case, payload)
    if not dry and mode == "backtest":
        print("  score it against the sealed outcome with: python -m suites.arena --score %s" % run_id)


def _record_candidate_ruling(case: dict, payload: dict) -> None:
    """Write the ruling back INTO quarantine. This never promotes anything.

    pattern-evaluator/MODEL.md: "nothing leaves quarantine without passing here,
    and promotion is the operator's call even then." The arena is a gate added
    before the operator, not a replacement for them. Its consequence 3 is
    falsified by any candidate leaving quarantine without a recorded transfer
    prediction, so the ruling's transfer_prediction is stored alongside the
    evaluator's own -- and a ruling of RESEMBLANCE is stored too, because "the
    arena could not make the case for this one" is exactly what the operator
    needs to see.
    """
    final = payload["rounds"][-1]["ruling"]
    f = TOOLS / "pattern-candidates" / "candidates" / "arena-rulings.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    try:
        doc = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        doc = {"spec": "arena-candidate-rulings-v1",
               "note": ("Arena rulings on pattern-evaluator survivors. STILL QUARANTINED: "
                        "a ruling here is an argument about a candidate, not a promotion. "
                        "Promotion remains the operator's call, and a MECHANISM ruling "
                        "without a transfer_prediction must not be promoted -- that is the "
                        "leak pattern-evaluator consequence 3 is written to catch."),
               "rulings": []}
    doc["rulings"] = [r for r in doc.get("rulings", []) if r.get("case") != case["slug"]]
    doc["rulings"].append({
        "case": case["slug"],
        "run_id": payload["run_id"],
        "ruled_on": TODAY,
        "ruling": final.get("ruling"),
        "because": final.get("because"),
        "transfer_prediction": final.get("transfer_prediction"),
        "resolve_by": final.get("resolve_by"),
        "evaluator_transfer": case.get("evaluator_transfer", ""),
        "evaluator_should_have_killed": final.get("evaluator_should_have_killed"),
        "shared_assumption": final.get("shared_assumption"),
        "panel": [x["slug"] for x in payload["panel"]],
        "promoted": False,
        "promotion_note": "NOT PROMOTED. The arena does not promote; the operator does.",
    })
    doc["updated"] = TODAY
    f.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print("  ruling recorded in quarantine -> %s" % f)
    print("     NOT PROMOTED — promotion is the operator's call")
    if final.get("evaluator_should_have_killed"):
        print("     JUDGE SAYS THE EVALUATOR SHOULD HAVE KILLED THIS — a gate leak to log "
              "against pattern-evaluator")


# ---------------------------------------------------------------- score

def score(run_id: str, dry: bool, model_hint: str) -> None:
    """Reveal the sealed outcome and score the FINAL ruling against it.

    This runs only after the judge has ruled. It is the one place the real
    outcome enters, and it never reaches a panelist.
    """
    f = ADIR / run_id / "arena.json"
    if not f.exists():
        raise SystemExit("no such run: %s" % run_id)
    payload = json.loads(f.read_text(encoding="utf-8"))
    case = backtest_cases()[payload["case"]]
    final = payload["rounds"][-1]["ruling"]
    prompt = (
        "A panel of models argued a case and an independent judge ruled. The real outcome is "
        "now revealed. Score the RULING against it.\n\nQUESTION: %s\n\nRULING: %s\n\nBECAUSE: %s"
        "\n\nTHE REAL OUTCOME:\n%s\n\nReturn STRICT JSON:\n"
        '{"outcome_accuracy": <0-100>, "reasoning_quality": <0-100>, '
        '"biggest_error": "<what it got most wrong>", '
        '"what_it_got_right": "<the best call>", '
        '"beat_origin": true|false, "why": "<one sentence>"}'
        % (payload["question"], final.get("ruling", ""), final.get("because", ""),
           case["sealed_outcome"][:3000]))
    body = _call(model_hint, prompt, dry)
    payload["score"] = body
    payload["origin_score"] = case["origin_score"]
    f.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    o = case["origin_score"] or {}
    print("[score] %s" % run_id)
    print("  arena ruling : accuracy=%s reasoning=%s" % (body.get("outcome_accuracy"), body.get("reasoning_quality")))
    print("  origin single: accuracy=%s reasoning=%s" % (o.get("outcome_accuracy"), o.get("reasoning_quality")))
    print("  biggest error: %s" % str(body.get("biggest_error"))[:100])
    print("\n  NOTE: the origin score was produced by a different grader at a different time. "
          "Treat any gap under ~10 points as noise, not as the arena beating a single model.")


def report(run_id: str) -> None:
    f = ADIR / run_id / "arena.json"
    if not f.exists():
        raise SystemExit("no such run: %s" % run_id)
    p = json.loads(f.read_text(encoding="utf-8"))
    print("[arena report] %s — %s" % (p["run_id"], p["case_title"]))
    print("  panel: %s" % ", ".join(x["slug"] for x in p["panel"]))
    print("\n  cycle  distinct  revised  spread   ruling")
    for r in p["rounds"]:
        d = r["disagreement"]
        print("   %-5d  %d/%-6d %-8d %-8.2f %s"
              % (r["cycle"], d["distinct_claims"], d["panelists"], d["revised"],
                 d["confidence_spread"], str(r["ruling"].get("ruling", ""))[:60]))
    ratios = [r["disagreement"]["distinct_ratio"] for r in p["rounds"]]
    if len(ratios) > 1 and ratios[-1] < 0.5 and ratios[-1] < ratios[0]:
        print("\n  CONVERGED. Read this as an echo, not a consensus: the panel is one LLM over "
              "one corpus. The finding is about the corpus.")
    if p.get("score"):
        s = p["score"]
        print("\n  scored: accuracy=%s reasoning=%s  beat_origin=%s"
              % (s.get("outcome_accuracy"), s.get("reasoning_quality"), s.get("beat_origin")))


def main() -> None:
    ap = argparse.ArgumentParser(description="Public arena: claim, defend, be judged blind.")
    ap.add_argument("--case")
    ap.add_argument("--panel", default="auto")
    ap.add_argument("--cycles", type=int, default=1)
    ap.add_argument("--model", default="openai/gpt-4o", help="backend model hint")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list-cases", action="store_true")
    ap.add_argument("--score")
    ap.add_argument("--report")
    a = ap.parse_args()
    _load_env()

    if a.list_cases:
        bt = backtest_cases()
        print("[arena] %d backtest cases (each has a SEALED outcome to score against)" % len(bt))
        for s, c in bt.items():
            o = c["origin_score"] or {}
            print("  %-26s T=%-22s origin_accuracy=%s"
                  % (s, c["as_of"][:22], o.get("outcome_accuracy", "unscored")))
            print("      panel: %s" % ", ".join(AUTO_PANELS.get(s, ["(default)"])))
        cd = candidate_cases()
        print("\n[arena] %d candidate cases — survivors of pattern-evaluator." % len(cd))
        print("  These have NO sealed outcome: the judge rules mechanism-or-resemblance,")
        print("  the ruling returns to quarantine, and the operator still decides.")
        for s, c in cd.items():
            print("  %-26s %s" % (s, c["title"]))
        if not cd:
            print("  (none — run pattern-candidates then pattern-evaluator to fill quarantine)")
        return
    if a.score:
        return score(a.score, a.dry_run, a.model)
    if a.report:
        return report(a.report)
    if not a.case:
        ap.print_help()
        return
    run(a.case, a.panel, max(1, a.cycles), a.dry_run, a.model)


if __name__ == "__main__":
    main()
