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
import hashlib
import hmac
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


# --- HMAC authorship signing ------------------------------------------------
#
# The hash chain proves a record was not ALTERED. It cannot prove WHO wrote it,
# because every input to a plain sha256 is public and anyone can recompute it.
# An HMAC mixes in a secret, so a valid tag can only be produced by a holder of
# that secret.
#
# WHAT THIS PROVES: the instance holding ARENA_HMAC_KEY produced this record.
# WHAT IT DOES NOT: that any particular person did, or that the key was not
# copied. It is a shared secret, so anyone who can read .env can sign as this
# instance, and verification requires that same secret -- a third party cannot
# check it without being handed the ability to forge it. Public-key signing
# (ed25519) is what removes that trade-off, and it needs a library this
# stdlib-only engine does not ship.

_KEY_ENV = "ARENA_HMAC_KEY"


def _hmac_key() -> bytes | None:
    """The signing key, loading .env on demand.

    Loading here rather than only in main() matters: run() can be called
    programmatically (the test suite does), and without this every minute from
    such a call would be silently UNSIGNED while .env sat there correctly
    configured. That is the same failure the backend hit earlier in this file,
    and it fails quietly in exactly the same way.
    """
    if not os.environ.get(_KEY_ENV):
        _load_env()
    k = os.environ.get(_KEY_ENV, "").strip()
    return k.encode("utf-8") if k else None


def key_fingerprint(key: bytes) -> str:
    """A public, non-reversible label for which key signed.

    The fingerprint is the hash of the key's hash -- never the key itself, and
    never a prefix of it, so publishing it in a record leaks nothing usable.
    """
    return hashlib.sha256(hashlib.sha256(key).digest()).hexdigest()[:16]


def sign_tag(payload: str, key: bytes) -> str:
    return hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_tag(payload: str, tag: str, key: bytes) -> bool:
    # compare_digest, not ==, so verification time does not leak the tag.
    return hmac.compare_digest(sign_tag(payload, key), tag or "")


def _copy_signed_with_key(rows: list, key: bytes) -> list:
    """Re-sign a copy of `rows` with a different key. Test support only.

    Used to prove that a record signed by someone else's key is reported as
    such, rather than quietly verifying.
    """
    import copy
    out = copy.deepcopy(rows)
    for r in out:
        if r.get("hmac_sha256"):
            r["hmac_sha256"] = sign_tag(r["minute_sha"], key)
            r["key_fingerprint"] = key_fingerprint(key)
    return out


def _sha(data) -> str:
    """sha256 of a string or of a canonicalised object.

    Canonical form is sorted-key, tight-separator JSON so the same content
    always hashes the same way regardless of dict ordering.
    """
    if not isinstance(data, str):
        data = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _tree_dirty(slug: str) -> bool:
    """Does the model's MODEL.md differ from what its HEAD commit records?

    This is the flag that makes a commit hash honest. Demonstrated on
    2026-09-16: editing ai-pressure/MODEL.md without committing left the
    reported commit unchanged, so a minute could cite a commit whose content
    was not what the model read.
    """
    try:
        r = subprocess.run(["git", "status", "--porcelain", "--", "MODEL.md"],
                           cwd=str(TOOLS / slug), capture_output=True, text=True, timeout=10)
        return bool(r.stdout.strip())
    except Exception:
        return False


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


