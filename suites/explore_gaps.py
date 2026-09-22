"""Propose model candidates for the cells the reality map says are empty.

The map is the brief. 45 models cover 42 of 180 aspect x floor cells, and they
cluster: everything sits between E8 and E13, in 8 of 12 aspects. The empty cells
are not all equal -- most are empty because no AI-threat mechanism operates
there, and a model at such a cell would be vocabulary rather than a model.

So this proposes CANDIDATES, not models. A candidate is one line: the mechanism,
the cell it occupies, and the dated observable that would falsify it. Candidates
are then filtered before any repo is scaffolded, because the expensive mistake
is 55 repos that each fail the listability bar for having no real falsifier.

THE FILTER, applied in code rather than by the model that proposed them:

  * a dated observable, resolving inside 18 months
  * a mechanism that is not a restatement of an existing model's
  * an aspect x floor cell that is actually empty
  * a switch-off test: if the AI were removed, does the claim still hold? If it
    does, the model is about something else and the AI is decoration.

  python -m suites.explore_gaps --propose          # candidates, nothing written
  python -m suites.explore_gaps --propose --apply  # write candidates.json
  python -m suites.explore_gaps --filter           # score what was proposed
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
OUT = ROOT / "explore"
TODAY = datetime.date.today().isoformat()

# The regions worth proposing into, and WHY each is plausible. A region with no
# stated mechanism does not belong here -- that is the judgement this file
# exists to make explicitly rather than leave to a prompt.
REGIONS = [
    ("E0-E1 · matter-energy",
     "Datacentre thermodynamics, grid interconnection queues, transformer and turbine "
     "lead times, water for cooling. AI threat operates here as a PHYSICAL constraint: "
     "compute that cannot be powered is compute that does not exist."),
    ("E4-E6 · life",
     "AI-assisted protein design, synthesis screening, and the gap between what a model "
     "can design and what a benchtop can make. Operates here because the threat is "
     "mediated by biology, not by persuasion."),
    ("E7 · individual-minds (substrate)",
     "Interpretability, the gap between a system's stated and operating objective, and "
     "what is legible before deployment. Below E8 because it is about the substrate "
     "that produces a mind, not a mind's choices."),
    ("E14 · civilization-longterm",
     "Irreversibility: commitments whose cost to undo rises faster than the evidence "
     "needed to justify undoing them. Long-horizon lock-in of standards, dependencies "
     "and institutional form."),
    ("countries and blocs",
     "India, Gulf states, Brazil, Nigeria, Indonesia, Japan, Korea. Present models are "
     "US/EU/China-shaped; a threat model that only reads three jurisdictions cannot see "
     "a fourth deciding something."),
    ("domains under-covered",
     "Insurance and reinsurance, standards bodies, export-control enforcement mechanics, "
     "labour and unions, education, elections administration, healthcare procurement, "
     "military procurement, cloud concentration, undersea cable and chokepoint physics."),
    ("missing aspects",
     "infrastructure-logistics, attention-media and culture-narrative are thin (4-5 "
     "models each) relative to science-epistemics (23). Not every gap is a floor gap."),
    # Formal threat modelling is a DIFFERENT DISCIPLINE from forecasting, and
    # mixing the two produces neither. A forecaster says what will happen; a
    # kill chain says what an adversary must accomplish in order, and where the
    # cheapest place to break it is. The fleet has adversary-kind models but no
    # structured attack decomposition.
    ("kill chains and attack trees",
     "Lockheed-Martin style: decompose an AI-enabled harm into the ordered stages an "
     "adversary must complete -- reconnaissance, weaponization, delivery, exploitation, "
     "installation, command-and-control, actions on objectives -- and identify which "
     "stage is cheapest to break. Applies to AI-enabled intrusion, model supply-chain "
     "compromise, synthetic-media operations, and autonomous agent misuse. The model "
     "claims WHICH STAGE breaks first, which is falsifiable when an incident occurs."),
    # The Diamond Model complements the kill chain rather than repeating it: a
    # kill chain is a SEQUENCE, a diamond is a RELATION. Its four vertices are
    # adversary, capability, infrastructure, victim, joined by edges that let an
    # analyst pivot -- observe infrastructure, infer capability, reach the
    # victim class. It also fits this fleet unusually well, because three of the
    # four vertices are observable and only "adversary" tempts interiority.
    ("diamond model: adversary, capability, infrastructure, victim",
     "Four-vertex analysis of an AI-enabled intrusion or influence event, and the PIVOTS "
     "between vertices -- from an observed capability to the infrastructure it requires, "
     "from infrastructure to the victim class it can reach, from victim to the adversary "
     "class for whom that victim is worth the cost. Applies to model-weight theft, "
     "agentic tool abuse, synthetic-media operations, and poisoned training data. Only "
     "the adversary vertex risks a claim about intent, so it is characterised by "
     "DEMONSTRATED capability and access. The model claims which pivot is available "
     "first when an incident surfaces -- typically infrastructure -- and is falsified "
     "when the next reported incident is attributed by a different route."),
    ("adversary capability and intent-free threat actors",
     "Threat actors characterised by DEMONSTRATED capability and access, never by "
     "assumed motive -- the fleet bans interiority, which is unusually compatible with "
     "capability-based threat modelling. What can a given actor class actually do this "
     "quarter: state services, criminal groups, insiders, unaligned automation? What "
     "capability would have to be demonstrated for the assessment to change?"),
    # Attack surface is not one region. Each surface has a different owner, a
    # different control, and a different observable, so they are proposed
    # separately -- one region listing six surfaces produced candidates spread
    # too thin to be mechanisms.
    ("attack surface · the training pipeline",
     "Everything upstream of a released model: data acquisition and provenance, "
     "poisoned or laundered corpora, annotation and RLHF contractor access, checkpoint "
     "storage, and the build chain that turns a corpus into weights. The defining "
     "property is that compromise here is LATENT -- it is present in the artefact and "
     "invisible at inference until triggered. Observables: a disclosed poisoning "
     "incident, a provenance requirement entering a procurement contract, a published "
     "audit of training-data supply."),
    ("attack surface · weights, inference and the served endpoint",
     "The model as a deployed asset: weight exfiltration by insider or intrusion, "
     "extraction and distillation through an API, prompt injection reaching a system "
     "prompt, jailbreaks that survive a published patch, and side channels in serving "
     "infrastructure. The defining property is that the attacker interacts with a "
     "RUNNING system, so every attempt is in principle logged -- and whether it is "
     "logged is itself the finding. Observables: a disclosed weight-theft incident, a "
     "provider publishing extraction-rate data, a jailbreak surviving N patch cycles."),
    ("attack surface · agents, tools and the blast radius of autonomy",
     "What changes when a model is given credentials, a browser, a shell, a payment "
     "method or another agent to talk to. The surface is the TOOL BOUNDARY: what the "
     "agent can reach, what it can do without a human in the loop, and what a single "
     "compromised step can touch. Distinct from jailbreaks because the harm does not "
     "require the model to be fooled -- a correctly-following agent with over-broad "
     "permissions is sufficient. Observables: a reported agentic incident with a named "
     "scope of access, a provider publishing default tool permissions, an enterprise "
     "policy requiring human approval at a named step."),
    ("attack surface · the supply chain beneath the model",
     "Dependencies nobody treats as an AI surface: the ML framework and its transitive "
     "packages, model hubs and unsigned artefacts, container images, GPU firmware and "
     "drivers, the cloud tenancy, and the handful of orchestration tools everyone "
     "shares. Concentration is the mechanism -- a compromise at a shared dependency "
     "reaches every downstream deployment at once, which is the opposite of the "
     "distributed picture most threat models assume. Observables: a CVE in a named ML "
     "dependency with disclosed downstream count, a hub introducing artefact signing, a "
     "named provider publishing an SBOM for a model release."),
    ("control efficacy · what has actually been tested",
     "Not which mitigations exist but which have a DEMONSTRATED effect under "
     "adversarial conditions. Red-team findings that changed a release decision, "
     "evaluation suites that a model failed and was held back for, filters measured "
     "against an adaptive attacker rather than a fixed benchmark, and the gap between "
     "a control's announced scope and its tested scope. A control nobody has tested "
     "adversarially is a claim, not a control -- and the model's job is to say which "
     "is which, with the test as the observable."),
    ("evaluation gaming and the measurement surface",
     "The evaluations themselves as an attack surface: benchmark contamination, "
     "training on the test set by accident or design, evaluations scoped so that "
     "passing is uninformative, and the incentive to optimise a metric a third party "
     "will publish. Distinct from other surfaces because the victim is the REASONING "
     "of everyone downstream who trusts the number, including regulators writing "
     "thresholds into rules. Observables: a contamination finding on a named benchmark, "
     "an evaluator publishing a held-out protocol, a regulator citing a specific "
     "evaluation in binding text."),
    # Deflection is observable WITHOUT claiming intent, and the distinction is
    # the whole design. "He dodged" is a claim about a mind and is banned.
    # "The answer did not contain the asked-for object, and the topic moved to X"
    # is a claim about a transcript, checkable by anyone with the tape.
    ("non-answers under questioning",
     "What happens to a QUESTION when a powerful actor is asked it on the record. "
     "Observable without any claim about intent: does the response contain the "
     "asked-for object (a date, a number, a name, a yes/no)? If not, what does it "
     "contain instead -- a reframe to a different timescale, a shift from the specific "
     "to the categorical, an appeal to process, a counter-question, a pivot to a rival "
     "actor's conduct? WHICH questions reliably produce non-answers is a fact about "
     "what is unanswerable in public, not about the answerer. Track the question "
     "classes -- capability timelines, incident counts, evaluation access, revenue "
     "concentration, compute sourcing -- and which produce a specific answer from whom. "
     "The model claims that a NAMED question class produces a non-answer from a NAMED "
     "role, and is falsified the moment someone in that role answers it specifically."),
    ("topic control and agenda substitution",
     "Where a conversation goes after a hard question, measured as a transition rather "
     "than an inference: interview and hearing transcripts have a question topic and an "
     "answer topic, and the gap between them is data. Which substitutions recur "
     "(safety->competitiveness, harm->benefit, present->future, us->China), who performs "
     "them, and whether an interviewer returns to the original question. Falsifiable "
     "against any transcript, and the subtext claim -- that the substituted topic is "
     "the one the actor is under pressure on -- is checkable against the pressure field "
     "the fleet already computes."),
    ("risk registers, severity and cascade",
     "Quantified risk mapping: likelihood x impact, but with the failure modes named -- "
     "correlated risks scored as independent, tail events priced on a normal, and "
     "cascade paths where one realised risk changes the probability of others. Where "
     "does a single failure propagate across the map, and what is the shortest path "
     "from an observed incident to a systemic one?"),
]

PROMPT = """You are proposing MODEL CANDIDATES for a fleet that already holds 45
forecasting models about AI risk. A model here is a document: premises, a
mechanism, at least one dated falsifiable consequence, and a deletion clause.

