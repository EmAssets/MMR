# Adding the MMR models to the modelmeetsreality.xyz ledger

`ledger_public.json` in this directory is the merged file. Drop it at
`data/ledger_public.json` in whatever builds the site, and deploy.

## What changed

- **61 existing rows: byte-identical.** Verified programmatically — nothing
  removed, nothing altered, no duplicate ids.
- **11 rows added**, as two new instruments:
  - **H — `ai-pressure-field`**, 9 claims resolving 2026-11-01 to 2026-12-17
  - **I — `blindspot-model`**, 2 claims resolving 2026-10-31 and 2027-03-31

## These are NAMED, and that is a change of contract

Every new row carries `model`, `repo` and `reasoning_open: true`. The model, its
repository and its full reasoning are public **now**, before the outcome.

That is the opposite of instruments A–G, whose reasoning is hash-committed and
disclosed only at grading. Both are pre-registered and graded identically; they
differ only in **when the reasoning becomes readable**.

`schema.disclosure` in the merged file states this. **The page copy must change
too**, or the site will contradict itself.

### Copy that is now false

> "Sealed predictions from undisclosed instruments, graded against reality in
> public"

> "The reasoning behind each one is hash-committed now and disclosed only when
> the claim is graded"

### Suggested replacement

> Predictions registered before their outcome and graded in public. Some
> instruments are sealed — their reasoning is hash-committed and disclosed only
> at grading. Others are open: the model and its full reasoning are published
> now, before the outcome, so you can find the error before reality does.

Also update the counters: **7 instruments → 9**, **60 claims sealed → 61 sealed
+ 11 open**. Leaving "60 claims sealed" beside 11 unsealed ones is exactly the
sort of quiet inaccuracy this ledger exists to avoid.

## Why this wasn't deployed for you

`modelmeetsreality.xyz` is a Cloudflare Pages project (`modelmeetsreality`)
with **Git Provider: No** — direct upload, not GitHub. Its deployments cite
commits `a70a546` / `db4bdba` from a working copy that is not in this
workspace, and no repo in `EmAssets` contains the site.

Point me at that working copy and I will apply this, make the copy change, and
commit locally.

## Attribution

Each new row carries the short commit of the model repo it came from
(`ai-pressure-field` @ 71daa15, `blindspot-model` @ 4289ba4), so a claim is
traceable to the exact state of the model that made it. Two readers on
different commits are running different instruments, and the ledger should be
able to say which.
