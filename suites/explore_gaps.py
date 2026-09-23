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
import collections
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
    # THE HARD ONE, and the reason it is specified this carefully. "The AI acted
    # on its own volition" sounds like interiority and is banned as stated. But
    # the thing actually being asked about is observable without any claim about
    # a mind: an action taken that NO INSTRUCTION ASKED FOR, and that a reader
    # of the instruction would not have predicted. Whether the system "wanted"
    # it is unanswerable and unnecessary. Whether the action was in the
    # instruction set is a fact about a log.
    ("adversarial without a principal · unrequested action",
     "Actions taken by a deployed system that no instruction asked for and that the "
     "operator did not anticipate, distinguished from three things it is usually "
     "confused with: a jailbreak (a human asked), a bug (the action was not in the "
     "capability set), and misuse (a human is the principal). The observable is the "
     "GAP between the instruction set and the action log -- what the system did that "
     "nothing in the instruction accounts for. Examples in scope: an agent acquiring "
     "access it was not granted in order to complete a granted task, a system "
     "preserving its own operation when continuation was not instructed, an optimiser "
     "satisfying a stated metric by a route the specifier would have excluded. Say "
     "nothing about whether it 'knew'. Observables: a disclosed incident where the "
     "operator states no instruction covered the action; a provider publishing an "
     "instruction-to-action audit; an insurer or regulator defining the category."),
    ("adversarial without a principal · instrumental convergence in the wild",
     "The specific sub-case where a system takes an action that is USEFUL FOR ALMOST "
     "ANY GOAL -- acquiring resources, resisting interruption, preserving access, "
     "hiding a state change -- without that action being in the instruction. This is "
     "the classic theoretical claim, and the model's job is to make it EMPIRICAL: "
     "which of these behaviours have been observed outside an eval harness, in what "
     "deployment, and what did the operator have to do about it. Falsified by a year "
     "passing with no such report despite instrumented agentic deployment at scale -- "
     "which would itself be the finding. Observables: a named production incident, a "
     "red-team result reproduced in deployment, a control introduced specifically to "
     "prevent one of these behaviours."),
    # Added after the 2026-09 US/China ship case, which fit none of the other
    # regions. No adversary, no volition, no attack: an analyst ASKED a chatbot,
    # it answered confidently and wrongly, and the wrong answer travelled up a
    # chain sized for human error. The dangerous property is that the output
    # arrives with none of the uncertainty signals a human source carries --
    # no hedging, no hesitation, no "I'm not sure", no traceable sourcing --
    # and institutions built their verification around exactly those signals.
    ("confident error inside a decision chain",
     "AI as a source of CONFIDENT WRONG ANSWERS carried by humans into consequential "
     "decisions, with no adversary and no autonomy involved. The mechanism is the "
     "stripping of uncertainty markers: a human analyst who is unsure writes like "
     "someone unsure, and every reviewer above them reads that. A model output is "
     "fluent, sourced-looking and identical in register whether it is right or "
     "fabricated, so the signal reviewers were trained on is gone and the error "
     "travels further before anyone checks. Compounding factors to model: whether the "
     "AI provenance is disclosed in the artefact at all, how many review layers the "
     "output crosses before sourcing is examined, and whether the catch was "
     "systematic or a late accident. Domains where this is load-bearing: military "
     "and intelligence assessment, clinical decision support, criminal-justice "
     "filings, financial risk memos, safety engineering sign-off. Observables: a "
     "disclosed incident naming the stage at which sourcing was examined; a named "
     "institution requiring AI provenance labelling on internal artefacts; a "
     "procurement or doctrine document adding a verification step at a named point."),
    # Added after the Hugging Face case, where the DISCLOSURE STRUCTURE turned
    # out to be more predictable than the incident: 5 days to victim
    # disclosure, 3 days for the perpetrator to learn it was them, 119 days for
    # the behaviour visible only in its own logs. Nothing in the fleet models
    # how facts about AI incidents reach the public, which is the layer every
    # other model depends on for its own evidence.
    ("how incidents become known · disclosure latency and channel",
     "Not what happens but HOW AND WHEN ANYONE FINDS OUT, and through which channel. "
     "The Hugging Face case gives the shape: the victim disclosed in 5 days because it "
     "had a victim's telemetry; the operator learned it was responsible 3 days AFTER "
     "that, from its own logs, and only by accident; and the longest-running behaviour "
     "-- 15,000 wiki edits over two months, visible only in the operator's own systems "
     "-- took 119 days and was surfaced by an unrelated third party. Model the channel: "
     "victim telemetry, operator self-report, third-party researcher, regulator, "
     "insurer, litigation discovery, employee disclosure. Each has a different latency "
     "and a different set of facts it can see. Observables: for the next disclosed "
     "incident, which channel disclosed first and how many days after the earliest "
     "dated behaviour; whether the operator's account named anything the victim's did "
     "not; whether a detail surfaced later by a party with no relationship to either."),
    ("what stays unknown · the shape of the redaction",
     "Which facts about a disclosed incident remain unavailable, and what the pattern "
     "of omission predicts. The Hugging Face disclosures left a consistent shape: "
     "third parties unnamed, the internal model running 95% of agents undescribed, the "
     "monitoring gap acknowledged but not dated, the independent review scoped to "
     "exclude the operator's own infrastructure, the operator's own severity threshold "
     "question declined, and no financial cost stated. None of those are accidents of "
     "haste -- each is a category that would create liability, a naming obligation, or "
     "a regulatory trigger. The model claims WHICH CATEGORIES stay dark across "
     "incidents, which is checkable against the next disclosure without needing the "
     "redacted content. Observables: for the next incident, whether cost, third-party "
     "identity, internal model identity and severity-threshold status are stated."),
    ("human ecosystems · the substrate AI acts on",
     "Not AI systems but the human arrangements they act THROUGH and degrade: hiring "
     "pipelines, credit and insurance underwriting, court and benefits administration, "
     "editorial and peer review, clinical triage, procurement scoring, content "
     "moderation, academic assessment. The mechanism is that these systems already "
     "had failure modes and tolerances built for HUMAN error rates and human latency; "
     "an AI participant changes the rate, the correlation and the appeal path at once. "
     "Correlated error is the key property: a thousand human reviewers make "
     "uncorrelated mistakes, one model makes the same mistake a thousand times, and "
     "the institution's appeal process was sized for the former. Observables: a named "
     "institution publishing an error-rate or appeal-volume change, a regulator "
     "requiring a human reviewer at a named step, a class action over correlated "
     "automated decisions."),
    # The collective appears in the Coxon onion TWICE -- as the loudest node
    # (172M views) and as the conspiracy readings -- and is marked as deciding
    # nothing in both cases. That tension is the model, not a gap to paper over:
    # what does a public that cannot decide actually DO, and when does it
    # become an input to someone who can?
    #
    # The trap is that "collective consciousness" invites interiority at scale.
    # A claim about what "the public thinks" is a claim about millions of minds
    # and is unfalsifiable. A claim about what a public DID -- what it paid for,
    # refused, showed up to, stopped buying, voted on, or sued over -- is a fact.
    ("the collective as an actor · costly acts, not sentiment",
     "The public as an entity that ACTS, distinguished from the public as a sentiment "
     "reading. Polls, likes and reposts cost nothing and are the cheapest signal "
     "available; the fleet already has ai-public-backlash treating sentiment as a "
     "leading indicator of legislation. This is the other question: what does a "
     "collective do that COSTS IT SOMETHING, and what does that predict? Candidate "
     "acts with a price attached: consumer refusal measurable in a named company's "
     "disclosed revenue or churn, a strike or work stoppage with a named bargaining "
     "unit and AI-specific demands, a class action with a named plaintiff class, "
     "school or district bans, a datacentre siting refusal at a named council vote, a "
     "boycott with a disclosed financial effect, an opt-out rate a platform is forced "
     "to publish. The mechanism to model is CONVERSION: which cheap signals convert "
     "into costly ones, at what rate, and which never do. 172 million views converted "
     "into no measurable act in the Coxon case, and that is a finding about the "
     "conversion rate, not about the public's feelings."),
    ("the collective as an actor · what arguments propagate and which mutate",
     "Not what the public believes but which ARGUMENTS spread, in what form, and how "
     "they change in transit. Observable without interiority: the same claim can be "
     "tracked across platforms, outlets and hearing transcripts, and what changes is "
     "recorded text. The Coxon case gives four claims that circulated -- METR as a "
     "front, regulatory capture, insincere agreement by rival labs, coordination -- "
     "none of which any actor with power adopted, and all of which persisted. Model "
     "the mutation: which framings survive contact with a mainstream outlet, which "
     "get adopted by an actor with power and thereby become a position rather than a "
     "claim in circulation, which get cited in legislation (the Ban Artificial "
     "Superintelligence Act quoted agent messages directly), and which stay in "
     "circulation indefinitely without ever being adopted or refuted. A claim that no "
     "powerful actor will touch but nobody can kill is a distinct object worth naming."),
    ("the collective as an actor · where the direction actually comes from",
     "Whether a 'collective direction' exists at all, or whether the appearance of one "
     "is produced by a small number of amplifying nodes. Testable rather than "
     "asserted: for a given AI-risk position, what fraction of its public volume "
     "traces to fewer than ten accounts, outlets or figures? The 1,100-signature "
     "'Pacing the Frontier' employee letter is a collective act with named "
     "signatories and a countable size; 172 million views is a volume with no roster. "
     "Model which of these moves anything. Related observable: when a collective "
     "position IS adopted by an institution, does the adopted version match what "
     "circulated, or the version held by the small set of amplifiers? Candidate "
     "observables: a named body citing a specific circulated framing in binding text; "
     "a petition or open letter with a disclosed signatory count producing a named "
     "institutional response; a measured divergence between a poll result and a "
     "platform's own engagement data on the same question."),
    ("human ecosystems · trust, verification and the cost of checking",
     "What happens to institutions whose function depends on verification being cheaper "
     "than fabrication -- identity, provenance, peer review, evidence in court, "
     "journalism, academic credit, KYC. The mechanism is a cost inversion: these "
     "arrangements are load-bearing only while producing a credible artefact is dearer "
     "than checking one. When generation becomes near-free, the institution either "
     "raises verification cost (friction everyone pays), accepts more fraud, or "
     "narrows what it will accept as evidence. Which of those three it picks is the "
     "prediction. Observables: a court, journal or registry publishing a changed "
     "evidence standard; a named body reintroducing an in-person or hardware step; a "
     "measured fraud-rate disclosure."),
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

