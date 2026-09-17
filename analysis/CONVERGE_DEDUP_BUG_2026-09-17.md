# The independence dedup collapses transitively — found 2026-09-17

**Severity: invalidating for any run where it fires.** One of six runs produced a
degenerate `p=1.00` claim from 14 vectors. That claim is in
`ai-pressure-field/predict/ledger.json` and should not be graded as a forecast.

## What happened

`suites/pressure_converge.py` implements the independence test from its own
docstring — "vectors sharing >50% of their source structure are ONE vector" —
with **union-find over the LLM's pairwise `overlaps` lists**.

Union-find is transitive. Overlap is not.

Beijing run, 14 vectors, every one merged into `v1`:

    v1  BIS export controls        overlaps v2, v3
    v3  Nvidia compliance          overlaps v1, v2, v4
    v4  State Council buy-local    overlaps v5, v9
    v12 Xi state visit             overlaps v11, v13
    v13 China rare-earth controls  overlaps v4, v12
    v14 Nexperia retaliation       overlaps v1, v13

Each pair is defensible. The chain is not: BIS export controls and Alibaba's
competitive position do not share a source structure, but
`v1–v3–v4–v9` connects them, so the resultant was computed from **one vector**:

    v1 -> 'labs self-restrict frontier weights': 3sev x 0.75cred x 1.0ts = 2.25
    tension=0.00

Distribution: `1.0 / 0.0 / 0.0 / 0.0`. Tension zero, because with one vector
there is nothing to be in tension with. Eight of the fourteen vectors pushed
`delay/no-change`; that outcome scored 0.0.

## Why the output looks fine

Nothing in the artifact says "this went wrong." The `.md` renders a clean
distribution, the ledger claim carries `confidence: 1.0`, and `p=1.00` reads as
maximum confidence rather than as a collapsed calculation. A certainty is the
one output a resultant-vector method should never emit, so it is also the
cheapest possible tripwire — and there isn't one.

## Blast radius across the six runs

| run | vectors | largest merge | top p | tension |
|---|---|---|---|---|
| Beijing | 14 | **14** | **1.00** | 0.00 |
| public opposition | 12 | 8 | 0.37 | 0.60 |
| US courts | 12 | 7 | 0.52 | 0.39 |
| frontier labs | 14 | 4 | 0.29 | 0.66 |
| EU AI Office | 10 | 4 | 0.35 | 0.59 |
| US executive | 12 | 4 | 0.35 | 0.50 |

Only Beijing fully collapsed, but an 8-of-12 merge is the same mechanism firing
part way. The independence test is meant to *prevent* overcounting corroboration;
here it overcounts *identity*, which is the opposite failure and biases toward
false certainty.

## This is consequence 3 of ai-pressure-field, on day one

`ai-pressure-field/MODEL.md` consequence 3: *"Merged vectors were not really one
vector. If merged-away vectors systematically resolve in different directions
from the vector they were merged into, the >50% test is wrong and convergence
counts built on it are inflated."*

That did not need to wait for resolution. Eight vectors pointing at
`delay/no-change` were merged into one pointing at `labs self-restrict`, which
is the consequence's condition observable at write time rather than at grading
time.

## Not patched here, and why

The fix is a design decision in someone else's engine, not a typo:

1. **Require mutual overlap** — merge only on `b in a.overlaps and a in b.overlaps`.
   Cheapest, still transitive.
2. **Cap component size** — refuse to merge a component past some fraction of the
   table and report the refusal. Treats the symptom.
3. **Drop transitivity** — cluster on a real similarity measure over
   `source_form` rather than on the LLM's pairwise hints. Most correct, most work.
4. **Add the tripwire regardless** — a post-dedup component holding >half the
   vectors, or any distribution emitting 1.0, should print loudly and refuse to
   write a ledger claim. This is separable from 1–3 and worth having whichever
   is chosen.

Recommended: 1 + 4 now, 3 when the psychometric work touches this file anyway.

## Also found, same session

`suites/new_model.py` scaffolds `MODEL.md` and `watch.json`, both of which
reference `predict/ledger.json`, but never creates that file. `pressure_converge`
writes its trace, then dies with `FileNotFoundError` appending the claim — so a
fresh model repo loses its first claim while keeping its trace. Created by hand
for `ai-pressure-field`.
