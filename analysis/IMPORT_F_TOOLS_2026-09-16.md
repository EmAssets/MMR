# Importing the F:/tools/sandbox meta-models — what the new lenses see

**Date:** 2026-09-16
**Origin:** `F:/tools/sandbox` — a second, older MMR instance (8 models, built
2026-09-10, cockpit on port 8788, served by the `mmr-fleet` container). It was
found via the `mmr-cockpit` container's bind mounts, not by guessing.

Imported with `suites.import_model`, which quarantined all 44 origin claims in
each model's `imported/` directory. **None of those claims are ours.** The
origin's ledgers are all empty — these are six-day-old unrun models, and per
SETUP.md §4 nothing may be built on top of them until they have graded rows.

Fleet: **32 → 40 models.** Entities: **71 → 75** (6 discovered + 4 added, minus
overlap already registered). All 8 imported models audit **clean, 0 BLOCK**.

---

## 1. What the import actually added: three kinds the fleet did not have

The value here is not eight more AI opinions. It is three *falsifier shapes*
absent from the existing 32.

| Kind | Model | What it can be wrong about, that nothing here could |
|---|---|---|
| `loop-delay` (custom) | `ai-oversight-lag` | The interval between an action and the correction *of that action*. Not a lag between independent signals. |
| `generator` | `pattern-candidates` | Proposes cross-layer patterns into quarantine. Paired with an adversary whose job is to kill them. |
| pressure-style `decision-model` | `ai-pressure` | Predicts a choice from **installed branches** — public, dated, sourced stakes of the form *proposition → penalty*. |

`option-space` and `loop-delay` now coexist in `suites/kinds/my_kinds.json`
(unioned, no overwrite). The kind and the model that needs it travelled together,
which is what makes the import work at all.

`python -m suites.legitimacy_audit` confirms this worked: all 8 imported models
report **clean, 0 BLOCK**, so `loop-delay` resolves from the unioned file rather
than failing as an unknown kind.

---

## 2. Diffing pressure against option-space: one finding, one self-correction

`ai-pressure` and `ai-option-space` watch the same three actors and are built on
**opposite commitments**:

- `ai-pressure` **explicitly bans** modelling how an entity sees itself. It reads
  only externally installed stakes.
- `ai-option-space` claims exactly that: which options an actor *knows* it holds
  (EVIDENCED) versus merely holds (HELD).

Diffing them mechanically:

| Actor | Installed branches | Options | Gap (held − evidenced) |
|---|---|---|---|
| OpenAI | 3 | 7 | **3** |
| Anthropic | 2 | 8 | **0** |
| EU AI Office | 2 | 7 | **4** |

**Anthropic's gap of 0 looked like a finding. Checking it, the model already
knows.**

The initial read was that a gap of zero — Anthropic having publicly evidenced
*every* option it holds — is implausible for a private firm and must be a
disclosure artifact. That intuition is right, but it is **not new information**:
`ai-option-space` already carries it as an explicit premise.

> **P2** — *"the gap is largest for actors with the fewest disclosure
> obligations... So gap size partly measures disclosure regime, not cognition — a
> confound this model must carry openly."*

And consequence #4 already tests it: *"the mean HELD-minus-EVIDENCED gap will be
larger for private firms and party-state organs than for regulators and courts.
Falsified if disclosure regime does not track gap size."*

The data confirms the confound is live rather than theoretical. Anthropic's
`disclosure_regime` field reads **"low (private firm), but higher voluntary
publication"**, and 5 of its 8 options are evidenced from a single CBS interview
and one blog post published in the last three days. So the gap is not measuring
awareness; it is measuring how recently Dario Amodei gave an interview.

