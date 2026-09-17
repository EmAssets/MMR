# Tuning the Arena for accuracy — scenarios, tests, and two bugs found on the way

**Date:** 2026-09-16

**What can be tuned against, honestly.** "Most accurate outcomes" needs ground
truth, and the AI-domain fleet has none before 2026-10-01. The six backtests in
`attention-substrate/predict/` are the only cases with a sealed outcome, so they
are the whole test bed: **6 cases, 4 with an origin score.** Everything below is
a designed experiment on those six. Nothing here is a tuned arena — it is a
ranked list of what to vary, what each test would show, and what it costs.

---

## 0. Two bugs found before any tuning was possible

Both invalidate earlier results, and both are fixed with regression tests.

### The brief leaked the origin model's answer

`backtest_cases()` split the case file on `## Real outcome` and treated
everything before it as setup. But that "setup" included the origin's
`## Prediction` section, which ends with a numbered **`3. OUTCOME`** stating its
conclusion verbatim — *"Sam Altman is formally rehired as CEO of OpenAI..."*

**So the panel was reading an answer and paraphrasing it.** The first run's
90/100 accuracy score partly measured copying. The code comment claimed the
prediction was stripped; it never was.

Fixed: everything from `## Prediction` onward now travels with the sealed
material. `arena_test` fails if any of the five origin-prediction markers
appears in any brief or live prompt.

**A consequence worth stating:** with the origin's prediction withheld, every
one of the six case files is *only* a prediction — so the remaining setup is a
title and a date (`thin_setup: true` on all six). The arena now asks models to
reason from "OpenAI board fires Altman, 17 Nov 2023" and general knowledge.
That is a harder and more honest test, and any score after this point is not
comparable to the score before it.

### Two panelists were briefed with a title instead of a mechanism

`mechanism()` read `**The domain:**`, which `attention-substrate` and
`pressure-model` do not have — they state their mechanism as prose under a
thesis heading. Both were handed only their title, correctly replied *"mechanism
unstated"*, and abstained.

In the `cand-05` run **two of three panelists contributed nothing and the judge
ruled on a single voice.** That was a briefing bug, not model reticence. Fixed
with a thesis-paragraph fallback; both now brief with their real mechanism.

---

## The scenarios, ranked by expected effect per unit of cost

### 1. Grip filter — drop or down-weight panelists with no grip
**Knob:** in round 2, exclude `grip: "none"` minutes from the board; optionally
weight the judge's view of each minute by its declared grip.

**Why it should matter:** the arena already collects `grip` and then ignores it.
`cand-05` is the proof — a panel of three where two abstained produced a ruling
that read as unanimous. A model with no grip does not add a perspective, it adds
a vote.

**Test:** `openai-nov-2023`, panel of 6 vs panel of 3 (the three the judge named
strongest), one cycle each, same scorer.
**Cost:** ~25 min, 2 runs.
**Either way:** if the small panel scores the same or better, panel size is
noise and *grip* is the variable — which also cuts cost per run. If the large
panel wins, breadth is doing real work and the grip filter should only
down-weight, never drop.

### 2. One grader for every arm — the confound behind every other comparison
**Knob:** none. This is a measurement fix, not a tuning knob.

The first comparison (arena 90/85 vs origin 85/90) used **two different graders
at two different times**. No tuning claim survives that. Before any arm is
compared to any other, the same `--score` prompt must grade both, and the origin
backtests must be **re-scored with it** so "origin 85" and "arena 90" sit on one
scale.

**Cost:** one call per case (~6 calls total). **Do this first** — without it,
every scenario below produces an uninterpretable number.

### 3. Cycle count — and a prediction registered before running
**Knob:** `--cycles 1` vs `2` vs `3`.

**Registered prediction, written before the experiment:** on a *backtest*,
cycle 2 scores **≤** cycle 1, and `distinct_ratio` falls. The reason: the cycle-2
premise is the judge's own ruling, which carries information about the ruling,
not about the world. More cycles should produce convergence on the judge's
framing rather than accuracy.

**Falsified by:** cycle 2 scoring meaningfully higher with `distinct_ratio`
holding.
**Test:** same case, cycles=1 vs cycles=2, same grader.
**Cost:** ~40 min.
**If the prediction holds,** more cycles is *anti-tuning* for backtests, and the
multi-cycle design is only justified on live claims where the premise can carry
real information. That is worth knowing and is the opposite of the intuition
that more deliberation is better.

### 4. Judge independence by model tier
**Knob:** `_claude_model()` maps slugs to opus / sonnet / haiku. Run the judge
on a different tier from the panel.

**Why:** today the panel and judge are the same underlying model at the same
temperature. Independence is of *information* (the judge sees only minutes), not
of training — a shared prior is shared by both sides of the check.

**Test:** fixed panel, judge=opus vs judge=sonnet.
**Cost:** ~25 min, and opus is the expensive tier.
**Caveat:** this cannot fully fix the problem. Real independence needs a
different model family, which this instance does not have.

### 5. Adversary seat — a panelist whose job is to attack the emerging consensus
**Knob:** add one panelist briefed to argue the *strongest case against* whatever
round 1 converged on, using `pattern-evaluator`'s kind (`adversary`).

**Why:** the judge has twice flagged a shared assumption nobody argued for
(`openai-nov-2023`: the zero-sum attention pool; `cand-05`: "same mathematical
move implies same mechanism"). The judge catching it *after* the fact is worse
than a panelist attacking it *during*.

**Test:** same case with and without the adversary seat.
**Cost:** ~30 min.
**Watch for:** an adversary that always dissents raises `distinct_ratio`
mechanically without improving accuracy. Judge it on the score, not the spread.

---

## What would make this a real result rather than a design

- **n is 6 cases**, four with a prior. Any knob tested on one case proves
  nothing; the minimum credible sweep is one knob across all six, which is ~6
  runs per arm.
- **Hold out two cases.** `craigslist-classifieds` and `netflix-cable` have no
  origin score. Tune on the four scored cases, then check the winning
  configuration on those two once. A configuration selected and validated on the
  same six is fitted.
- **Order matters:** fix the grader (#2) → run the grip filter (#1) → test the
  cycle prediction (#3). The rest only becomes worth running if #1 or #3 moves
  the number.

## The limit no amount of tuning removes

Every panelist, the judge, and the scorer are the same underlying model. Tuning
the arena optimises **how one model argues with itself**. On the six backtests
that can still be measured against sealed outcomes — which is why they are worth
running — but a configuration that wins here has been shown to extract more from
one model's priors, not to have found a more accurate way to see the world.
The AI-domain claims registered for October remain the only test of that.
