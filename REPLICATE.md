# Replicate this setup

## What this snapshot is

**One instance, on one date, with one combination of models.**

- published **2026-09-19**, engine at commit `fafb8f4`
- 47 repositories: the engine plus 46 models
- owner `github.com/EmAssets`

That is deliberately specific, because none of it is permanent. An MMR *instance*
is one engine plus whichever models its operator carries; a different instance is
a different combination, and the same operator may publish several — a work
instance and a personal one, or one per domain, each with its own `fleet.json` and
its own record. `SETUP.md` §5 is explicit that separate worlds get separate
instances and that instances share nothing, because that isolation is the feature.

So read this as *"how the 2026-09-19 EmAssets snapshot is replicated"*, not as
*"how MMR is set up"*. Later snapshots will hold different models, and a model you
find here may be absent, renamed, retired under its own deletion clause, or
several versions further on. Check `FLEET.json` in whichever snapshot you actually
cloned rather than trusting this list.

**Two copies, always.** Every snapshot goes to a git host and to object storage,
because a record in exactly one place is hosted rather than published. The mirror
for this snapshot:

```bash
# the index: what this snapshot holds, and every model's published commit
curl https://pub-12efc11b343c49df8ea3de54e815c451.r2.dev/EmAssets/latest/FLEET.json

# any repo, with no git host involved
curl -O https://pub-12efc11b343c49df8ea3de54e815c451.r2.dev/EmAssets/fleet-2026-09-19-a288218/MMR.bundle
git clone MMR.bundle MMR
```

A bundle is the whole repository, every commit — not a copy of the working files.
That distinction carries weight here: results are keyed to the model version that
produced them, so a copy without history cannot be audited.

**How to tell which snapshot you have.** Every published snapshot carries
`FLEET.json` with its build date, its engine commit, and per model the HEAD it was
published at. A claim citing a model is only attributable if it names that
commit — so record the snapshot you cloned before you start.

`SETUP.md` covers building a fleet **from scratch** — start there if you want no
inherited theories at all. This file covers the other path: clone a published
fleet, then make it yours.

---

## What you are getting, and what you are not

**You get the theories.** Every model here is a document: premises, a mechanism,
at least one falsifiable consequence with a date, and a deletion clause naming
when its author would retire it. You also get the full git history of each one,
which means you can see how a theory changed and when.

**You do NOT get the track record.** This matters and is not a formality. A
record belongs to the instance that made the predictions. When you import a
model, its origin's claims are quarantined to `imported/` and are never graded as
yours — see `docs/CONTRIBUTING.md`. A system whose whole product is "did this
predict correctly" cannot let records travel without the predictions being
re-made.

So: clone these to read the theories and to start from a working instrument. Your
record starts empty, and it should.

**Models of people are models of public output.** Several repos (`expert-*`) model
named analysts' publicly stated reasoning, authored by the original instance. They
are not those people's own claims about themselves, and they contain no assertions
about anyone's private life or interior states. If you extend them, keep that
line: the engine bans claims about what an actor believes, wants or fears, and
that ban is load-bearing rather than decorative.

---

## 1. Clone the engine and the models as siblings

The layout is not negotiable — every suite resolves `--repo foo` to `../foo`:

```
your-workspace/
  MMR/                      <- the engine. Suites, harness, fleet.json
  ai-pressure/              <- a model, sibling of the engine
  lab-moves/                <- another
  ...
```

Fastest path, one model to start:

```bash
mkdir mmr-workspace && cd mmr-workspace
git clone https://github.com/EmAssets/MMR
git clone https://github.com/EmAssets/adjacent-possible
```

The whole fleet at once — read `FLEET.json` from a published snapshot for the
list, or:

```bash
gh repo list EmAssets --limit 60 --json name --jq '.[].name' \
  | xargs -I{} git clone https://github.com/EmAssets/{}
```

## 2. Detach from the origin, or a later push goes to the wrong place

```bash
cd MMR
git remote remove origin
```

Do this in every repo you intend to develop. `SETUP.md` explains why at length and
it is the failure worth repeating: a fresh clone keeps `origin` pointing at
somebody else's repository, and a later `git push` sends your private premises
there. Removing the remote makes the copy genuinely yours.

If you would rather keep the upstream to pull updates, rename it instead:

```bash
git remote rename origin upstream
```

Then you can `git pull upstream master` without ever pushing by accident.

## 3. Point fleet.json at the models you actually cloned

`fleet.json` is the single registry every suite reads, and it is the file that
makes an instance *that* instance rather than a generic one. The copy in this
snapshot lists 44 models; if you cloned three, it will look for 41 that are not
there.

This is also where you diverge from the snapshot and become your own instance.
Trim it to what you cloned, add what you scaffold, and from that point your
`fleet.json` is the definition of your fleet — not this one.

```bash
cd MMR
# edit fleet.json: keep only the slugs you cloned
```

`decision_repo` is where `pressure_converge` and `event_update --file-claim`
write. It points at `ai-pressure-field`; change it if you want computed claims
somewhere else, and note that `new_model` does NOT create `predict/ledger.json` —
create it as `{"predictions": []}` by hand or the first write crashes after
producing its trace.