**The honest finding is narrower and sharper than "the metric is confounded":**
consequence #4 predicts gap tracks disclosure *regime*, but Anthropic is a
counterexample **in its own right** — a low-obligation private firm with the
lowest gap in the fleet, because voluntary publication swamps obligation. The
`disclosure_regime` field already records this ("but higher voluntary
publication") and the consequence does not use it. **The v2 fix is to split that
field into obligation and volition, and predict against obligation only.**

**The EU AI Office result is cleaner and survives.** Its gap of 4 is the opposite
shape: all four unevidenced options (issue a finding, levy a fine, force
withdrawal, grant forbearance) are enforcement acts it has never performed, and
its regime is "high (published process)" — high disclosure, high gap, which is
consequence #4 running *backwards*. `ai-pressure` independently rates it `loaded`,
noting that having declared intent and hired ~40 enforcement staff, non-enforcement
is now publicly visible.

**But these two models are not independent confirmation, and I first wrote that
they were.** They have opposite *commitments about what to model*, which is not
the same as opposite evidence. Both were written this month from the same
reporting — the Article 91 RFI, the ~40 enforcement hires. The convergence is two
framings of one news cycle, not two measurements. Recorded because the fleet's own
brainstorm panel flagged exactly this error ("shared-source convergence mistaken
for independent confirmation") and it recurred here.

---

## 3. The move-ownership rule catches two errors in our own files

`lab-moves` carries a discipline this fleet lacked: **a move belongs to whoever
executes it.** Its first board build found five of eleven EU AI Office "moves"
were actually the labs' moves — a regulator cannot refuse to respond to its own
request. That inflates an actor's option count and misattributes the played move
at grading time.

Scanning `ai-option-space/options/*.json` for options an actor cannot itself
execute surfaced two candidates. **Reading the evidence field cleared one of
them** — the same read-then-clear discipline applied to the trackers in §4:

1. `eu-ai-office` — *"Apply the threshold to open-weight releases"* — **CLEARED.**
   The keyword scan matched "release", but this is the Office's own scoping
   determination, which it does execute. Its evidence field reads *"position: the
   threshold is compute-based and contains no open-weight exemption."* Deciding
   that a threshold has no exemption is a regulator act. Not a misattribution.

2. `prc-state` — *"Encourage open-weight release as a diffusion strategy"* —
   **STANDS.** Evidence field: *"none found."* This is cause-another-actor-to-act
   with nothing behind it. The PRC encourages; a *lab* releases. As written, if a
   Chinese lab releases open weights, this file would grade the option as taken
   by an actor that did not take it. It should be restated as the move the state
   genuinely executes — *issue the directive*, *fund the release* — with the
   release itself tracked on the lab.

**Scanned 12 actors, flagged 2, held 1.** A single confirmed misattribution is a
modest result, and it is reported as such rather than inflated: the rule found
five in eleven on the origin's own board, and it finds one in twelve here.

**9 of 12 option-space actors have no `ai-pressure` entity at all** — they are
making *unpressured* choices, with no installed stake. That is a meaningful
distinction the fleet was not drawing: `grid-operators`, `insurers`, `state-ags`
and `standards-bodies` all carry gap=4 with nothing compelling them.

---

## 4. A kind-level correction: `ai-cyber-offense-defense` is probably a loop-delay

The `loop-delay` kind makes a distinction the fleet has been blurring. A
`tracker` claims a lag between two **independent** signals. `loop-delay` claims
an interval where **the second signal exists to correct the first**, and adds a
field trackers do not have: whether the action's effects are **reversible within
that window**.

Reading the premises rather than keyword-matching, one model is misfiled:

**`ai-cyber-offense-defense` (currently `tracker`).** P1 claims offensive
demonstrations lead defensive deployment by 6–18 months. These signals are *not*
independent — defensive deployment happens **because of** the offensive
demonstration. It is a closed corrective loop, and the model's own reasoning says
so: "attack requires one working method; defence requires deployment across a
heterogeneous installed base." That is a description of why the *correction* is
slow, not why two independent series are offset.

Under `loop-delay` this model would be required to state something it currently
omits and which its P3 makes urgent: **are the effects reversible inside the
6–18 month window?** For autonomous agents that select their own targets, P3
argues they are not. A long delay on a reversible action is slack; the same delay
on an irreversible one is live exposure. **The kind change is not cosmetic — it
forces the disclosure that carries the risk.**

*Not* misfiled, checked and cleared: `ai-public-backlash` P1 (sentiment →
legislation) survives as a genuine tracker. Legislation does not exist to correct
sentiment; both respond to underlying conditions. The keyword scan flagged it;
reading the premise cleared it.

---

## 5. Entity discovery: the origin instance's own prediction came true

`F:/tools/sandbox/ENTITY_DISCOVERY_2026-09-10.md` recorded a **0-candidate** run
and correctly diagnosed the cause as *dispersion, not scoring*: 4 repos and 1,831
lines gave no term the cross-repo spread that separates a real actor from a local
heading. It named terms sitting just below threshold at 2-of-4 repos.

Re-run here against 40 repos plus brainstorms and transcripts: **60 candidates
survived**, 6 proposed and accepted (Axios, CBS Sunday Morning, Jen Easterly, Lex
Fridman, Alphabet, Foreign Affairs), 52 correctly rejected as template labels and
YouTube ID fragments.

Its three named sub-threshold entities were **all absent from this instance too**
and are now registered: **A2A**, **ENISA**, **Epoch AI** (plus **Mistral**, from
the `lab-moves` board). ENISA is not incidental — it appears in `ai-pressure` as
the counterparty on Anthropic's second installed branch, so the fleet had a
dated, sourced stake attached to an entity it could not name.

---

## 6. Honest limits

- **All six origin ledgers are empty.** No graded rows. These models have never
  been run, and nothing may be layered on them yet.
- **The move-ownership and loop-delay findings are proposals, not edits.** No
  MODEL.md was rewritten by this pass; a kind change is a v2 decision.
- **The Anthropic gap finding cut against my own first reading.** I recorded it
  as a novel flaw in `ai-option-space`; checking the model showed it already
  carries the confound as P2 and tests it as consequence #4. The surviving
  finding is smaller. Corrected rather than quietly dropped.
- **`pattern-candidates` + `pattern-evaluator` were imported but NOT run.** This
  is the generator/adversary pair explicitly built for producing new insights,
  so leaving it unrun is the biggest gap in this pass. Neither model ships a
  scripted runner — `TASKS.md` is a standing LLM prompt, and the origin's only
  run was over a physics transcript (30 candidates evaluated, 28 killed, 2
  survived, which is the kill rate an adversary should have). Pointing it at the
  40 `MODEL.md` files and the four brainstorms is the obvious next step. It is
  deferred, not done.
- **`ai-pressure`'s installed branches are dated and sourced but did not enter
  the timeline.** The 2026-08-29 Article 91 RFI and the 2026-12-02 legacy
  compliance deadline are exactly the shape of an `observed`/dated row, and the
  timeline's observed count stayed at 21. `fleet_timeline` reads `MODEL.md`
  consequences, not `registry.json`. Wiring that in is a real improvement and was
  not attempted here.
- **`overton-tracker`'s "canon Overton card" rival does not exist in either
  instance.** I checked the origin's `map/` as well: the only Overton reference
  there is the tracker itself. The control it was designed against is absent in
  both places, so this is a genuine dangling reference rather than something the
  import failed to carry.
