# Remote access to the cockpit

The cockpit binds `127.0.0.1:8787` and has **no authentication of its own**. Its header
still says "local · 127.0.0.1 only" and it exposes, among 26 endpoints:

- `POST /api/run` — executes suites. `grade` runs `grading_loop`, which spends LLM budget.
- `POST /api/inbox` — queues instructions into a Claude Code session.

So exposure is not a UI convenience question. **Cloudflare Access is the entire security
boundary.** The tunnel must never run without a policy in front of the hostname.

## What is configured

| piece | value |
| --- | --- |
| tunnel name | `mmr-cockpit` |
| tunnel id | `d3a841d7-cc47-4c4e-a1aa-2874df4e86f1` |
| hostname | `cockpit.modelmeetsreality.com` (CNAME added by `tunnel route dns`) |
| config | `~/.cloudflared/config.yml` — single ingress rule, catch-all `http_status:404` |
| Zero Trust plan | Free (50 seats, $0) |
| Access application | `MMR Cockpit`, self-hosted, public DNS |
| Access policy | `Owner only` — Action **Allow**, Include **Emails = <owner email>** |
| policy id | `94059072-a8a7-4077-9d59-028a49b727fd` |
| identity | accept-all IdPs; with none configured this is the built-in **one-time PIN by email** |
| session | 24 hours |

Access is **default-deny**: anything not matching `Owner only` is refused at Cloudflare's
edge and never reaches the tunnel.

## Order of operations, and why it matters

The policy must exist **before** the tunnel runs. Starting the tunnel first publishes
`/api/run` and `/api/inbox` to the internet for however long the gap lasts.

Verify the boundary exists before starting anything:

```bash
~/bin/cloudflared.exe access login https://cockpit.modelmeetsreality.com
```

- `failed to find Access application` -> **no policy. Do not start the tunnel.**
- a URL containing `aud=<hash>` -> the application is registered and enforcing.

Then:

```bash
python ui/server.py                                        # cockpit on 127.0.0.1:8787
~/bin/cloudflared.exe tunnel --config ~/.cloudflared/config.yml run mmr-cockpit
```

`cloudflared tunnel list` shows a CONNECTIONS count once it is up; blank means down.

## From a phone

Open `https://cockpit.modelmeetsreality.com`. Cloudflare presents its own login page,
mails a one-time PIN to `<owner email>`, and the session lasts 24 hours. No
password is typed anywhere and nothing is installed on the device.

## Known gap

Access authenticates the *person*, not the *request*. Once a session is open, every
endpoint is reachable — including the two that spend money and queue instructions. If
the cockpit ever needs to be shared with anyone else, per-endpoint authorisation inside
`ui/server.py` is the thing to add; the Access policy cannot express it.
