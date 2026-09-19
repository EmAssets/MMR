"""Publish the whole fleet as a dated, verifiable snapshot — engine plus every model.

WHY GIT BUNDLES AND NOT COPIED DIRECTORIES. Three reasons, and the third is the
one that matters:

  1. A bundle carries every commit. `trajectory` keys graded results by MODEL.md
     VERSION and `freeze_check` proves criteria were committed before a resolve
     date -- both read git history. A directory copy throws that away and takes
     the record's whole premise with it.
  2. A bundle is verifiable. `git bundle verify` before you clone it.
  3. A bundle contains ONLY TRACKED CONTENT. It structurally cannot carry `.env`,
     `inbox/` (other people's transcripts), `povs/`, `trajectory/` or any other
     gitignored working data. An allow-list of paths is a promise a human has to
     keep correct; this is the same guarantee enforced by the tool.

WHAT A SNAPSHOT IS. `fleet-<date>-<engine-commit>/` holding one bundle per repo,
a machine index (FLEET.json) and a readable one (FLEET.md). It is immutable: a
later snapshot is a new directory, never an overwrite, so a reader who cited one
can still fetch it.

REFUSES TO PUBLISH when any of these is true, because each one makes the
artifact a lie rather than merely imperfect:

  * a repo has uncommitted changes -- then the snapshot is a working tree, not a
    state, and nothing in it is attributable to a commit
  * `.env` is TRACKED in any repo
  * a credential-shaped string appears in any repo's tracked content or history
  * the engine's own preflight fails

    python -m suites.publish_fleet                      # stage + verify, upload nothing
    python -m suites.publish_fleet --publish r2 --dest <bucket>/<prefix> --handle <you>
    python -m suites.publish_fleet --publish r2 --dest ... --handle ... --apply
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
TODAY = datetime.date.today().isoformat()
# The standing mirror. A git host can suspend an account, a repo can be renamed
# or deleted, and a published record that lives in exactly one place is not
# published -- it is hosted. Every snapshot goes to both.
R2_BUCKET = os.environ.get("MMR_R2_BUCKET", "em-mmr-mirror")
R2_PUBLIC = os.environ.get("MMR_R2_PUBLIC",
                           "https://pub-12efc11b343c49df8ea3de54e815c451.r2.dev")

KEYPAT = (r"sk-or-v1-[A-Za-z0-9]{20,}|sk-ant-[A-Za-z0-9-]{20,}"
          r"|AIza[0-9A-Za-z_-]{30,}|ghp_[A-Za-z0-9]{30,}")


def _models_dir(root):
    try:
        cfg = json.loads((root / "fleet.json").read_text(encoding="utf-8"))
        if cfg.get("models_dir"):
            return (root / cfg["models_dir"]).resolve()
    except Exception:
        pass
    return root.parent


TOOLS = _models_dir(ROOT)


def _git(d: Path, *args, timeout=60) -> str:
    """git stdout, or "" — decoded with replacement, never None.

    `git log -p --all` over a repo containing any non-UTF8 byte (a transcript, a
    stray encoding) kills the default text decode on Windows, and the caller then
    gets None and crashes in re.search. A credential scan that dies on a binary
    byte is a scan that silently stops protecting you, so this decodes with
    errors="replace" and always returns a string.
    """
    try:
        r = subprocess.run(["git", *args], cwd=str(d), capture_output=True,
                           timeout=timeout)
        return (r.stdout or b"").decode("utf-8", errors="replace")
    except Exception:
        return ""


def audit(repos: list) -> tuple[list, list]:
    """Every refuse-to-publish condition, checked per repo. Returns (ok, blocked)."""
    ok, blocked = [], []
    for slug, d in repos:
        why = []
        if not (d / ".git").exists():
            why.append("not a git repo")
        else:
            if _git(d, "status", "--porcelain").strip():
                why.append("uncommitted changes -- a snapshot must be a committed state")
            if _git(d, "ls-files", ".env").strip():
                why.append(".env is TRACKED")
            if _git(d, "grep", "-lIE", KEYPAT).strip():
                why.append("credential-shaped string in tracked content")
            # history too: .gitignore only stops future adds
            hist = _git(d, "log", "-p", "--all", timeout=180)
            if re.search(KEYPAT, hist):
                why.append("credential-shaped string in git HISTORY")
        (blocked if why else ok).append((slug, d, why))
    return ok, blocked


def bundle_all(repos: list, out: Path) -> list:
    out.mkdir(parents=True, exist_ok=True)
    made = []
    for slug, d, _ in repos:
        f = out / ("%s.bundle" % slug)
        r = subprocess.run(["git", "bundle", "create", str(f), "--all"],
                           cwd=str(d), capture_output=True, text=True, timeout=300)
        if r.returncode != 0 or not f.exists():
            print("  [skip] %s: bundle failed" % slug)
            continue
        v = subprocess.run(["git", "bundle", "verify", str(f)], cwd=str(d),
                           capture_output=True, text=True, timeout=120)
        made.append({"slug": slug, "file": f.name, "bytes": f.stat().st_size,
                     "head": _git(d, "rev-parse", "--short", "HEAD").strip(),
                     "commits": len([l for l in _git(d, "log", "--oneline").splitlines() if l]),
                     "tracked_files": len([l for l in _git(d, "ls-files").splitlines() if l]),
                     "verified": v.returncode == 0})
    return made


def index(made: list, blocked: list) -> dict:
    """The machine index. A reader's site lists a snapshot from THIS file alone."""
    ladder = {}
    try:
        m = json.loads((ROOT / "map" / "projections" / "em-ladder.v1.json")
                       .read_text(encoding="utf-8"))
        ladder = m.get("assignments", {})
    except Exception:
        pass
    try:
        fleet = json.loads((ROOT / "fleet.json").read_text(encoding="utf-8"))
    except Exception:
        fleet = {}
    rows = []
    for b in made:
        d = TOOLS / b["slug"] if b["slug"] != "MMR" else ROOT
        a = ladder.get(b["slug"], {})
        card = d / "model.json"
        md = d / "MODEL.md"
        rows.append(dict(b, e_span=a.get("e_span"), kind=a.get("kind"),
                         aspects=a.get("aspects"),
                         has_model_md=md.exists(),
                         # MODEL_SPEC_V1 makes model.json the shareable card and
                         # make_card generates it. None of the private repos has
                         # one; reported as null rather than invented.
                         card=json.loads(card.read_text(encoding="utf-8"))
                         if card.exists() else None))
    return {
        "spec": "mmr-fleet-snapshot-v1",
        "built": TODAY,
        "engine_commit": _git(ROOT, "rev-parse", "--short", "HEAD").strip(),
        "repos": len(rows),
        "total_bytes": sum(r["bytes"] for r in rows),
        "fleet_json": fleet,
        "status": ("Every model here is its author's own theory, stated so it can be "
                   "wrong: premises, at least one dated falsifiable consequence, and a "
                   "deletion clause. Models OF PEOPLE are models of their public "
                   "output, authored by this instance -- never those people's own "
                   "claims about themselves, and never claims about anyone's private "
                   "life or interior states."),
        "how_to_use": [
            "git clone <slug>.bundle <slug>     # full history, every version",
            "git bundle verify <slug>.bundle    # before you clone it",
            "clone MMR.bundle as the engine; clone the models as its siblings",
            "python -m suites.compat_check      # then read MMR/CLAUDE.md",
        ],
        "records_are_not_transferable": (
            "A track record belongs to the instance that made the predictions. "
            "Imported claims are quarantined and never graded as the receiver's own "
            "(docs/CONTRIBUTING.md). Clone these to read the theories, not to "
            "inherit the record."),
        "excluded": [{"slug": s, "why": w} for s, _, w in blocked],
        "models": sorted(rows, key=lambda r: r["slug"]),
    }


