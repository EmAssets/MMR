# Submitting a model: what actually happens

I walked the submission path on 2026-09-21 exactly as the page describes it,
using real repos, and recorded every place it breaks. Nothing here is
hypothetical — each item is a command that was run and its actual output.

**Headline:** the path as written fails at step 2 for every submitter, and a
single unbuilt file silently blocked 13 of 45 otherwise-valid models.

---

## F1 — The validator command on the page cannot work · BLOCKING

The page says:

> 2. Check it: `python -m suites.validate_card model.json --repo .`

Run that in a model repo, which is where an author is standing:

```
$ cd my-model
$ python -m suites.validate_card model.json --repo .
Error while finding module specification for 'suites.validate_card'
(ModuleNotFoundError: No module named 'suites')
```

`suites` lives in the MMR **engine**, not in a model repo. Step 1 tells the
author to prepare a repo with three files; step 2 tells them to run a module
that exists somewhere else entirely, with no instruction to clone it.

Every submitter hits this. It is the first thing they are asked to do, and it
fails with a Python traceback.

**Fix, cheapest first:**

- State the dependency in step 2:
  `git clone https://github.com/EmAssets/MMR && cd MMR && python -m suites.validate_card ../my-model/model.json --repo ../my-model`
- Better: ship `validate_card` as a **single dependency-free file** an author
  can download next to their model. It already imports only the stdlib.
- Best: validate server-side on submit, so the author pastes a URL and gets the
  verdict back. Then step 2 disappears from the author's job entirely.

## F2 — Two first-party tools disagree about the same card · BLOCKING

`make_card` reported a card listable that `validate_card` then rejected:

```
$ python -m suites.make_card --all --author EmAssets
  43 listable, 2 blocked by a missing falsifier

$ python -m suites.validate_card ../ai-pressure-field/model.json --repo ../ai-pressure-field
  FAIL [schema] card has no coordinates (coords or e_span)
  VERDICT: not listable — 1 blocking issue(s).
```

The generator and the checker apply different rules. An author who runs the
generator, is told "listable", submits, and is then rejected has been actively
misled — and has no way to know which tool speaks for the Garden.

This is a known regression: `make_card.map_coords` carries a docstring
describing this exact failure as already fixed once.

**Fix:** `make_card` should run `validate_card`'s checks before printing
"listable", and refuse to claim a card is listable that the validator would
reject. One of the two tools has to be authoritative, and it should be the one
the page tells authors to trust.

## F3 — A missing file produces a traceback and exit code 0 · SHOULD FIX

```
$ python -m suites.validate_card ../blindspot-model/model.json --repo ../blindspot-model
Traceback (most recent call last):
  ...
FileNotFoundError: [Errno 2] No such file or directory: '..\\blindspot-model\\model.json'
$ echo $?
0
```

Two problems. A traceback is not an error message an author can act on — the
fix is "run make_card first", which the output never says. And **exit 0 on
failure** means any CI wired to this check passes when the card is missing,
which is the one case it most needs to catch.

**Fix:** catch `FileNotFoundError`, print
`no model.json at <path> — generate one with: python -m suites.make_card --model <slug>`,
and exit non-zero on every blocking outcome.

## F4 — One unbuilt file silently blocked 13 of 45 models · WAS BLOCKING

Every one of the 13 failures was the same line: `card has no coordinates
(coords or e_span)`. The coordinates come from `map/mapcards.json`, which the
instance had built when it held 32 models. The other 13 were simply absent from
it, so `make_card` emitted cards with no coordinates and `validate_card`
rejected all 13.

```
before:  32 listable, 13 blocked
$ python -m suites.reality_map --build      # 45 cards
after:   44 listable,  1 blocked
```

Nothing was wrong with those 13 models. A stale derived file made them
unlistable, and the error message names a missing field rather than the missing
build step, so the author cannot tell the difference between "my model is
incomplete" and "your index is stale".

**Fix:** have `make_card` rebuild or refresh the map when a model is not in it,
or at minimum make the message say so:
`no coordinates — this model is not on the reality map; run: python -m suites.reality_map --build`.

## F5 — The "three required files" are four · SHOULD FIX

The page says `MODEL.md`, `model.json`, and a LICENSE. In practice a listable
card also needs the instance's **reality map** built (F4), and `MODEL.md` must
contain two specific sections whose exact headings are never stated on the
page:

- `## Falsifiable consequences` — without it, not listable
- premises — `canon` fails with `MODEL.md states no premises`

An author reading the page has no way to know these headings are load-bearing.

**Fix:** publish a minimal `MODEL.md` template with the required headings, and
link it from step 1. "Match the v1 format" is not actionable without one.

---

## What the machine check should say, and does not

The page promises:

> Everything else is machine-checked: the licence and the three required files,
> nothing about whether the model is any good.

That promise is right, and the checker mostly honours it — every blocking
reason encountered was structural (missing coordinates, missing premises,
missing falsifiable consequences), none was about quality. The problem is not
the bar. It is that **the author cannot reach the checker**, and when they do,
its failures do not name the action that fixes them.

## Measured state after the fixes above

| | |
| --- | --- |
| model repos | 45 |
| listable after rebuilding the map | **44** |
| blocked | 1 (`canon` — genuinely has no premises) |
| licence check | 45/45 pass (all CC-BY-4.0) |
| blocked for quality reasons | 0 |