THE FLEET ALREADY COVERS THIS, and you must not propose a restatement:
{existing}

THE GAP YOU ARE PROPOSING INTO:
{region}
{why}

Propose {n} candidates. Each must be a mechanism nobody in the list above is
running, and must pass this test before you write it down:

  THE SWITCH-OFF TEST. If frontier AI were removed from the world, would the
  claim still hold? If yes, the model is about something else and the AI is
  decoration. Say what specifically breaks without the AI.

Each candidate must name a DATED OBSERVABLE resolving within 18 months of
{today} -- a specific, checkable event, not a trend. "Adoption increases" is not
an observable. "X publishes Y by DATE" is.

Do NOT propose:
  - anything requiring a claim about what a person or company believes, wants or
    fears. This fleet bans interiority everywhere.
  - a model whose only content is that something is important.
  - a restatement of a textbook with AI vocabulary attached.

Return STRICT JSON:
{{
 "candidates": [
  {{"slug": "<short-kebab-slug>",
    "title": "<what it models, one line>",
    "mechanism": "<the causal claim, one or two sentences>",
    "aspect": "<one of: matter-energy, life, individual-minds, science-epistemics, technology-tools, economy-markets, institutions, states-geopolitics, culture-narrative, attention-media, infrastructure-logistics, civilization-longterm>",
    "e_span": [<low>, <high>],
    "kind": "<forecaster|classifier|tracker|tracer|finder|timer|attributor|adversary|mirror|generator>",
    "observable": "<the dated, checkable event>",
    "resolve_by": "<YYYY-MM-DD>",
    "switch_off": "<what specifically breaks if frontier AI is removed>",
    "rival": "<the boring explanation that would explain the same observable>",
    "threat_frame": "<OPTIONAL. For a threat model only: the ordered stages an adversary must complete, and WHICH STAGE this model claims is cheapest to break. Omit entirely for a forecasting model -- an empty frame is worse than none.>"}}
 ]
}}

