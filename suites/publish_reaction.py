"""Publish the reaction-layers data so the live page picks it up.

The page at modelmeetsreality.com/asset/reaction-layers.html fetches its data
from reaction-layers.json beside it. That split is the point: new analysis is
ONE upload, and the blog embed, the standalone page and the cockpit copy all
update together. Nothing is republished and nothing goes stale in three places.

The page also ships with the last known data baked in as a fallback, so a failed
or malformed fetch renders the previous reading rather than an empty frame. A
visualisation that silently empties is worse than one that is a few days old.

  python -m suites.publish_reaction --check          # what would change
  python -m suites.publish_reaction --apply          # upload it

A dossier is only written where sourced material exists. An actor with none
renders as "nothing on file", which is a statement about this reading rather
than about them -- inventing a plausible position for a real person is the
failure this whole project is built to avoid.
"""
from __future__ import annotations

import argparse
import json
import shutil
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
DATA = ROOT / "arena" / "cases" / "reaction" / "coxon-resignation.page.json"
BUCKET = "em-mmr-mirror"
KEY = "asset/reaction-layers.json"
LIVE = "https://modelmeetsreality.com/asset/reaction-layers.json"


def _npx() -> str:
    """wrangler runs through npx, which is a .cmd on Windows and not on PATH
    for a bare subprocess call. Resolved rather than assumed."""
    for name in ("npx.cmd", "npx"):
        p = shutil.which(name)
        if p:
            return p
    raise SystemExit("npx not found on PATH — install Node, or upload by hand")


def validate(d: dict) -> list:
    """Problems that would break the live page. Returned, never auto-repaired."""
    out = []
    nodes = d.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return ["no nodes array — the page would fall back to its baked copy"]
    ids = [n.get("id") for n in nodes]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        out.append("duplicate ids: %s" % ", ".join(sorted(map(str, dupes))))
    seeds = [n["id"] for n in nodes if not n.get("to")]
    if len(seeds) != 1:
        out.append("expected exactly one seed, found %d: %s" % (len(seeds), ", ".join(seeds)))
    known = set(ids)
    for n in nodes:
        if n.get("to") and n["to"] not in known:
            out.append("%s points at unknown node %r" % (n.get("id"), n["to"]))
        if not n.get("act"):
            out.append("%s has no act" % n.get("id"))
        # A dossier line with no source is allowed but must say so on the page;
        # a dossier with no `known` list at all is a half-written record.
        dos = n.get("dossier")
        if dos is not None and not dos.get("known"):
            out.append("%s has a dossier with no 'known' entries" % n.get("id"))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Publish reaction-layers data to R2.")
    ap.add_argument("--file", default=str(DATA))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    f = Path(a.file)
    if not f.exists():
        raise SystemExit("no data file at %s" % f)
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SystemExit("not valid JSON: %s" % e)

    probs = validate(d)
    nodes = d.get("nodes") or []
    print("[reaction] %s" % f)
    print("  %d nodes · %d with a dossier · updated %s"
          % (len(nodes), sum(1 for n in nodes if n.get("dossier")), d.get("updated", "?")))
    for p in probs:
        print("  ! %s" % p)
    if probs:
        raise SystemExit("refusing to publish with problems above")

    if not a.apply:
        print("\n  DRY. Nothing uploaded. Re-run with --apply to publish:")
        print("    python -m suites.publish_reaction --apply")
        return

    cmd = [_npx(), "wrangler", "r2", "object", "put", "%s/%s" % (BUCKET, KEY),
           "--file", str(f), "--content-type", "application/json; charset=utf-8",
           "--remote"]
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print(r.stdout[-800:])
        print(r.stderr[-800:])
        raise SystemExit("upload failed")
    print("  uploaded -> %s" % LIVE)
    print("  the live page picks it up on next load; nothing else to republish.")


if __name__ == "__main__":
    main()
