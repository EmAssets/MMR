# Deploying the garden index

Two files go to the `modelmeetsreality` Cloudflare Pages project:

| local | deployed to |
| --- | --- |
| `garden/index.json` | `/modelgarden/index.json` |
| `garden/AMENDMENT-2026-09-21.md` | `/modelgarden/AMENDMENT-2026-09-21.md` |

The cockpit already fetches `https://modelmeetsreality.xyz/modelgarden/index.json`
(see `ui/server.py`, `/api/garden`), so nothing client-side needs changing — the
Garden tab starts showing 43 models the moment the file lands.

## ORDER MATTERS

Per R3, the amendment is **published first** and the index follows only after
the comment window closes on **2026-10-05**. Shipping the index today is the
unregistered rule change that R3 exists to prevent, and there is a sealed
prediction resolving 2026-11-15 that watches for exactly that.

1. **now** — deploy `AMENDMENT-2026-09-21.md` only
2. **2026-10-05** — deploy `index.json`, with any objections received appended
   to the amendment per R3.3

## Deploy

`modelmeetsreality` is a Pages project with Git Provider: **No** (direct
upload), so it does not deploy from GitHub. Its deployments cite commits
(`a70a546`, `db4bdba`) from a working copy not present in this workspace —
point me at it and I will wire this in properly.

Failing that, direct upload of the two files works:

    npx wrangler pages deploy <site-dir> --project-name modelmeetsreality

## What is listed

43 of 45 models. `attention-substrate` and `canon` are **withheld**: their
MODEL.md has no `## Falsifiable consequences` section, so they are not listable
under the garden's own bar. They are named in `withheld_not_listable` rather
than silently omitted. Adding that section to either makes it listable.

`submitted_count` stays **0**. First-party listings never increase it; pooling
the counts would let the operator manufacture apparent traction.
