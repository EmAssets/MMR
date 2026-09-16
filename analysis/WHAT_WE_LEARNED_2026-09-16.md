# What we have actually learned

**Date:** 2026-09-16 · 40 models · 75 entities · 152 timeline rows · **0 graded predictions**

Read the last number first. Everything below is what the fleet currently
*believes*, not what it has *earned*. The first belief resolves in two weeks.

---

## 1. What the fleet believes about AI right now

Five dated claims that more than one model makes. Tagged by whether the backing
models are genuinely independent — because three of the five are not, and that
distinction is the difference between corroboration and an echo.

### A. The pacing endorsement is rhetorical and will stay untested
*Resolves 2027-03-15 · confidence 0.55–0.60 · **shared source***

Amodei published *We Must Pace the Frontier* (2026-09-12) and Anthropic
unilaterally granted permanent embedded-evaluator access. Altman and Musk
publicly endorsed the *principle* within 24 hours. The fleet predicts no rival
will either **match** the commitment or **explicitly decline** it — the
endorsement simply stays unresolved and unmentioned.

**This is the fleet's single most confident object-level position, and it is a
prediction of stasis.** Note what that means: the fleet is not predicting a race
or a pause. It predicts *nothing happens*, and that the absence of an answer is
itself the answer.

⚠️ All five backing rows come from **one brainstorm** (`bs-2026-09-16-1`), and
two of them are the *same claim double-counted* at 0.55 and 0.60. Treat this as
**one** claim from one panel, not five from a fleet.

### B. The EU AI Office inspects and files, but does not fine
*Resolves 2027-01-31 (step) / 2027-12-31 (action) · **genuinely independent***

`ai-regulation-teeth`, `ai-pressure` and `ai-option-space` reach this from
different directions and different evidence:
- `ai-option-space`: the Office holds 7 options; **4 are unevidenced** and all
  four are enforcement acts it has never performed (issue a finding, levy a
  fine, force withdrawal, grant forbearance).
- `ai-pressure`: rates it **`loaded`** — having declared intent and hired ~40
  enforcement staff, *non-enforcement is now publicly visible*. That is a stake
  installed on the regulator by its own prior act.
- `ai-regulation-teeth`: carries the dated statutory machinery (enforcement
  began 2026-08-02; first systemic-risk filings 2026-09-15).

**This is the most trustworthy convergence in the fleet** — three different
falsifier shapes, one of them reading only external stakes and explicitly banned
from modelling self-perception. The prediction: *inspection and filings within
the window, no fine.*

### C. Compute price and inference share — not capex — are the real signal
*Ongoing · **shared source (Dwarkesh/Patel), weakened by it***

Three independent corrections landed on `ai-capex-signal`'s measurement layer
this week: performance-per-watt, ~$1.65T of off-balance-sheet commitments, and
spot compute >40% above the February trough with frontier tranches at ~2x spot.
Inference share of lab compute reportedly went ~25% → ~50%+.

The learning is methodological: **reported capex measures intent, lagged and
badly.** The proposed signal chain is *footnote commitments (intent) → compute
price (scarcity) → effective FLOPs (capacity) → capability releases.*

⚠️ The corroboration is weaker than it looks: `ai-compute-concentration`,
`ai-compute-buildout` and `ai-bubble-thesis` all trace to the same two
commentators. Same news cycle read three times.

### D. Release clustering: rivals ship within ~10 weeks of each other
*Resolves **2026-10-01** — the first thing that grades*

The September 2026 cluster is documented: Claude Fable 5.1 and Mythos 5.1 (1st),
OpenAI Astra announced (1st) and released (3rd), Gemini 3.8 Flash (2nd), Muse
Spark 1.3 (2nd), DeepSeek V4.1-Flash (10th).

`lab-moves` is careful here in a way my models were not: clustering is
documented, but that any one lab *chose* to cluster is not — a shared conference
calendar explains it equally well. Its confidence is **low** and stated as such.

### E. Open weights trail the closed frontier — but the fleet disagrees on by how much

**The one clean internal contradiction, and it is gradeable:**

| Model | Claim | Resolves |
|---|---|---|
| `ai-open-weights-lag` (mine) | closed leads open by **6–12 months** | 2027-01-01 |
| `ai-capability-tracker` (imported) | the lag band is **2–8 months** | 2027-03-31 |

Same phenomenon, two models built independently four days apart, **bands that
barely overlap**. Whichever way the first measurement falls, one of them takes a
hit. This is the most valuable row in the timeline precisely because nobody
designed it.

---

## 2. Where the fleet disagrees with itself