def scenario_cases() -> dict:
    """Forward, conditional cases: "assume X, then what?"

    The other two case types both have something the arena can eventually be
    checked against -- a backtest has a sealed outcome, a candidate has an
    evaluator verdict behind it. A scenario has NEITHER, and pretending
    otherwise would be the worst thing this file could do. So:

      * `sealed_outcome` is empty and `--score` refuses the mode outright.
        There is nothing to reveal; a scenario is scored by waiting.
      * the branch assumption is stated IN the brief as an assumption, so a
        reader of the minutes can see what was granted rather than inferring
        it from the ruling.
      * the brief carries NO conclusion. Same lesson as the 2026-09-16 leak:
        a brief that says what the branch causes hands the panel an answer to
        paraphrase, and the ruling then measures copying.

    A scenario's honest status is "an argument about a conditional", and only
    the branch that actually materialises can ever be graded.

    Case files: MMR/arena/cases/*.md. First line is the title; an optional
    `as of: YYYY-MM-DD` and `question:` line follow; the rest is the brief.
    """
    out = {}
    d = ADIR / "cases"
    if not d.exists():
        return out
    for f in sorted(d.glob("*.md")):
        t = f.read_text(encoding="utf-8", errors="replace")
        lines = t.splitlines()
        if not lines:
            continue
        title = lines[0].lstrip("# ").strip()
        as_of, question, body_at = TODAY, "", 1
        for i, ln in enumerate(lines[1:8], 1):
            low = ln.strip().lower()
            if low.startswith("as of:"):
                as_of, body_at = ln.split(":", 1)[1].strip(), i + 1
            elif low.startswith("question:"):
                question, body_at = ln.split(":", 1)[1].strip(), i + 1
        brief = "\n".join(lines[body_at:]).strip()
        # A SEQUENCED scenario: `## Stage N` sections are argued one per cycle,
        # each carrying the previous stage's ruling forward as its premise --
        # which is the carry-forward run() already does, pointed at a moving
        # brief instead of a fixed one. Everything before the first stage header
        # is shared setting, prepended to every stage, so the pressure table and
        # the no-conclusions setting are stated once rather than per section.
        stages = []
        mstage = list(re.finditer(r"^##\s*Stage\s+\d+\b.*$", brief, re.M))
        if mstage:
            shared = brief[:mstage[0].start()].strip()
            for i, mm in enumerate(mstage):
                end = mstage[i + 1].start() if i + 1 < len(mstage) else len(brief)
                stages.append((shared + "\n\n" + brief[mm.start():end].strip()).strip())
        out[f.stem] = {
            "slug": f.stem, "title": title, "as_of": as_of,
            "brief": brief, "question": question, "stages": stages,
            "sealed_outcome": "", "origin_prediction_withheld": False,
            "thin_setup": len(brief) < 200, "origin_score": None,
            "mode": "scenario", "source": str(f),
        }
    return out


def all_cases() -> dict:
    c = backtest_cases()
    for k, v in c.items():
        v.setdefault("mode", "backtest")
    c.update(candidate_cases())
    c.update(scenario_cases())
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
    raw = p.read_bytes()
    t = raw.decode("utf-8", errors="replace")
    # Hash the EXACT bytes just read, here, rather than re-opening the file
    # later: a read-then-rehash is a race, and the whole point is to attest to
    # what this run actually saw.
    md_sha = hashlib.sha256(raw).hexdigest()
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
        # content identity, not a pointer to it
        "model_md_sha256": md_sha,
        "model_md_bytes": len(raw),
        "tree_dirty": _tree_dirty(slug),
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


