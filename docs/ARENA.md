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

## Signed minutes

Every minute carries the speaking model's slug, its version line, and its repo
commit at the moment it spoke:

```
DEFENCE · r2 · signed ai-lab-revealed-priorities v1 @d95eb3b
```

So "the model changed its mind" and "the model was edited" can never be
confused, and a claim is attributable to a specific state of a specific model.

## Two kinds of case

### Backtest cases — the only reality signal before 2026-10-01

Six historical cases from `attention-substrate/predict/backtest_*.md`, each with
a **sealed outcome** written before the run. The brief is split so the outcome
never travels with it. After the judge rules, the outcome is revealed and the
ruling is scored against it.

Four carry an origin score from a single model, so the arena has a number to
beat — but the scorer prints a warning with every result: *different graders at
different times, a gap under ~10 points is noise.*

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

## What the first run found

`openai-nov-2023`, six panelists, 13 signed minutes, one cycle.

The ruling scored **90 accuracy / 85 reasoning** against the sealed outcome; the
origin single model scored 85/90. Inside the noise band — **comparable, not
better**, and one case proves nothing either way.

More useful than the score, the judge did two things unprompted:

- **Named a shared assumption across all six panelists:** an unargued
  "attention/leverage is a conserved, zero-sum pool" framing that no minute
  justified against the alternative of treating board legitimacy and employee
  leverage as separate, non-fungible resources.
- **Named the weakest minute and why:** a panelist called Microsoft's payroll
  floor decisive in round 1, then reversed to a hedge in round 2 "without
  resolving why the floor it called decisive didn't in fact decide the outcome."

Disagreement was **5/6 distinct (ratio 0.83)** — the panel did not converge.

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