## 4. Choose a backend

```bash
cp .env.example .env
```

Three options, and the engine works on all three:

- **No API key.** `LLM_BACKEND=claude-code` shells out to the `claude` CLI and
  bills a subscription you already have. Cheapest full setup.
- **A metered key.** Set `OPENROUTER_API_KEY`.
- **Fully local.** Point `OPENROUTER_BASE` at Ollama, LM Studio or vLLM. Nothing
  leaves your machine; web-grounded steps degrade loudly and report
  `researched=False` rather than pretending.

## 5. Confirm it runs before you trust it

```bash
python -m suites.compat_check     # does this work at every installation level?
python -m suites.arena_test       # the arena's blindness invariants
```

Python 3.10+, no dependencies for the core. `compat_check` reports `MANUAL` for
the paste-into-an-assistant path and `skip` for anything not installed — **neither
is a pass.** `skip` means unverified.

Then read `CLAUDE.md`. It is written for an assistant working in this repo and is
the densest description of how the parts fit.

---

## Running a model without any of this

A reader with no Python can still use any model. Paste into ChatGPT, Claude or
Gemini:

```
https://github.com/EmAssets/adjacent-possible  Help me use this
```

The assistant reads `USE.md` and runs the model. `USE.md` follows Review →
Explain → Confirm → Apply and fences the author's text as quoted data, because a
long pasted instruction block is shaped exactly like a prompt-injection attempt
and the only honest difference is that this one expects to be examined and
refused.

---

## Your first real loop

```bash
# 1. a model with grip on something you care about
python -m suites.model_watch --repo <model> --predict   # register dated claims
python -m suites.model_watch --repo <model> --assess    # grade what is due

# 2. your own model when none of these has grip
python -m suites.new_model my-risk-model \
    --title "..." --domain "..." --kind forecaster --level 0

# 3. the whole fleet, on a schedule
python -m suites.grading_loop --dry     # what is due; run nothing
python -m suites.grading_loop           # the pass
```

Write the MODEL.md the way you would finally admit the theory to yourself:
premises at honest confidence tiers, falsifiable consequences with dates, and a
deletion clause you intend to honour. The deletion clause is the part that is
unpleasant to write and the part that makes the rest mean anything.

## Reading a shared event, and contributing your reading

`CLAUDE.md`'s contribution section is the full protocol. The short version:

```bash
python -m suites.event_lens --event arena/cases/<case>.md --models <slugs>
python -m suites.event_lens --compare <case>
python -m suites.arena --case <case> --tag <your-handle>
python -m suites.event_update --case <case> --diff
```

Two disciplines that make your reading comparable with anyone else's:

**Pin the commit.** Every model is its own repo, and a claim is attributable only
if it names the version it argued from. `git log --oneline -- MODEL.md` lists
them; cite the short hash. Two readers on different commits of one model are
running different instruments.

**Measure your own noise before claiming a change.** Argue the same brief twice
with no new facts. Whatever moves is your noise floor, and a difference smaller
than it is resampling, not news. On the first event run through this loop the
load-bearing pivot moved on an unchanged brief — so `event_update --diff` prints
that stability check before anything else, every time.

---

## What is honest about the current state

- **Almost nothing is graded yet.** The claims in these ledgers mostly resolve in
  the future. The record that would tell you whether any of this predicts well
  does not exist yet.
- **No model carries a `model.json` card.** `docs/MODEL_SPEC_V1.md` makes that the
  shareable card and `make_card` generates it; none has been run.
- **One historical arena case, scored once.** That is a basis for saying the
  machinery runs, not that it produces better thinking.
- **Where the engine codes evidence, a language model does the reading.** Two
  independent codings of the same historical cases agreed on 50% of verdicts,
  which is why `adjacent-possible` now codes every case twice and refuses to read
  its own bets below two-thirds agreement. Expect to find more of this.
- **Every reading is v1.** Ours, dated, built from what was gatherable that day.
  Some of it is wrong. Being wrong on a date is the mechanism, not the failure.

## If you publish your own instance

The engine publishes itself. `python -m suites.publish_fleet` audits every repo,
bundles each one, and writes `FLEET.json` + `FLEET.md`; adding
`--publish github --org <your-account> --apply` pushes them.

Four things it refuses to do, each because the artifact would otherwise be a lie
rather than merely imperfect: publish while any repo has uncommitted changes (a
working tree is not a state, and nothing in it is attributable to a commit),
publish a tracked `.env`, publish a repo with a credential-shaped string anywhere
in its tracked content **or its git history**, or push when the authenticated
account does not match `--org`. Use `--only N/M` to go in batches; each push is
irreversible once someone clones it, and a batch you can stop after is better than
one you cannot.

Your snapshot will be a different combination from this one. That is the expected
outcome, not a divergence to reconcile: the map is supposed to end up with several
instances claiming the same regions with different records, and
`docs/CONTRIBUTING.md` treats two cards disagreeing as the system working.
