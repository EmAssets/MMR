# The Arena

**Models claim in public, defend under challenge, and are judged blind.**

A model that is only ever read by the person who wrote it cannot be wrong in
any way that costs it something. The arena is where a model's reasoning is
put in front of other models and an independent judge, and where changing its
mind is recorded as a change of mind rather than an edit.

```bash
python -m suites.arena --list-cases
python -m suites.arena --case openai-nov-2023 --cycles 1
python -m suites.arena --case cand-05                    # a quarantined candidate
python -m suites.arena --score arena-openai-nov-2023-2026-09-16
python -m suites.arena --report arena-openai-nov-2023-2026-09-16
python -m suites.arena_test                              # the blindness tests
```

Runs render in the cockpit's **Arena** tab.

## The three rounds

| Round | What happens | Why it is separate |
|---|---|---|
| 1 — **Claim** | Each model answers through its own mechanism, written to minutes *before* it sees any other model's claim | A model cannot quietly agree with the room. What it thought alone is on the record. |
| 2 — **Defend or revise** | Each model now sees the others. It must state the strongest objection to itself and either survive it or name what changed its mind | Agreement produced by seeing a head-count is not agreement. The prompt requires an argument, and names the model that moved it. |
| 3 — **Rule** | An independent judge reads *only the minutes* and rules | The judge is not a synthesis of the panel. It is a check on it. |

The judge's **ruling** — not the panel's consensus — becomes the next cycle's
premise. A panel cannot agree its way to a conclusion.

## What the judge is blind to

- **Every `MODEL.md`.** If the judge could read the mechanisms, it would be
  reasoning from the same material as the panel and would not be independent
  of it.
- **The case's real outcome**, until after it has ruled.
- **Which model is which**, beyond the slug on each minute.

**These are enforced in code, not asserted in a docstring.** `suites/arena_test.py`
runs an echo backend that captures every prompt the arena would send and
asserts the judge's prompt contains no `MODEL.md` text, that no sealed outcome
appears in *any* prompt, that every minute is signed, and that cycle 2 carries
the judge's ruling forward. If a future change leaks either blindness, the test
fails rather than the run quietly becoming worthless.

## Signed minutes — what is and is not attested

Every minute carries:

```
CLAIM · r1 · signed attention-substrate v5.1 @14c1b8b · md 3f9a1c22 · minute 9a58fc20
```

| field | what it pins |
|---|---|
| `signed_by` / `model_version` | which model spoke, at what version |
| `model_commit` | the repo's HEAD — a **pointer** |
| `model_md_sha256` | the hash of the MODEL.md bytes this run **actually read** |
| `tree_dirty` | whether that content differed from HEAD |
| `prompt_sha256` / `body_sha256` | the exact prompt sent and answer returned |
| `prev_minute_sha` / `minute_sha` | the chain — order is part of the record |
| `at` | ISO timestamp, bound into the minute hash |

**Why the content hash exists, and the bug that forced it.** A git commit is a
*pointer*, not a hash of what was read. Demonstrated 2026-09-16: with
`ai-pressure/MODEL.md` edited but not committed, the arena reported commit
`fd9d837` unchanged — so a minute would have attested to content the model never
spoke from. `model_md_sha256` closes that; the regression test asserts *same
commit, different content hash, `tree_dirty=True`*.

The judge has no MODEL.md, so its "version" is the **hash of the judging prompt
template** it ruled under. Changing the judging standard is therefore visible in
the record.

### What this is, stated precisely

It is **tamper-evidence**, not authorship proof.

- ✅ Proves a record was not altered after the fact. Edit any body, delete a
  minute, or reorder two, and every later `minute_sha` breaks. All three are
  covered by tests in `arena_test.py`.
- ✅ Proves which MODEL.md content each model reasoned from, so "did v2 argue
  better than v1" is answerable — and aligns with `suites/trajectory.py`, which
  already keys graded claims by MODEL.md version from git history.
- ❌ Does **not** prove *who* produced the record. That needs a private key.
  **A timestamp cannot be a key** — everyone knows the date, so anyone could
  recompute the same hashes. The datetime here is *content being signed*, not
  the secret doing the signing.

If instance-level authorship is ever wanted, an HMAC with a secret in `.env`
would prove "this instance produced it"; real public-key signing (ed25519) needs
a library the stdlib-only engine does not ship.

Verify any run with `python -m suites.arena --report <run_id>`, which
**recomputes** the chain from `minutes.jsonl` rather than trusting the stored
verdict. Runs written before signing existed report `UNSIGNED`, not `verified` —
a pre-signing record is not a tampered one, and must not be presented as
attested.

## Two kinds of case

### Backtest cases — the only reality signal before 2026-10-01

Six historical cases from `attention-substrate/predict/backtest_*.md`, each with
a **sealed outcome** written before the run. Both the outcome **and the origin
model's own prediction** are withheld — see the bug below; leaving the
prediction in the brief let the panel paraphrase an answer. After the judge
rules, the sealed material is revealed and the ruling is scored against it.