## Suggested order of work

1. **F1** — fix the command on the page. One line of copy; unblocks everyone.
2. **F2** — make `make_card` refuse to overclaim. Prevents the worst
   experience, which is being told yes and then no.
3. **F4** — better message, or auto-rebuild. Turns 13 mystery failures into
   one actionable instruction.
4. **F3** — exit codes and a readable missing-file error.
5. **F5** — publish a `MODEL.md` template.

Items 1–3 are the difference between a submission process that works and one
that does not. 4 and 5 are polish.

---

# Part 2 — actually submitting, 2026-09-21

Corrected premise: **an external user needs no Cloudflare access at all.** They
paste a GitHub URL into the form and press one button. The page is right that
nothing is uploaded. Earlier notes in this document assumed the operator's
publishing path was the submitter's path; it is not.

The form posts to `POST /modelgarden/api/submit`, guarded by Turnstile. It
works: `ai-pressure-field` returned **"Queued for review."** on the first try.

## F6 — the Turnstile token is single-use, and nothing says so · SHOULD FIX

Submitting a second model without reloading fails:

> Challenge failed — reload and try again

An author with five models to submit must fully reload the page between each
one. The message does say "reload", which is better than most — but the form
gives no indication beforehand that one submission per page load is the rule,
and the natural behaviour after a success is to type the next URL.

**Fix:** reset the Turnstile widget after a successful submit
(`turnstile.reset()`), so consecutive submissions work without a reload. Failing
that, clear the field on success and say "reload to submit another".

## F7 — a submission succeeded while the UI reported failure · SHOULD FIX

`blindspot-model` was submitted on a stale token and the UI showed *"Challenge
failed."* Resubmitting after a reload returned:

> Already queued for review

So the first attempt **did** reach the queue. The UI reported a failure for a
request that succeeded. An author in that position either gives up on a model
that is actually queued, or resubmits repeatedly against a backend that already
has it.

**Fix:** make the client trust the response status rather than inferring from
the challenge, and distinguish "not submitted" from "submitted, duplicate".
"Already queued for review" is the right message — it just needs to not follow
a false failure.

## F8 — the field keeps a stale value after a failed submit · MINOR

After a failed attempt the input still held a URL from an earlier attempt, so
the next click submitted the wrong repo. Clearing on success, and leaving the
value intact only on genuine failure, would make the state legible.

## What is good, and should not change

- **One field, one button.** Nothing to configure, no account, no upload.
- **The error messages are specific.** An empty POST returns *"Send an https
  link to a public repo — e.g. https://github.com/you/your-model"*, which names
  the fix. That is better than most submission forms.
- **Duplicate detection works**, and its message is honest.
- **Turnstile rejects scripted POSTs.** A direct `curl` with a valid repo URL
  returned 403 — the anti-spam is real, not decorative.

## Measured

| | |
| --- | --- |
| submissions attempted | 3 |
| reached the queue | 2 (`ai-pressure-field`, `blindspot-model`) |
| failed for a real reason | 0 |
| failed for token reuse | 1, which had in fact succeeded (F7) |
| Cloudflare access needed by the submitter | **none** |

## Revised priority

F6 and F7 are now the top items, above everything in Part 1 — they affect every
author submitting more than one model, and F7 actively misinforms. F1 (the
validator command that cannot run) remains the highest-impact copy fix.

---

# Part 3 — blast_radius on UNGA 81, 2026-09-22

Second live test of the extractor, on a case with a genuinely different shape:
a four-year institutional lineage (Global Digital Compact 2024 -> A/RES/79/325
-> Geneva session) running alongside a one-day debate.

**It flagged its own problem**, which is the behaviour the validators exist for:

```
! 2 nodes claim to be the seed: global-digital-compact, rahman-opens-debate
  unreachable from this centre: abdullah-unga81, rahman-opens-debate
```

That was correct — the case really does have two roots — but two edges were
wrong, and the extractor's own quoted evidence showed it:

| edge drawn | evidence quoted | what the evidence names |
| --- | --- | --- |
| `trump-unga81 -> dialogue-inaugural-session` | "totally rejects any attempt to construct a globalist scheme" | no Geneva session; he is speaking into the general debate |
| `erdogan-unga81 -> dialogue-inaugural-session` | "establish a common international legal framework for AI" | also the general debate |

**Same failure class as the Microsoft edge in openai-nov-2023:** acts attached
to the most prominent prior node rather than to the one the evidence names. The
flattening detector did not fire, because this chain is four deep — flat-to-seed
was the wrong symptom to watch for. Depth does not prove the edges are right.

Corrected (both speakers -> `rahman-opens-debate`, which opened the debate they
spoke into), every node becomes reachable and the seed is unique.

**What the corrected structure shows:** Trump and Erdoğan sit at **L2 from each
other**. They took opposite positions on the same day in the same room and
there is no edge between them — both responded to the debate, neither to the
other. An account that reads them as arguing with each other is adding a
relationship the record does not contain.

**Fix to consider:** the "everything attached to the seed" heuristic catches
flattening but not misrouting. A stronger check would ask whether each edge's
evidence mentions its target at all — tried once and removed for crying wolf on
shared words (see Part 1), so it needs to be smarter than substring matching,
not merely reinstated.