- **Profitability — a named decider.** Campbell (2026-06-18): *"None of these
  companies are profitable, not even close."* Dylan Patel (2026-08-25):
  *"Anthropic started turning a profit in Q2."* Registered as a formal conflict
  with the decider written in advance: **audited company-wide net income, not
  segment margin.** Most likely both are right about different quantities — which
  is the finding, because it means "is AI profitable?" is not one question.
  Resolves 2026-12-31.

- **RSI framing — already retracted.** I initially read the Dwarkesh panel
  (Sept 11) as a rebuttal to Amodei's essay (Sept 12). It predates it. A
  sequencing artifact, not a debate.

- **Fleet bias toward specificity.** The challenge panel caught the fleet
  preferring Patel over Campbell because Patel gives numbers — *specificity
  mistaken for reliability*. Both have zero graded claims here.

---

## 3. What we learned that cuts against our own work

The findings worth the most are the ones that damaged our own models:

- **`ai-bubble-thesis` lost both load-bearing premises.** P1 weakened by the
  $1.65T off-balance-sheet commitments; P2 weakened by the dot-com analogue —
  assets did retain value, but *for the buyer, after the builder was wiped out*.
- **`ai-capex-signal`'s measurement layer was wrong three separate ways** (§1C).
- **`ai-option-space`'s gap metric is confounded** — and the model already knew
  (P2, consequence #4). Anthropic reads gap=0 not from self-knowledge but because
  5 of 8 options are evidenced from one CBS interview and one blog post published
  in the last three days. **The gap measures how recently someone gave an
  interview.**
- **`ai-cyber-offense-defense` is misfiled as a `tracker`.** It is a closed
  corrective loop; under `loop-delay` it would be forced to state whether effects
  are reversible inside the 6–18 month window. Its own P3 says they are not.
- **`prc-state` holds a move it cannot execute** ("encourage open-weight
  release", evidence: *none found*).
- **`sleep` was the wrong tool.** The dry run showed WOULD PIN 0 / WOULD COMPRESS
  136 — running it would have summarised away the model documents for zero gain.

---

## 4. What we learned about the instrument (the part that changes how to read §1)

**The fleet has made 2 predictions and graded 0.** Everything in §1 is
unfalsified because nothing has been tested yet, not because it survived a test.

**The confidence labels are unearned on both sides, in opposite directions:**

| | low-confidence markers | medium/high markers |
|---|---|---|
| My 32 models | **0** | 90 medium, plus high |
| The 8 imported | **26** | 0 |

Same evidence base — zero resolved predictions — and a completely inverted
epistemic posture. The imported models also mark premises `SEEDED` (a status
convention my models lack entirely) and carry `warning:` fields on DESIGNED
kinds. **The honest reading is not "they are humble and I am rash": it is that
no confidence label in this fleet is currently earned, and mine assert more than
theirs on identical grounds.**

**The evidence base is narrower than 40 models implies:**
- **37 distinct URLs** support **137 citations** — and **19 of the 37 are
  YouTube**. The same handful of podcast appearances is cited ~4x each.
- Of the **21 "observed" events, roughly 8 are commentator statements**, not
  events (Campbell, Easterly, Dwarkesh, Patel, VandeHei, Schulman, Sheehan,
  Amodei on CBS). `fleet_timeline` created `expert-claim` as a separate type to
  prevent exactly this; some leaked through. **The real event base is ~13.**
- **17 of 21 fall in the last six weeks** — that is an artifact of which media
  was fed in, not evidence that the world accelerated in August.

**The recurring error has a name.** Three times now the fleet mistook
*shared-source convergence for independent confirmation* — and I made it a fourth
time in the import report, claiming `ai-pressure` and `ai-option-space`
independently confirmed each other when both were written this month from the
same reporting. It is the failure mode of a fleet: more models reading the same
corpus produce more agreement and no more information.

**`my-predictions/MODEL.md` has an unfilled template line** — its kind parses as
`aforecaster.Startedfromthebasiccatalogue…`, so the 40-model histogram only
really parsed 39.

---

## 5. What resolves first

| Date | Claim | Source |
|---|---|---|
| **2026-10-01** | Next generation step within 10 weeks of a rival's | `ai-frontier-cadence` |
| **2026-12-31** | Patel: Anthropic profitable in Q2 (vs Campbell) | conflict, decider named |
| **2026-12-31** | No RFI-named lab withdraws a GPAI model from the EU | `ai-pressure` |
| **2027-01-01** | Every closed benchmark record matched by open weights | `ai-open-weights-lag` |
| **2027-01-31** | AI Office takes ≥1 publicly reported enforcement step | `ai-pressure` |

**In two weeks the first "learned" becomes "graded."** That is the only thing
that converts this document from a set of positions into a track record — and
until it happens, the most useful thing the fleet has produced is not a
prediction about AI. It is a list of the specific ways its own reading of AI is
structurally likely to be wrong.