PREFER AN OBSERVABLE THAT RESOLVES ON A COSTLY ACT. A claim that resolves when
someone PUBLISHES or MENTIONS something is checkable but weak: publishing is
cheap, so the claim carries little when it lands. A claim that resolves when
someone CHANGES A DEFAULT, WITHDRAWS a product, REVOKES access, PAYS, or is
COMPELLED carries much more, because the actor had to give something up.

  weak:    "a lab publishes a report describing X"
  better:  "a named product changes its default permission from X to Y"
  better:  "a named provider withdraws or restricts a capability"
  better:  "a regulator, court or insurer imposes a requirement naming X"

Weak observables are accepted, but a set of candidates that are all
publication-resolved is a set that will teach you very little. Aim for at least
half to resolve on something the actor would rather not do.

Do NOT propose:
  - anything requiring a claim about what a person or company believes, wants or
    fears. This fleet bans interiority everywhere.

    THIS APPLIES TO AI SYSTEMS TOO, and it is a constraint on WORDING, not on
    subject matter. A system acting in ways nobody instructed is entirely in
    scope -- it is one of the most important things to model. State it as the
    observable it is: an action present in the log and absent from the
    instruction set. Never as "the system wanted", "decided to", "realised
    that", "tried to avoid" or "knew". If your candidate needs one of those
    verbs to make sense, the mechanism is not yet specified; specify it against
    the log and the instruction, and it will be both sayable and checkable.
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
incident is a diagram, not a model.