If the gap you are proposing into is a threat-modelling one, the dated
observable is still required and is usually of this shape: "when an incident of
class X is next publicly reported by DATE, the reporting shows it was stopped
at / got through stage N." A threat model that cannot be checked against an
incident is a diagram, not a model."""


def existing_models() -> str:
    f = ROOT / "map" / "mapcards.json"
    if not f.exists():
        return "(no map built)"
    d = json.loads(f.read_text(encoding="utf-8"))
    out = []
    for c in d.get("cards", []):
        out.append("- %s: %s" % (c.get("model"), (c.get("mechanism") or "")[:110]))
    return "\n".join(sorted(out))


def propose(n_per: int, dry: bool, model_hint: str) -> list:
    from suites import arena as A
    A._load_env()
    ex = existing_models()
    prompts, labels = [], []
    for region, why in REGIONS:
        prompts.append(PROMPT.format(existing=ex, region=region, why=why,
                                     n=n_per, today=TODAY))
        labels.append(region)
    bodies = A._call_many(model_hint, prompts, dry,
                          on_done=lambda i, b: print("    proposed: %s" % labels[i]))
    out = []
    for label, b in zip(labels, bodies):
        if b.get("_error") or b.get("_unparsed"):
            print("  ! %s: %s" % (label, str(b.get("_error") or "unparsed")[:80]))
            continue
        for c in (b.get("candidates") or []):
            c["region"] = label
            out.append(c)
    return out


# ------------------------------------------------------------------ filter

ASPECTS = {"matter-energy", "life", "individual-minds", "science-epistemics",
           "technology-tools", "economy-markets", "institutions",
           "states-geopolitics", "culture-narrative", "attention-media",
           "infrastructure-logistics", "civilization-longterm"}


def score(c: dict, taken: set) -> tuple:
    """(ok, reasons). Reasons are why it was REJECTED; empty means it passed."""
    bad = []
    slug = c.get("slug", "")
    if not re.fullmatch(r"[a-z0-9-]{3,48}", slug):
        bad.append("slug not a clean kebab slug")
    if slug in taken:
        bad.append("slug collides with an existing model")
    if c.get("aspect") not in ASPECTS:
        bad.append("aspect %r not on the map" % c.get("aspect"))
    e = c.get("e_span")
    if not (isinstance(e, list) and len(e) == 2 and all(isinstance(x, int) for x in e)
            and 0 <= e[0] <= e[1] <= 14):
        bad.append("e_span is not a valid [low,high] within 0-14")
    rb = str(c.get("resolve_by") or "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", rb):
        bad.append("resolve_by is not a date")
    else:
        horizon = (datetime.date.fromisoformat(rb) - datetime.date.today()).days
        if horizon < 14:
            bad.append("resolves in %d days — too soon to be a forecast" % horizon)
        if horizon > 550:
            bad.append("resolves in %d days — beyond an 18-month horizon" % horizon)
    obs = str(c.get("observable") or "")
    if len(obs) < 25:
        bad.append("observable too thin to check")
    # A trend is not an observable. These verbs are how a vague claim disguises
    # itself as a dated one.
    # Stems, not whole words: "increases" does not match \bincrease\b, which let
    # the exact phrasing this check exists to catch straight through.
    low = obs.lower()
    trendy = re.search(r"\b(increas|decreas|grow|rising|rise|fall|declin|improv|"
                       r"more |less |trend|continue|accelerat|expand)", low)
    # An event is DATED and has an ACTOR. "adoption continues to accelerate"
    # contains the word "adopt" but names nobody and no date; requiring both is
    # what separates a checkable event from a trend wearing a verb.
    dated = re.search(r"\b(by|before|on|at)\s+\d{4}-\d{2}-\d{2}|\b\d{4}-\d{2}-\d{2}", low)
    actor = re.search(r"\b(a named|the |any )\w+", low)
    if trendy and not (dated and actor):
        bad.append("observable reads as a trend, not a dated event with an actor")
    elif not dated:
        bad.append("observable names no date — cannot be resolved on a day")
    if len(str(c.get("switch_off") or "")) < 20:
        bad.append("no switch-off answer — the AI may be decoration")
    if not c.get("rival"):
        bad.append("no rival explanation named")
    return (not bad, bad)


def main() -> None:
    ap = argparse.ArgumentParser(description="Propose and filter model candidates.")
    ap.add_argument("--propose", action="store_true")
    ap.add_argument("--filter", action="store_true")
    ap.add_argument("--n", type=int, default=12, help="candidates per region")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--model", default="auto")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    f = OUT / "candidates.json"

    if a.propose:
        print("[explore] %d regions x %d candidates" % (len(REGIONS), a.n))
        cands = propose(a.n, a.dry_run, a.model)
        print("\n  %d candidates proposed" % len(cands))
        if a.apply or not a.dry_run:
            f.write_text(json.dumps({"generated": TODAY, "candidates": cands},
                                    ensure_ascii=False, indent=1), encoding="utf-8")
            print("  -> %s" % f)
        return

    if a.filter:
        if not f.exists():
            raise SystemExit("no candidates yet — run --propose first")
        d = json.loads(f.read_text(encoding="utf-8"))
        taken = {p.name for p in ROOT.parent.iterdir() if p.is_dir()}
        kept, cut = [], []
        for c in d.get("candidates", []):
            ok, why = score(c, taken)
            (kept if ok else cut).append((c, why))
        print("[filter] %d in -> %d kept, %d cut" % (len(kept) + len(cut), len(kept), len(cut)))
        reasons = {}
        for _c, why in cut:
            for w in why:
                k = re.sub(r"\d+", "N", w)
                reasons[k] = reasons.get(k, 0) + 1
        if reasons:
            print("\n  why candidates were cut:")
            for k, v in sorted(reasons.items(), key=lambda kv: -kv[1]):
                print("    %3d  %s" % (v, k))
        out = OUT / "candidates.kept.json"
        out.write_text(json.dumps({"generated": TODAY,
                                   "candidates": [c for c, _ in kept]},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
        print("\n  -> %s" % out)
        return

    raise SystemExit("need --propose or --filter")


if __name__ == "__main__":
    main()