SCENARIO_CORE = ["ai-pressure", "lab-moves", "ai-public-backlash"]
SCENARIO_PANELS = {
    "s1-hard-regulation":  SCENARIO_CORE + ["ai-regulation-teeth", "ai-us-policy-direction"],
    "s2-unregulated":      SCENARIO_CORE + ["ai-regulation-teeth", "ai-courts-decide"],
    "s3-public-pressure":  SCENARIO_CORE + ["overton-tracker", "ai-adoption-phases"],
    "s4-asi-emergence":    SCENARIO_CORE + ["ai-rsi-timeline", "ai-oversight-lag"],
    "s5-major-incident":   SCENARIO_CORE + ["ai-incident-severity", "ai-liability-pricing"],
    # SEQUENCED cases. pressure-model IS seated here, unlike s1-s5: the brief now
    # carries a measured installed-stake table, which is what its P6 bridge is
    # about ("E9+ forms install branches with stakes"). It still briefs from its
    # thesis paragraph (P1, felt pressure) rather than from P6, because its
    # MODEL.md states no kind/domain header -- so whether it grips or abstains is
    # itself the finding, and is reported per stage rather than assumed.
    "seq-a-reactive": SCENARIO_CORE + ["pressure-model", "ai-incident-severity",
                                       "ai-regulation-teeth"],
    "seq-b-outrun":   SCENARIO_CORE + ["pressure-model", "ai-rsi-timeline",
                                       "ai-courts-decide"],
    "seq-c-stress":   SCENARIO_CORE + ["pressure-model", "ai-regulation-teeth",
                                       "ai-oversight-lag"],
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
    elif case in SCENARIO_PANELS:
        # A shared core across every scenario, so rulings are comparable
        # branch-to-branch, plus the models whose mechanism actually has grip
        # on that branch. attention-substrate and pressure-model are
        # deliberately NOT seated: both state their mechanism as prose rather
        # than under a kind/domain header, and both abstained as "mechanism
        # unstated" in the candidate runs. A panelist with no grip adds a vote,
        # not a perspective.
        want = SCENARIO_PANELS[case]
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

THE PIVOT. Beyond your claim, name the ONE variable this case actually turns
on — the fact whose resolution would REORDER the outcomes, not merely shift
confidence in them. Not your falsifier: a falsifier is what proves YOU wrong,
while the pivot is what the SITUATION hinges on, and the two are often
different. A pivot must be a thing that could go either way and that someone
could check on a date; "how it plays out" is not a pivot.

Most arguments are not pivots. An argument can be correct, well-evidenced and
still sit entirely on one side of the real hinge — true but not load-bearing.
Say plainly whether your own claim bears on the pivot you named, or falls to
one side of it.

Return STRICT JSON, no prose outside it:
{{
 "grip": "strong" | "partial" | "none",
 "claim": "<your single falsifiable claim about what happens, one sentence>",
 "because": "<the mechanism step that produces it, 2-3 sentences>",
 "falsifier": "<the specific observation that would prove you wrong>",
 "pivot": "<the ONE variable this case turns on, stated so it could resolve either way>",
 "pivot_observable": "<what would settle that variable, and by when>",
 "claim_bears_on_pivot": true | false,
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


JUDGE_SCENARIO = """You are an INDEPENDENT JUDGE. You have not seen any model's
documentation and you do not know which model is which beyond its name. You know
nothing about this situation except what the minutes below contain.

THE QUESTION: {question}

THE MINUTES:
{minutes}

Rule on the ARGUMENT AS ARGUED. You are not scoring who sounds confident, and
you must not reward a claim for being popular -- if four models agree because
they share an assumption, say so and treat it as ONE argument, not four.

This is a CONDITIONAL. The branch in the brief is granted; the question is what
follows from it. Do not re-litigate whether the branch happens. Do rule on
whether a minute smuggled in a SECOND assumption the brief did not grant.

YOUR PRIMARY JOB IS THE PIVOT. Each minute named the variable it thinks this
case turns on. Rule on which one is actually load-bearing: the single variable
whose resolution REORDERS the outcome set, rather than merely shifting
confidence within a fixed order. Test a candidate by asking whether the
situation lands somewhere materially different if it resolves the other way. If
it does not, it is not the pivot however well it was argued.

You may name a pivot NO panelist named, if the minutes make one visible that
they all argued around. Say so explicitly when you do.

Then sort every minute by where it falls:
 - "above"       — bears on the pivot and argues one side of it
 - "below"       — bears on the pivot and argues the other side
 - "not-bearing" — sits entirely to one side, or on a different axis

"not-bearing" IS NOT A CRITICISM AND MUST NOT BE USED AS ONE. A minute can be
correct, well-evidenced and decisive-sounding and still carry no weight on the
hinge. Saying so is the useful part of this ruling: it separates what is true
from what is load-bearing. Do not demote a minute to "not-bearing" because you
disliked it, and do not promote a weak argument because it touched the pivot.

Three further fields specific to this mode:
 - `threat_live`: what becomes newly dangerous, or newly safe, on this branch --
   the risk arriving WITH the assumed change rather than as a background
   condition. If the minutes identify none, say so; do not invent one.
 - `resolve_by`: the single date by which your ruling is checkable. A ruling with
   no date is not a ruling, it is a mood.
 - `smuggled_assumption`: a premise a minute used that the brief did not grant.

Return STRICT JSON:
{{
 "pivot": "<the ONE variable this case turns on, stated so it could resolve either way>",
 "pivot_observable": "<the concrete thing that settles it>",
 "pivot_resolves_by": "<YYYY-MM-DD>",
 "pivot_source": "<slug of the minute that named it, or 'judge' if none did>",
 "pivot_because": "<why THIS variable reorders outcomes and the rivals do not, 2-4 sentences>",
 "minutes_by_side": {{"<slug>": "above|below|not-bearing"}},
 "rival_pivots_rejected": "<the other candidates named, and why each is not the hinge>",
 "ruling": "<your single best answer to the question, one sentence>",
 "because": "<what in the minutes decided it, 2-4 sentences>",
 "resolve_by": "<YYYY-MM-DD by which this ruling is checkable>",
 "threat_live": "<what becomes newly dangerous or newly safe on this branch, or null>",
 "strongest_minute": "<slug whose argument was best, and why>",
 "weakest_minute": "<slug whose argument was weakest, and why>",
 "shared_assumption": "<an assumption multiple models relied on without arguing for it, or null>",
 "smuggled_assumption": "<a premise a minute used that the brief did not grant, or null>",
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


def _call_many(model_hint: str, prompts: list, dry: bool, workers: int = 0) -> list:
    """Run independent prompts concurrently, returning bodies IN INPUT ORDER.

    Safe only where the prompts genuinely do not depend on each other, which in
    this file is exactly two places and no others:

      * round 1 -- every claim is written before its author sees anyone else.
        That is the arena's first blindness, so the calls were already
        independent; running them in sequence was a property of the loop, not
        of the design.
      * round 2 -- each defence sees ALL of round 1 and none of round 2. The
        board is built once, before any call goes out.

    The judge is NOT run through here: there is one of it, and it must see the
    finished minutes.

    WHY ORDER IS PRESERVED. Minutes are hashed into a chain, and the chain is
    order-sensitive by design -- reordering two minutes is meant to break every
    hash after them. So results are collected into a pre-sized list by index
    and the chain is built afterwards, in panel order, exactly as the sequential
    version did. A run's minutes are therefore byte-identical in structure
    whether or not this ran concurrently; only `at` timestamps differ, and they
    were never ordered by anything but call completion anyway.

    Concurrency is bounded and overridable (ARENA_WORKERS), because each call on
    the claude-code backend is a CLI subprocess billing one subscription: too
    many at once trades a rate-limit error for the wall time it was meant to
    save. On a dry run nothing is dispatched.
    """
    n = len(prompts)
    if dry or n <= 1:
        return [_call(model_hint, p, dry) for p in prompts]
    if workers <= 0:
        try:
            workers = int(os.environ.get("ARENA_WORKERS", "4"))
        except ValueError:
            workers = 4
    workers = max(1, min(workers, n))
    if workers == 1:
        return [_call(model_hint, p, dry) for p in prompts]
    out: list = [None] * n
    from concurrent.futures import ThreadPoolExecutor
    # Threads, not processes: every backend here blocks on IO (a subprocess or
    # an HTTP request), so the GIL is released while waiting and threads are
    # both sufficient and far cheaper to reason about.
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_call, model_hint, p, dry): i for i, p in enumerate(prompts)}
        for f in list(futs):
            i = futs[f]
            try:
                out[i] = f.result()
            except Exception as e:  # a crashed worker is not an empty answer
                out[i] = {"_error": "%s: %s" % (type(e).__name__, e)}
    return out


def _minute(kind: str, who: dict, cycle: int, rnd: int, body: dict,
            prompt: str = "", prev_sha: str = "") -> dict:
    """A signed, chained minute.

    WHAT "SIGNED" MEANS HERE, stated precisely because it is easy to overclaim:

      * `model_md_sha256` is the hash of the MODEL.md bytes this run actually
        read. Unlike `model_commit`, which is only a pointer, it changes the
        moment the document changes -- committed or not.
      * `tree_dirty` says whether that content differed from the model's HEAD.
        A dirty minute is still valid; it is just not reproducible from git
        alone, and it says so.
      * `prev_minute_sha` chains each minute to the one before it, so editing
        or deleting any minute breaks every `minute_sha` that follows.

    This is TAMPER-EVIDENCE, not authorship proof. It shows that a record was
    not altered after the fact. It does not prove WHO produced it -- that needs
    a private key, and a timestamp is not a key because everyone knows the date.
    """
    m = {
        "cycle": cycle, "round": rnd, "type": kind,
        "signed_by": who.get("slug"),
        "model_title": who.get("title", ""),
        "model_version": who.get("version", ""),
        "model_commit": who.get("commit", ""),
        "model_md_sha256": who.get("model_md_sha256", ""),
        "model_md_bytes": who.get("model_md_bytes", 0),
        "tree_dirty": bool(who.get("tree_dirty", False)),
        "at": datetime.datetime.now().isoformat(timespec="seconds"),
        "prompt_sha256": _sha(prompt) if prompt else "",
        "body_sha256": _sha(body),
        "prev_minute_sha": prev_sha,
        "body": body,
    }
    # The minute's own hash covers everything above it, including the
    # timestamp and the previous link. Computed over the record WITHOUT
    # minute_sha itself, which cannot contain its own hash.
    m["minute_sha"] = _sha({k: v for k, v in m.items() if k != "body"} | {"body": body})

    # Authorship tag over the minute hash. Absent when no key is configured --
    # an unsigned minute is honest about being unsigned rather than carrying an
    # empty field that looks like a signature.
    key = _hmac_key()
    if key:
        m["hmac_sha256"] = sign_tag(m["minute_sha"], key)
        m["key_fingerprint"] = key_fingerprint(key)
    return m


def verify_chain(rows: list) -> dict:
    """Recompute every minute's hash and every link. Returns the first break.

    A run whose minutes were written before signing existed has no hashes;
    that is reported as UNSIGNED rather than as a failure, because a
    pre-signing record is not a tampered one.
    """
    if not rows:
        return {"ok": False, "reason": "no minutes"}
    if not any(r.get("minute_sha") for r in rows):
        return {"ok": None, "reason": "unsigned (pre-chain run)", "rows": len(rows)}
    prev = ""
    for i, r in enumerate(rows):
        want_body = _sha(r.get("body"))
        if r.get("body_sha256") != want_body:
            return {"ok": False, "reason": "body altered", "row": i,
                    "signed_by": r.get("signed_by")}
        if r.get("prev_minute_sha", "") != prev:
            return {"ok": False, "reason": "chain link broken (a minute was "
                                           "inserted, removed or reordered)",
                    "row": i, "signed_by": r.get("signed_by")}
        # The tag fields are added AFTER minute_sha is computed, so they must be
        # excluded when recomputing it -- otherwise a correctly signed minute
        # fails its own integrity check.
        recomputed = _sha({k: v for k, v in r.items()
                           if k not in ("minute_sha", "body", "hmac_sha256",
                                        "key_fingerprint")} | {"body": r.get("body")})
        if r.get("minute_sha") != recomputed:
            return {"ok": False, "reason": "minute hash mismatch", "row": i,
                    "signed_by": r.get("signed_by")}
        prev = r["minute_sha"]

    # authorship, checked separately from integrity: a record can be intact and
    # unsigned, or intact and signed by a key we do not hold. Those are three
    # different states and are reported as such rather than collapsed to a bool.
    key = _hmac_key()
    tagged = [r for r in rows if r.get("hmac_sha256")]
    auth = {"signed_rows": len(tagged), "total_rows": len(rows)}
    if not tagged:
        auth["status"] = "unsigned"
    elif not key:
        auth["status"] = "signed, but no key configured to verify"
        auth["key_fingerprint"] = tagged[0].get("key_fingerprint", "")
    else:
        fp = key_fingerprint(key)
        wrong = [r.get("signed_by") for r in tagged if r.get("key_fingerprint") != fp]
        if wrong:
            auth["status"] = "signed by a DIFFERENT key"
            auth["their_fingerprint"] = tagged[0].get("key_fingerprint", "")
            auth["our_fingerprint"] = fp
        else:
            bad = [r.get("signed_by") for r in tagged
                   if not verify_tag(r["minute_sha"], r["hmac_sha256"], key)]
            if bad:
                auth["status"] = "FORGED OR ALTERED — hmac did not verify"
                auth["rows"] = bad[:5]
            elif len(tagged) != len(rows):
                auth["status"] = "partially signed"
            else:
                auth["status"] = "verified"
                auth["key_fingerprint"] = fp

    return {"ok": True, "rows": len(rows), "head": prev,
            "dirty_minutes": sum(1 for r in rows if r.get("tree_dirty")),
            "authorship": auth}


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
    stages = case.get("stages") or []
    if stages and cycles < len(stages):
        # A sequence argued short of its last stage is not that sequence.
        # Raising the count is the honest fix: stopping halfway, or arguing
        # stage 1 repeatedly, would both file something else under this name.
        print("  [note] %d stages in this case; running %d cycles (asked %d)"
              % (len(stages), len(stages), cycles))
        cycles = len(stages)
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
    elif mode == "scenario":
        # The case file states its own question, because a conditional's
        # question IS the branch. Falls back to the backtest phrasing only if
        # the file omitted one.
        question = case.get("question") or (
            "Given the assumption stated in the brief: what follows, and why?")
    else:
        question = "As of %s: what happens next, and why?" % (case["as_of"] or "the case date")
    premise = None
    all_cycles = []
    chain_head = ""   # links cycle N's first minute to cycle N-1's last

    for cyc in range(1, cycles + 1):
        print("\n  -- cycle %d --" % cyc)
        minutes = []
        brief = stages[cyc - 1] if stages and cyc <= len(stages) else case["brief"]
        if premise:
            brief += ("\n\nPREMISE CARRIED FROM THE PREVIOUS CYCLE (an independent judge's "
                      "ruling on the prior round's minutes — not a fact, and you may argue "
                      "against it):\n%s" % premise)

        # round 1 — claim, written before anyone sees anyone else.
        #
        # Every prompt is built before any call goes out, which is the same
        # thing the blindness already required: a round-1 prompt cannot contain
        # another model's minute because no such minute exists yet. So these run
        # concurrently, and the minutes are still chained in panel order below.
        r1_prompts = [
            CLAIM.format(title=p["title"], slug=p["slug"], kind=p["kind"],
                         one_line=p["one_line"], as_of=case["as_of"], brief=brief)
            for p in panel]
        r1_bodies = _call_many(model_hint, r1_prompts, dry)
        for p, prompt, body in zip(panel, r1_prompts, r1_bodies):
            minutes.append(_minute("claim", p, cyc, 1, body, prompt,
                                   minutes[-1]["minute_sha"] if minutes else chain_head))
            print("     r1 %-26s grip=%-8s conf=%s" % (p["slug"], body.get("grip"), body.get("confidence")))

        # round 2 — defend or revise, now seeing the others.
        #
        # The board is built once, from the completed round 1, so every defence
        # sees the same material and none sees another defence. That was already
        # true sequentially -- a later panelist never saw an earlier panelist's
        # round-2 minute, because `board` is filtered to round 1.
        board = "\n".join(
            "- [%s] %s" % (m["signed_by"], str(m["body"].get("claim", ""))[:220])
            for m in minutes if m["round"] == 1)
        r2_prompts = []
        for p in panel:
            mine = next((m for m in minutes if m["signed_by"] == p["slug"] and m["round"] == 1), None)
            others = "\n".join(l for l in board.splitlines() if not l.startswith("- [%s]" % p["slug"]))
            r2_prompts.append(DEFEND.format(
                title=p["title"], slug=p["slug"],
                mine=json.dumps(mine["body"], ensure_ascii=False)[:700] if mine else "",
                others=others or "(no other minutes)"))
        r2_bodies = _call_many(model_hint, r2_prompts, dry)
        for p, prompt, body in zip(panel, r2_prompts, r2_bodies):
            minutes.append(_minute("defence", p, cyc, 2, body, prompt,
                                   minutes[-1]["minute_sha"]))
            print("     r2 %-26s %-8s moved_by=%s" % (p["slug"], body.get("move"), body.get("moved_by")))

        # the judge — minutes only. No MODEL.md, no sealed outcome.
        jtext = "\n".join(
            "[%s | %s | commit %s | round %d] %s"
            % (m["signed_by"], m["model_version"] or "unversioned", m["model_commit"] or "uncommitted",
               m["round"], json.dumps(m["body"], ensure_ascii=False)[:600])
            for m in minutes)
        jtmpl = (JUDGE_CANDIDATE if mode == "candidate"
                 else JUDGE_SCENARIO if mode == "scenario" else JUDGE)
        jprompt = jtmpl.format(question=question, minutes=jtext)
        jbody = _call(model_hint, jprompt, dry)
        # The judge has no MODEL.md, so what identifies its "version" is the
        # prompt template it ruled under. Hashing that makes a later change to
        # the judging standard visible in the record.
        judge_who = {"slug": JUDGE_SLUG, "title": "Independent judge",
                     "version": ("candidate-v1" if mode == "candidate"
                                 else "scenario-v2-pivot" if mode == "scenario" else "backtest-v1"),
                     "commit": "", "model_md_sha256": _sha(jtmpl),
                     "model_md_bytes": len(jtmpl), "tree_dirty": False}
        ruling = _minute("ruling", judge_who, cyc, 3, jbody, jprompt,
                         minutes[-1]["minute_sha"])
        minutes.append(ruling)
        print("     JUDGE  %s" % str(jbody.get("ruling", ""))[:88])
        if jbody.get("pivot"):
            src = jbody.get("pivot_source") or "?"
            print("     PIVOT [%s]: %s" % (src, str(jbody["pivot"])[:78]))
            sides = jbody.get("minutes_by_side") or {}
            if sides:
                nb = [k for k, v in sides.items() if str(v).startswith("not-bear")]
                print("       sides: %s" % ", ".join("%s=%s" % (k, v) for k, v in sides.items()))
                if nb:
                    # Not a demerit. A minute can be right and carry no weight on
                    # the hinge, and separating those is the point of the field.
                    print("       not bearing on the pivot (not a criticism): %s" % ", ".join(nb))
        if jbody.get("shared_assumption"):
            print("     judge flags shared assumption: %s" % str(jbody["shared_assumption"])[:80])

        chain_head = minutes[-1]["minute_sha"]
        chain = verify_chain(minutes)
        dis = disagreement(minutes)
        print("     disagreement: %d/%d distinct (ratio %.2f) · %d revised · spread %.2f"
              % (dis["distinct_claims"], dis["panelists"], dis["distinct_ratio"],
                 dis["revised"], dis["confidence_spread"]))
        print("     chain: %s · head %s%s"
              % ("verified" if chain.get("ok") else str(chain.get("reason")),
                 str(chain.get("head", ""))[:12],
                 ("  · %d minute(s) spoke from an UNCOMMITTED MODEL.md"
                  % chain["dirty_minutes"]) if chain.get("dirty_minutes") else ""))

        cdir = outdir / ("cycle-%d" % cyc)
        cdir.mkdir(exist_ok=True)
        with (cdir / "minutes.jsonl").open("w", encoding="utf-8") as fh:
            for m in minutes:
                fh.write(json.dumps(m, ensure_ascii=False) + "\n")
        (cdir / "ruling.json").write_text(json.dumps(jbody, ensure_ascii=False, indent=1), encoding="utf-8")
        all_cycles.append({"cycle": cyc, "ruling": jbody, "disagreement": dis,
                           "minutes": len(minutes), "chain": chain})

        # the judge's ruling — NOT the panel's consensus — carries forward
        premise = jbody.get("ruling")

    payload = {
        "spec": "arena-v2-signed", "run_id": run_id, "built": TODAY, "case": case_slug,
        "case_title": case["title"], "as_of": case["as_of"], "question": question,
        "cycles": len(all_cycles), "dry_run": bool(dry),
        "panel": [{k: p[k] for k in ("slug", "title", "kind", "version", "commit", "derived")} for p in panel],
        "signing": {
            "scheme": "sha256 content hash + minute hash chain",
            "attests": ["the MODEL.md bytes each model actually read",
                        "the exact prompt sent", "the response body",
                        "the order of minutes", "the timestamp of each minute"],
            "does_not_attest": ["WHO produced the record — that needs a private "
                                "key, and a timestamp is not a key",
                                "that a dirty working tree matched any commit"],
            "verify": "python -m suites.arena --report <run_id>",
        },
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
    # A scenario has no sealed outcome to reveal. Scoring one would have to
    # invent the outcome it claims to be scoring against, so it is refused
    # rather than allowed to produce a number that means nothing.
    if payload.get("mode") == "scenario":
        raise SystemExit(
            "%s is a SCENARIO run: there is no sealed outcome to score against.\n"
            "A conditional is graded by waiting for the branch to materialise, "
            "not by revealing an answer that was never written." % run_id)
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
        ru = r["ruling"]
        if ru.get("pivot"):
            print("          pivot [%s, by %s]: %s"
                  % (ru.get("pivot_source") or "?", ru.get("pivot_resolves_by") or "undated",
                     str(ru["pivot"])[:66]))
            sides = ru.get("minutes_by_side") or {}
            nb = [k for k, v in sides.items() if str(v).startswith("not-bear")]
            if sides:
                bear = len(sides) - len(nb)
                # Printed as a COUNT, not as a verdict on any model: a minute off
                # the hinge is not a worse minute, and the split is the finding.
                print("          %d of %d minutes bear on it; off-hinge: %s"
                      % (bear, len(sides), ", ".join(nb) if nb else "none"))
    # Re-verify from the minutes on disk rather than trusting the stored
    # verdict: a stored "ok" that is never recomputed attests to nothing.
    print("\n  chain verification (recomputed from minutes.jsonl):")
    for r in p["rounds"]:
        f = ADIR / run_id / ("cycle-%d" % r["cycle"]) / "minutes.jsonl"
        rows = []
        if f.exists():
            rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        v = verify_chain(rows)
        if v.get("ok") is None:
            print("   cycle %d  UNSIGNED — written before signing existed (%s rows). "
                  "Content is not attested." % (r["cycle"], v.get("rows", 0)))
        elif v.get("ok"):
            print("   cycle %d  VERIFIED  %d minutes · head %s%s"
                  % (r["cycle"], v["rows"], v["head"][:16],
                     ("  · %d from an uncommitted MODEL.md" % v["dirty_minutes"])
                     if v["dirty_minutes"] else ""))
            a = v.get("authorship", {})
            st = a.get("status", "unsigned")
            if st == "verified":
                print("            authorship: signed by key %s (all %d minutes)"
                      % (a.get("key_fingerprint", "?"), a.get("signed_rows", 0)))
            elif st == "unsigned":
                print("            authorship: UNSIGNED - integrity only. Who produced\n                      this record is not attested.")
            else:
                print("            authorship: *** %s ***" % st)
        else:
            print("   cycle %d  *** BROKEN *** %s at row %d (%s)"
                  % (r["cycle"], v.get("reason"), v.get("row", -1), v.get("signed_by")))

    ratios = [r["disagreement"]["distinct_ratio"] for r in p["rounds"]]
    if len(ratios) > 1 and ratios[-1] < 0.5 and ratios[-1] < ratios[0]:
        print("\n  CONVERGED. Read this as an echo, not a consensus: the panel is one LLM over "
              "one corpus. The finding is about the corpus.")
    if p.get("score"):
        s = p["score"]
        print("\n  scored: accuracy=%s reasoning=%s  beat_origin=%s"
              % (s.get("outcome_accuracy"), s.get("reasoning_quality"), s.get("beat_origin")))


def keygen() -> None:
    """Write a fresh ARENA_HMAC_KEY into .env. Never overwrites an existing one.

    Overwriting would silently orphan every minute already signed with the old
    key -- they would verify as "signed by a DIFFERENT key", which is correct
    but unrecoverable. Rotating is therefore a deliberate manual act.
    """
    import secrets
    f = ROOT / ".env"
    existing = f.read_text(encoding="utf-8") if f.exists() else ""
    if _KEY_ENV in existing:
        key = _hmac_key()
        print("[arena] %s already set in .env - not overwriting." % _KEY_ENV)
        if key:
            print("  fingerprint: %s" % key_fingerprint(key))
        print("  Rotating orphans every minute signed with the old key; to rotate,")
        print("  remove the line by hand first and keep a note of the old fingerprint.")
        return
    key = secrets.token_hex(32)
    lines = [
        "",
        "# Authorship signing for suites.arena. SECRET -- .env is gitignored.",
        "# Anyone holding this can sign as this instance; verification needs it too.",
        "%s=%s" % (_KEY_ENV, key),
        "",
    ]
    with f.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("[arena] wrote %s to .env (256-bit, from secrets.token_hex)" % _KEY_ENV)
    print("  fingerprint: %s" % key_fingerprint(key.encode("utf-8")))
    print("  .env is gitignored and untracked - verified before this feature was built.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Public arena: claim, defend, be judged blind.")
    ap.add_argument("--case")
    ap.add_argument("--panel", default="auto")
    ap.add_argument("--cycles", type=int, default=1)
    ap.add_argument("--model", default="openai/gpt-4o", help="backend model hint")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--tag", default="", help="namespace this run: arena-<case>-<date>-<tag>. "
                    "Use it for a re-run so a same-day run does not overwrite the first.")
    ap.add_argument("--list-cases", action="store_true")
    ap.add_argument("--score")
    ap.add_argument("--report")
    ap.add_argument("--keygen", action="store_true",
                    help="generate an ARENA_HMAC_KEY into .env (never overwrites)")
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
        sc = scenario_cases()
        print("\n[arena] %d scenario cases — forward conditionals ('assume X, then what?')." % len(sc))
        print("  These have NO sealed outcome and NO evaluator behind them. --score refuses")
        print("  them: a conditional is graded by waiting for the branch, not by revealing")
        print("  an answer nobody wrote. Only the branch that materialises is ever gradeable.")
        for s, c in sc.items():
            print("  %-26s %s" % (s, c["title"]))
        if not sc:
            print("  (none — add a case file to arena/cases/*.md)")
        return
    if a.score:
        return score(a.score, a.dry_run, a.model)
    if a.keygen:
        return keygen()
    if a.report:
        return report(a.report)
    if not a.case:
        ap.print_help()
        return
    run(a.case, a.panel, max(1, a.cycles), a.dry_run, a.model, a.tag)


if __name__ == "__main__":
    main()