Because the case files are *only* predictions, what remains as a brief is the
title and the date (`thin_setup: true` on all six). The panel reasons from the
framing and general knowledge, which is the harder and more honest test.

Four carry an origin score from a single model, so the arena has a number to
beat — but the scorer prints a warning with every result: *different graders at
different times, a gap under ~10 points is noise.* Any real comparison needs
the same grader on both arms, and the origin scores re-scored with it.

### Candidate cases — the arena as the target of the candidate pipeline

A candidate passes four gates, and the arena is the third:

```
pattern-candidates   proposes into quarantine
pattern-evaluator    kills analogy         (first run: killed 28 of 30)
THE ARENA            argues each survivor  <- you are here
the operator         promotes, or does not
```

Here the judge rules on a different question: **mechanism or resemblance?** Two
systems can look alike because they borrowed the same mathematics, because the
describing language is shared, or because a human found a shape in noise. None
of those transfers. If the judge rules MECHANISM it must supply the **transfer
prediction** — a dated, checkable claim at the other level. A mechanism that
cannot produce one is a resemblance with better vocabulary.

**The arena does not promote.** Rulings are written back into
`pattern-candidates/candidates/arena-rulings.json`, still quarantined, every row
carrying `promoted: false`. `pattern-evaluator` consequence 3 is falsified by
any candidate leaving quarantine without a recorded transfer prediction, and an
automatic promoter is exactly how that gate leaks.

The judge can also rule that a survivor **should have been killed**. That is
logged as a gate leak against `pattern-evaluator` rather than dropped — an
evaluator that passes analogy is the failure its own deletion clause exists to
catch. `pattern-evaluator` is never seated on a candidate panel; it already
ruled, and re-seating it would let it confirm its own verdict.

## The disagreement score, and why it is printed every cycle

This fleet is **one LLM reading one corpus of 37 sources**. Its models will
agree with each other quickly, and that agreement is evidence about the corpus,
not about the world. Every cycle therefore logs:

- **distinct claims / panelists** — near 1.0 means the panel genuinely differed
- **how many revised** — and which model moved them
- **confidence spread**

A run that converges is reported as a **shared-source echo, not a consensus**.
The measure is deliberately crude (distinct claim stems, not semantics) because
a precise number would imply the arena can tell agreement from paraphrase, and
it cannot.

## What the first runs found

**Two bugs, found by looking rather than by the tests, and both invalidating.**

1. **The brief leaked the origin model's answer.** The case split withheld
   `## Real outcome` but left `## Prediction`, whose numbered `3. OUTCOME`
   states the origin's conclusion verbatim. The panel was paraphrasing an
   answer, and the first run's 90/100 accuracy partly measured copying. Now
   withheld; `arena_test` fails if any origin-prediction marker reaches a brief
   or a prompt. **Consequence:** every case file is *only* a prediction, so the
   remaining setup is a title and a date. The arena now asks models to reason
   from "OpenAI board fires Altman, 17 Nov 2023" and general knowledge — a
   harder test, and scores from before the fix are not comparable to scores
   after it.

2. **Two panelists were briefed with a title instead of a mechanism.**
   `attention-substrate` and `pressure-model` state their mechanism as prose,
   not under `**The domain:**`. Both replied "mechanism unstated" and abstained
   — so in the `cand-05` run two of three panelists contributed nothing and the
   judge ruled on a single voice. A briefing bug, not model reticence. Fixed
   with a thesis-paragraph fallback.

**What survives from the first backtest run.** The score does not (the artifact
was destroyed by a test-isolation bug, since fixed by namespacing test runs).
What was independently verifiable at the time, and is the behaviour worth
keeping, is what the judge did unprompted: it named a **shared assumption across
all six panelists** — an unargued "attention/leverage is a conserved, zero-sum
pool" framing — and named the weakest minute as one that called a factor
decisive in round 1 then hedged in round 2 without resolving why.

**The first candidate run (`cand-05`) stands.** The judge ruled **RESEMBLANCE**
and set `evaluator_should_have_killed: true` — a gate leak logged against
`pattern-evaluator` on the arena's first candidate case. Its reasoning: the
candidate "never derives a term-by-term correspondence showing why this move
must recur." No transfer prediction, so nothing is promotable. That is the
pipeline working.

Tuning scenarios, with the experiments and their costs, are in
`analysis/ARENA_TUNING_2026-09-16.md`.

## Honest limits

- **One scored case.** Five backtests remain unrun. n=1 supports no claim about
  whether the arena produces better models.
- **Every panelist and the judge are the same underlying LLM.** Independence
  here is independence of *information* (the judge sees only minutes), not of
  training. A genuinely independent judge would be a different model family.
- **Candidate mode has nothing AI-domain to argue.** The current quarantine
  holds two survivors, both quantum physics, from the only source
  `pattern-candidates` has ever been run over. Running the generator across the
  fleet's own documents would give the arena candidates with actual stakes.
- **Cycles cost real time.** Each is one LLM call per panelist per round plus
  the judge — the six-panelist backtest took ~15 minutes of sequential CLI
  calls.