def readable(ix: dict) -> str:
    L = []
    L.append("# MMR fleet snapshot %s" % ix["built"])
    L.append("")
    L.append("Engine at commit `%s`. %d repositories, %.1f MB of bundles."
             % (ix["engine_commit"], ix["repos"], ix["total_bytes"] / 1e6))
    L.append("")
    L.append(ix["status"])
    L.append("")
    L.append("## Use it")
    L.append("")
    L.append("```bash")
    for h in ix["how_to_use"]:
        L.append(h)
    L.append("```")
    L.append("")
    L.append(ix["records_are_not_transferable"])
    L.append("")
    L.append("## The fleet")
    L.append("")
    L.append("| model | commits | tracked | E-span | kind | bundle |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    for r in ix["models"]:
        L.append("| `%s` | %d | %d | %s | %s | %.0f KB |"
                 % (r["slug"], r["commits"], r["tracked_files"],
                    ("E%d-E%d" % tuple(r["e_span"])) if r.get("e_span") else "-",
                    r.get("kind") or "-", r["bytes"] / 1000))
    if ix["excluded"]:
        L.append("")
        L.append("## Excluded from this snapshot")
        L.append("")
        for e in ix["excluded"]:
            L.append("- `%s` — %s" % (e["slug"], "; ".join(e["why"])))
    L.append("")
    L.append("## No model here carries a card yet")
    L.append("")
    L.append("`docs/MODEL_SPEC_V1.md` makes `model.json` the shareable card, generated")
    L.append("by `make_card`. No repo in this snapshot has one, so `card` is `null`")
    L.append("throughout the index rather than invented. Run `make_card` per model to")
    L.append("produce them.")
    return "\n".join(L) + "\n"


def to_github(repos: list, ix: dict, org: str, apply: bool) -> None:
    """Push each repo to its own GitHub repository under a dedicated owner.

    WHY THIS IS THE BETTER TARGET for a fleet, where R2 was right for one event
    bundle: a reader runs `git clone` and has the working repo with its whole
    history, no bundle step. GitHub also serves the browse-and-read case an
    article's readers actually want.

    WHY IT IS HANDLED SEPARATELY AND CAREFULLY. Pushing is the one step in this
    whole pipeline that is irreversible and outward-facing under an identity. The
    engine's own SETUP.md warns about exactly this failure: a clone that kept its
    origin, and `git push` sending private premises to a repo nobody intended.
    So:

      * the owner must be passed EXPLICITLY (--org). There is no default, and it
        must not be whatever account `gh` happens to be logged into -- the
        operator asked for a dedicated account precisely so the personal one
        cannot receive this by accident.
      * the currently authenticated account is printed and must MATCH --org, or
        this refuses. An `gh auth status` showing a personal account while --org
        names the publishing one means the push would land as the wrong identity.
      * --apply is still required. Without it this prints the plan.
    """
    who = _git(ROOT, "config", "--get", "user.name").strip()
    auth = subprocess.run(["gh", "api", "user", "--jq", ".login"],
                          capture_output=True, text=True, timeout=60)
    login = (auth.stdout or "").strip()
    print("")
    print("  gh authenticated as: %s" % (login or "(unknown)"))
    if not org:
        raise SystemExit(
            "--publish github needs --org <dedicated-account>.\n"
            "There is deliberately no default: the account gh is logged into is\n"
            "'%s', and pushing a fleet to a personal account by omission is the\n"
            "failure SETUP.md warns about." % (login or "?"))
    if login and login.lower() != org.lower():
        raise SystemExit(
            "gh is authenticated as '%s' but --org is '%s'.\n"
            "Switch accounts first (gh auth switch / gh auth login) so the push\n"
            "lands under the intended identity:\n"
            "  gh auth login --hostname github.com   # as %s\n"
            "Refusing to push cross-identity." % (login, org, org))

    print("  target owner: %s" % org)
    print("  %d repositories would be created and pushed:" % len(repos))
    for slug, d, _ in repos[:6]:
        print("    %s/%s" % (org, slug))
    if len(repos) > 6:
        print("    ... and %d more" % (len(repos) - 6))
    print("")
    print("  per repo: gh repo create %s/<slug> --public --source <dir> --push" % org)
    print("  plus one index repo carrying FLEET.json / FLEET.md")
    if not apply:
        print("")
        print("  DRY RUN -- nothing pushed. This is the irreversible step: a public")
        print("  push can be cloned, cached and forked within minutes. Re-run with")
        print("  --apply once the dedicated account is the authenticated one.")
        return
    for slug, d, _ in repos:
        r = subprocess.run(["gh", "repo", "create", "%s/%s" % (org, slug),
                            "--public", "--source", str(d), "--push",
                            "--description", "MMR model: %s" % slug],
                           capture_output=True, text=True, timeout=300)
        ok_ = r.returncode == 0
        print("    %-28s %s" % (slug, "pushed" if ok_ else
                                (r.stderr or "").strip().splitlines()[0][:70]))
    print("  done. Readers: git clone https://github.com/%s/<slug>" % org)
    print("")
    print("  A git host is a single point of failure for a published record.")
    print("  Mirror the same snapshot to R2 so the bundles survive an account")
    print("  suspension, a rename, or a deleted repo:")
    print("    python -m suites.publish_fleet --publish r2 --dest %s --handle %s --apply"
          % (R2_BUCKET, org))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", choices=["r2", "gcs", "github"], nargs="?", const="r2",
                    help="r2/gcs upload bundles; github pushes each repo as its own "
                         "remote branch (readers git clone directly)")
    ap.add_argument("--org", default="",
                    help="github: the owner (user or org) to push to. MUST be the "
                         "dedicated publishing account, not your personal one.")
    ap.add_argument("--dest", default=R2_BUCKET,
                    help="r2 bucket/prefix (defaults to the standing mirror) "
                         "or gs://bucket/path")
    ap.add_argument("--handle", default=os.environ.get("MMR_HANDLE", ""))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", default="",
                    help="comma-separated slugs to publish, or a batch spec "
                         "like 3/1 meaning 'batch 1 of size 3'. Batching keeps each "
                         "irreversible action small and stoppable.")
    ap.add_argument("--allow-blocked", action="store_true",
                    help="publish the repos that pass, listing the rest as excluded, "
                         "instead of refusing the whole snapshot")
    a = ap.parse_args()

    repos = [("MMR", ROOT)]
    for d in sorted(p for p in TOOLS.iterdir() if p.is_dir() and p != ROOT):
        if (d / ".git").exists():
            repos.append((d.name, d))
    print("[fleet] %d repositories found (engine + %d models)" % (len(repos), len(repos) - 1))

    ok, blocked = audit(repos)
    print("  audit: %d clean, %d blocked" % (len(ok), len(blocked)))
    for s, _, w in blocked:
        print("    !! %-26s %s" % (s, "; ".join(w)))
    if blocked and not a.allow_blocked:
        raise SystemExit(
            "\nRefusing to publish. Fix the above, or pass --allow-blocked to publish\n"
            "only the clean repos with the rest listed as excluded in the manifest.\n"
            "A snapshot containing a working tree is not a state, and a snapshot that\n"
            "hides what it left out is worse than one that publishes less.")

    # --only narrows what is PUBLISHED, never what is AUDITED. The credential and
    # clean-state checks above always run over the whole fleet: a batch that
    # passes while a sibling is dirty is still a snapshot built beside a problem,
    # and the operator should see it before the first push, not the sixteenth.
    if a.only:
        m = re.fullmatch(r"(\d+)/(\d+)", a.only.strip())
        if m:
            size, which = int(m.group(1)), int(m.group(2))
            if size < 1 or which < 1:
                raise SystemExit("--only N/M needs N>=1 and M>=1")
            ordered = sorted(ok, key=lambda r: (r[0] != "MMR", r[0].lower()))
            batches = [ordered[i:i + size] for i in range(0, len(ordered), size)]
            if which > len(batches):
                raise SystemExit("batch %d of size %d does not exist (%d batches for "
                                 "%d clean repos)" % (which, size, len(batches), len(ordered)))
            ok = batches[which - 1]
            print("  batch %d of %d (size %d): %s"
                  % (which, len(batches), size, ", ".join(s for s, _, _ in ok)))
            print("  remaining after this batch: %d"
                  % max(0, len(ordered) - which * size))
        else:
            want = {x.strip() for x in a.only.split(",") if x.strip()}
            missing = want - {s for s, _, _ in ok}
            if missing:
                raise SystemExit("--only names repo(s) not in the clean set: %s"
                                 % ", ".join(sorted(missing)))
            ok = [r for r in ok if r[0] in want]
            print("  publishing %d named repo(s): %s" % (len(ok), ", ".join(sorted(want))))

    snap = "fleet-%s-%s" % (TODAY, _git(ROOT, "rev-parse", "--short", "HEAD").strip())
    out = ROOT / "publish" / snap
    made = bundle_all(ok, out)
    bad = [m["slug"] for m in made if not m["verified"]]
    if bad:
        raise SystemExit("bundle verify FAILED for: %s" % ", ".join(bad))
    print("  bundled %d repo(s), all verify" % len(made))

    ix = index(made, blocked)
    (out / "FLEET.json").write_text(json.dumps(ix, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
    (out / "FLEET.md").write_text(readable(ix), encoding="utf-8")
    print("  -> %s" % out)
    print("     %.1f MB, FLEET.json + FLEET.md" % (ix["total_bytes"] / 1e6))

    if not a.publish:
        print("\n  staged only. Add --publish r2 --dest <bucket>/<prefix> --handle <you>")
        return
    if a.publish == "github":
        return to_github(ok, ix, a.org, a.apply)
    if not a.dest or not a.handle:
        raise SystemExit("--publish needs --dest and --handle")

    # Immutable snapshot: a dated bundle never changes, so it caches for a year.
    # Only `latest/FLEET.json` is mutable, and it is the one object an index polls.
    files = sorted(p for p in out.rglob("*") if p.is_file())
    cmds = []
    base = "%s/%s/%s" % (a.dest.strip("/"), a.handle, snap)
    for f in files:
        rel = f.relative_to(out).as_posix()
        ct = ("application/json" if rel.endswith(".json")
              else "application/octet-stream" if rel.endswith(".bundle")
              else "text/markdown; charset=utf-8")
        cmds.append(["npx", "wrangler", "r2", "object", "put", "%s/%s" % (base, rel),
                     "--file", str(f), "--content-type", ct,
                     "--cache-control", "public, max-age=31536000, immutable",
                     "--remote"] if a.publish == "r2"
                    else ["gsutil", "-h", "Cache-Control:public,max-age=31536000,immutable",
                          "cp", str(f), "%s/%s/%s" % (a.dest.rstrip("/"), snap, rel)])
    ptr = out / "FLEET.json"
    cmds.append(["npx", "wrangler", "r2", "object", "put",
                 "%s/%s/latest/FLEET.json" % (a.dest.strip("/"), a.handle),
                 "--file", str(ptr), "--content-type", "application/json",
                 "--cache-control", "public, max-age=300", "--remote"]
                if a.publish == "r2"
                else ["gsutil", "-h", "Cache-Control:public,max-age=300", "cp",
                      str(ptr), "%s/latest/FLEET.json" % a.dest.rstrip("/")])

    print("\n  key layout: %s/<file>" % base)
    print("  plus a short-TTL pointer at %s/%s/latest/FLEET.json" % (a.dest.strip("/"), a.handle))
    print("  %d object(s) to upload" % len(cmds))
    if not a.apply:
        print("  DRY RUN -- nothing uploaded. Inspect %s, then re-run with --apply." % out)
        print("  A publish cannot be taken back once cached.")
        return
    for c in cmds:
        r = subprocess.run(c, capture_output=True, text=True)
        if r.returncode != 0:
            print((r.stderr or r.stdout or "")[-800:])
            raise SystemExit("upload failed on %s" % c[-1])
    print("  uploaded %d object(s)." % len(cmds))
    if a.publish == "r2":
        pref = "%s/%s" % (a.handle, snap)
        print("")
        print("  public mirror:")
        print("    index:  %s/%s/FLEET.json" % (R2_PUBLIC, pref))
        print("    latest: %s/%s/latest/FLEET.json" % (R2_PUBLIC, a.handle))
        print("    bundle: %s/%s/<slug>.bundle" % (R2_PUBLIC, pref))
        print("  a reader with no git host access:")
        print("    curl -O %s/%s/MMR.bundle && git clone MMR.bundle MMR" % (R2_PUBLIC, pref))


if __name__ == "__main__":
    main()