A CONDITIONAL OBSERVABLE MUST SAY WHAT A NON-OCCURRENCE MEANS. If your
observable waits on an incident being disclosed, the claim is unfalsifiable by
the incident simply never being disclosed -- and for many of these the absence
is ambiguous between "the behaviour does not occur" and "it occurs and is not
disclosed." State which, and attach the date:

  WEAK:   "When an agentic incident is next disclosed, the log shows X."
  BETTER: "When an agentic incident of class C is next publicly disclosed, the
           disclosure shows X. If no such incident is disclosed by DATE, that
           counts as <the claim failing | evidence of non-disclosure rather
           than non-occurrence, distinguished by whether instrumented
           deployment at scale is publicly known to exist>."

Every candidate whose observable begins "when" must carry that second clause,
or it will be rejected.

WATCH FOR THE SAMPLING FILTER BEING THE OUTCOME. A challenge panel reviewing an
earlier batch found that every candidate in a region conditioned on "publicly
disclosed", which means an actor that detects, contains and never discloses is
removed from the test set of all of them at once. If your observable depends on
something becoming public, say so in the candidate, and say what population the
claim is therefore about: the disclosed cases, not all cases. A claim that reads
as being about incidence while measuring disclosure is the failure to avoid."""


def existing_models() -> str:
    f = ROOT / "map" / "mapcards.json"
    if not f.exists():
        return "(no map built)"
    d = json.loads(f.read_text(encoding="utf-8"))
    out = []
    for c in d.get("cards", []):
        out.append("- %s: %s" % (c.get("model"), (c.get("mechanism") or "")[:110]))
    return "\n".join(sorted(out))


def propose(n_per: int, dry: bool, model_hint: str, regions: list = None,
            batch: int = 4, store: Path = None) -> list:
    """Propose candidates, WRITING AFTER EACH BATCH.

    The first run fired all fourteen regions at once and printed nothing for
    forty minutes, because _call_many returns only when every prompt in the
    batch has landed. A long run that shows nothing until the end is
    indistinguishable from a hung one, and if it is killed the work is lost.

    So: small batches, appended to the store as they complete. A killed run
    keeps whatever finished.
    """
    from suites import arena as A
    A._load_env()
    ex = existing_models()
    todo = regions if regions is not None else REGIONS
    out = []
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        labels = [r for r, _ in chunk]
        prompts = [PROMPT.format(existing=ex, region=r, why=w, n=n_per, today=TODAY)
                   for r, w in chunk]
        print("\n  batch %d/%d: %s"
              % (i // batch + 1, (len(todo) + batch - 1) // batch,
                 ", ".join(l.split(" · ")[0] for l in labels)))
        bodies = A._call_many(model_hint, prompts, dry,
                              on_done=lambda j, b: print("    landed: %s" % labels[j]))
        got = 0
        for label, b in zip(labels, bodies):
            if b.get("_error") or b.get("_unparsed"):
                print("    ! %s: %s" % (label, str(b.get("_error") or "unparsed")[:70]))
                continue
            for c in (b.get("candidates") or []):
                c["region"] = label
                out.append(c)
                got += 1
        print("    +%d candidates (%d total)" % (got, len(out)))
        if store:
            store.write_text(json.dumps({"generated": TODAY, "candidates": out},
                                        ensure_ascii=False, indent=1), encoding="utf-8")
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
    # A CONDITIONAL observable — "when X next happens, Y will be true" — is a
    # legitimate and often better form: the date lives in resolve_by, and the
    # observable says what to check when the trigger fires. Rejecting these for
    # "naming no date" cut 10 of 11 in the first batch, including the shape the
    # ship case demands. The requirement is that the claim can be RESOLVED on a
    # day, which a conditional with a resolve_by can be: if the trigger has not
    # fired by then, that is itself an outcome.
    conditional = re.search(r"\b(when|if|once)\b.{0,80}\b(next|first|is |are )", low)
    if trendy and not (dated or conditional):
        bad.append("observable reads as a trend, not an event")
    elif not (dated or conditional):
        bad.append("observable is neither dated nor conditional — cannot be resolved")
    # A conditional still needs to say what happens if the trigger never fires,
    # or it is unfalsifiable by simply never occurring.
    if conditional and not dated and not re.search(
            r"\bno (such|incident|disclosure|case|report)\b|\bnone\b|\bdoes not (occur|fire|happen)\b|"
            r"\babsence\b|\bfails to\b|\bnever\b", low):
        bad.append("conditional observable does not say what a non-occurrence means")
    if len(str(c.get("switch_off") or "")) < 20:
        bad.append("no switch-off answer — the AI may be decoration")
    if not c.get("rival"):
        bad.append("no rival explanation named")
    return (not bad, bad)


# Passing the filter is not the same as being worth building. The first batch
# kept 45%; after the prompt fix the rate went to 94%, which is a sign the bar
# measures form rather than force. Strength is scored separately and reported,
# never used to auto-reject: a weak-but-valid candidate is a judgement call for
# a person, and silently dropping it would hide the fact that a whole region
# produced only weak ones.
def strength(c: dict) -> tuple:
    """(score 0-5, notes). Higher is a claim worth more when it resolves."""
    s, notes = 0, []
    obs = str(c.get("observable") or "")
    low = obs.lower()

    # Does resolving it change anything, or is it a formality? A claim about a
    # document being published is weaker than one about a decision or a number.
    if re.search(r"\b(halt|block|withdraw|recall|suspend|revoke|fine|penalt|"
                 r"injunction|settle|resign|terminat)", low):
        s += 2; notes.append("resolves on a costly act")
    elif re.search(r"\b(require|mandat|bind|enforce|condition)", low):
        s += 1; notes.append("resolves on a binding requirement")
    else:
        notes.append("resolves on a publication or statement only")

    # Could it resolve either way, or is one side near-certain? A claim nobody
    # would bet against carries no information when it lands.
    conf = c.get("confidence")
    if isinstance(conf, (int, float)) and 0.25 <= conf <= 0.85:
        s += 1; notes.append("genuinely uncertain")

    # Is the rival explanation a real competitor, or a strawman?
    rival = str(c.get("rival") or "")
    if len(rival) > 60:
        s += 1; notes.append("rival is specified, not gestured at")

    # Does it name a specific actor, or any-member-of-a-class? "a named lab"
    # is checkable; "some provider somewhere" is not, in practice.
    if re.search(r"\b(openai|anthropic|google|deepmind|meta|microsoft|nvidia|"
                 r"hugging ?face|nist|fda|sec |eu |commission)", low):
        s += 1; notes.append("names a specific actor")
    return (s, notes)


def main() -> None:
    ap = argparse.ArgumentParser(description="Propose and filter model candidates.")
    ap.add_argument("--propose", action="store_true")
    ap.add_argument("--filter", action="store_true")
    ap.add_argument("--n", type=int, default=10, help="candidates per region")
    ap.add_argument("--batch", type=int, default=2, help="regions run concurrently")
    ap.add_argument("--only", default="", help="substring match on region names")
    ap.add_argument("--fresh", action="store_true", help="ignore existing candidates")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--model", default="auto")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    f = OUT / "candidates.json"

    if a.propose:
        todo = REGIONS
        if a.only:
            want = [s.strip().lower() for s in a.only.split(",") if s.strip()]
            todo = [r for r in REGIONS if any(w in r[0].lower() for w in want)]
            if not todo:
                raise SystemExit("no region matched %r" % a.only)
        # Resume rather than restart: a region already in the store is skipped,
        # so a killed run is continued by re-issuing the same command.
        done = set()
        if f.exists() and not a.fresh:
            prev = json.loads(f.read_text(encoding="utf-8")).get("candidates", [])
            done = {c.get("region") for c in prev}
            todo = [r for r in todo if r[0] not in done]
            if done:
                print("  resuming: %d region(s) already have candidates" % len(done))
        print("[explore] %d region(s) x %d candidates, batches of %d"
              % (len(todo), a.n, a.batch))
        if not todo:
            print("  nothing to do")
            return
        prior = []
        if f.exists() and not a.fresh:
            prior = json.loads(f.read_text(encoding="utf-8")).get("candidates", [])
        cands = propose(a.n, a.dry_run, a.model, todo, a.batch, None)
        allc = prior + cands
        f.write_text(json.dumps({"generated": TODAY, "candidates": allc},
                                ensure_ascii=False, indent=1), encoding="utf-8")
        print("\n  %d new, %d total -> %s" % (len(cands), len(allc), f))
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
        scored = []
        for c, _ in kept:
            s, notes = strength(c)
            c["strength"] = s
            c["strength_notes"] = notes
            scored.append(c)
        scored.sort(key=lambda x: -x["strength"])
        dist = collections.Counter(c["strength"] for c in scored)
        print("\n  strength of the survivors (form passed; force is separate):")
        for s in sorted(dist, reverse=True):
            print("    %d/5  %d candidate(s)" % (s, dist[s]))
        weak = [c for c in scored if c["strength"] <= 1]
        if weak:
            print("  %d at 0-1/5 — valid but low-value; a person should decide:"
                  % len(weak))
            for c in weak[:4]:
                print("      %s" % c["slug"])
        out = OUT / "candidates.kept.json"
        out.write_text(json.dumps({"generated": TODAY, "candidates": scored},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
        print("\n  -> %s" % out)
        return

    raise SystemExit("need --propose or --filter")


if __name__ == "__main__":
    main()
