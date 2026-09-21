"""Blast radius — how many reaction-hops from the original act is each actor?

An event is not a flat list of responses. Someone reacts to the act; someone
else reacts to that reaction; a commentator summarises four layers and adds a
fifth. Those are different epistemic positions and flattening them loses the
thing you most want to know: WHO WAS ACTUALLY LOOKING AT WHAT.

The Coxon case makes it concrete. David Sacks attacked "the proposal" and METR's
independence -- he was responding to Amodei's essay, not to the resignation post.
Altman and Musk agreed with "pacing the frontier", which is Amodei's phrase.
Reading either as a response to Coxon puts them one ring too close and makes the
event look like a referendum on a resignation when it had become an argument
about an audit regime.

TWO STAGES, and the split is the point:

  1. An LLM reads the chronology and extracts EDGES: who responded to what, with
     the QUOTED SPAN that licenses each edge. This is a reading task and it is
     where the judgement lives.
  2. Plain code computes layers by breadth-first search. No model decides that
     Sacks is "layer 2" -- that falls out of the edges, and re-centering on any
     node recomputes it deterministically.

Stage 2 being code is what makes the output auditable: you can disagree with one
edge, change it, and every layer recomputes without re-running anything.

WHAT A LAYER IS NOT. It is not the emergence-ladder floor. `floor` (E8-E13) says
which substrate an act operates on; a layer says how many hops of reaction it
sits from the seed. A state (E12) can sit at layer 2. Both are carried and they
are never merged -- conflating them would quietly corrupt the ladder reading.

EVERY EDGE IS OUR READING. "Sacks responded to Amodei rather than Coxon" is an
inference from what he attacked, and it ships with the quote so a reader can
overrule it. Edges that no span licenses are marked inferred=true rather than
asserted quietly.

  python -m suites.blast_radius --case arena/cases/reaction/openai-nov-2023.md
  python -m suites.blast_radius --case <file> --center microsoft
  python -m suites.blast_radius --test        # known-answer cases
  python -m suites.blast_radius --case <file> --html out.html
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import re
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

EXTRACT = """You are mapping the REACTION STRUCTURE of an event: who responded to
what, and specifically whether each actor was responding to the original act or
to somebody else's response to it.

THE CHRONOLOGY:
{chronology}

Return every actor or act that appears, and for each one name what it was
RESPONDING TO -- the single thing its author was demonstrably looking at when
they acted.

RULES, and the whole value of this depends on them:

1. Decide from what the act ITSELF references. If someone attacks "the proposal",
   they are responding to the proposal, NOT to the earlier event that prompted
   the proposal. If someone replies to a post, they are responding to the post.

1a. THE MOST COMMON ERROR IS ATTACHING EVERYTHING TO THE SEED. Before you write
   any edge, re-read your own quoted span and ask: does it name the seed, or does
   it name something that itself responded to the seed? "responding to their
   departure" means the DEPARTURE is the target, not the event that caused the
   departure. "cites the offer" means the OFFER is the target. If your quote
   names an intermediate act, the edge points at the intermediate act. An edge
   whose evidence names something other than its target is simply wrong.

1b. Chains are expected and are the whole point. A five-item chronology can be
   five layers deep. Do not flatten it because every item ultimately traces back
   to the same origin -- of course it does; the question is by what route.
2. Quote the span that licenses each edge, verbatim from the chronology above.
   If no span licenses it, set "inferred": true and say what you reasoned from.
   An honest inferred edge is fine; a fabricated quote destroys the whole record.
3. The SEED is the act everything descends from. It responds to nothing.
4. Do NOT assert what anyone believes, wants or fears. "This act references X" is
   a claim about the act. "He was angry about X" is banned.
5. A person can appear at a different position than you expect. Someone who
   helped cause the original act, but whose PUBLIC ACT here responded to a later
   reaction, is positioned by the act -- not by their earlier involvement.
6. Two actors who did the same thing at the same remove share a position. That
   is expected and is not a problem to resolve.

Return STRICT JSON:
{{
 "seed": "<slug of the originating act>",
 "nodes": [
  {{"id": "<short-kebab-slug>",
    "label": "<human-readable name>",
    "act": "<what they publicly did, one line>",
    "date": "<YYYY-MM-DD or the chronology's own wording>",
    "responded_to": "<slug of what this act references, or null for the seed>",
    "evidence": "<verbatim span from the chronology licensing that edge>",
    "inferred": false,
    "kind": "<person|organization|state|press|public|artifact>"}}
 ]
}}"""


def parse_chronology(path: Path) -> tuple:
    """Title and chronology body from a case file."""
    t = path.read_text(encoding="utf-8", errors="replace")
    lines = t.splitlines()
    title = lines[0].lstrip("# ").strip() if lines else path.stem
    m = re.search(r"^##\s*Chronology.*$", t, re.M)
    body = t[m.end():] if m else t
    # stop at the next section, so quarantined claims and instructions to the
    # panel never reach the extractor as if they were events
    nxt = re.search(r"^##\s+", body, re.M)
    if nxt:
        body = body[:nxt.start()]
    return title, body.strip()


# ------------------------------------------------------------------ stage 2

def compute_layers(nodes: list, center: str = "") -> dict:
    """Breadth-first distance from the center, over UNDIRECTED reaction edges.

    Undirected on purpose. Centering on a late commentator should still reach
    the seed -- "how many layers of reaction did this person stack before adding
    their own" is exactly a walk back down the chain. Direction is preserved in
    the edge list for rendering; distance ignores it.

    Returns {id: layer}. Nodes unreachable from the center are ABSENT rather
    than assigned a large number: "not connected to this center" and "far from
    this center" are different facts and must not be merged.
    """
    by_id = {n["id"]: n for n in nodes}
    adj = collections.defaultdict(set)
    for n in nodes:
        tgt = n.get("responded_to")
        if tgt and tgt in by_id and tgt != n["id"]:
            adj[n["id"]].add(tgt)
            adj[tgt].add(n["id"])
    start = center or next((n["id"] for n in nodes if not n.get("responded_to")),
                           nodes[0]["id"] if nodes else "")
    if start not in by_id:
        raise SystemExit("no such entity: %r (have: %s)"
                         % (start, ", ".join(sorted(by_id))))
    dist = {start: 0}
    q = collections.deque([start])
    while q:
        cur = q.popleft()
        for nb in sorted(adj[cur]):
            if nb not in dist:
                dist[nb] = dist[cur] + 1
                q.append(nb)
    return dist


def validate(nodes: list, chronology: str) -> list:
    """Structural and evidence problems. Returned, never silently repaired."""
    problems = []
    ids = [n.get("id") for n in nodes]
    by_id = {n.get("id"): n for n in nodes}
    dupes = [i for i, c in collections.Counter(ids).items() if c > 1]
    if dupes:
        problems.append("duplicate ids: %s" % ", ".join(map(str, dupes)))
    seeds = [n["id"] for n in nodes if not n.get("responded_to")]
    if len(seeds) > 1:
        problems.append("%d nodes claim to be the seed: %s" % (len(seeds), ", ".join(seeds)))
    if not seeds:
        problems.append("no seed — every node claims to respond to something")
    for n in nodes:
        t = n.get("responded_to")
        if t and t not in by_id:
            problems.append("%s responds to unknown node %r" % (n.get("id"), t))
        if t == n.get("id"):
            problems.append("%s responds to itself" % n.get("id"))
        ev = (n.get("evidence") or "").strip()
        # A quote that is not in the chronology is a fabricated citation, which
        # this repo treats as the one unforgivable failure. Checked on a
        # normalised copy so whitespace and dash style do not cry wolf.
        if ev and not n.get("inferred"):
            norm = lambda s: re.sub(r"\s+", " ", s.replace("—", "-")
                                    .replace("’", "'").replace("“", '"')
                                    .replace("”", '"')).strip().lower()
            if norm(ev)[:60] and norm(ev)[:60] not in norm(chronology):
                problems.append("%s cites a span not found in the chronology: %r"
                                % (n.get("id"), ev[:60]))
    # A "does the evidence name a different node than the target" check was
    # tried here and REMOVED. On the real openai-nov-2023 extraction it missed
    # both genuine errors and fired twice on correct edges, because node ids
    # share words ("altman-posts" vs "altman-returns"). A detector that cries
    # wolf while missing the fault is worse than none: it trains you to ignore
    # it. The structural check below -- a chronology of N sequential acts that
    # collapses to depth 1 -- catches the same failure without pretending to
    # parse meaning out of a quote.

    # EVERYTHING-ATTACHED-TO-THE-SEED. The failure mode that collapsed
    # openai-nov-2023 from 4 layers to 2: most acts pointed straight at the
    # seed, because every act ultimately traces back to it. Of course it does;
    # the question is by what route. This is a smell, not proof, so it is
    # reported as one.
    if len(nodes) >= 6:
        direct = sum(1 for n in nodes if n.get("responded_to") == (seeds[0] if seeds else None))
        if direct >= len(nodes) * 0.6:
            problems.append(
                "%d of %d acts attach directly to the seed — chains may have been "
                "flattened; check whether an act references an intermediate act"
                % (direct, len(nodes)))

    # a cycle means someone responded to something that responded to them
    seen, stack = set(), set()

    def walk(i):
        if i in stack:
            problems.append("cycle through %s" % i)
            return
        if i in seen or i not in by_id:
            return
        stack.add(i); seen.add(i)
        t = by_id[i].get("responded_to")
        if t:
            walk(t)
        stack.discard(i)

    for i in list(by_id):
        walk(i)
    return problems


def build(nodes: list, title: str, center: str = "", source: str = "") -> dict:
    dist = compute_layers(nodes, center)
    by_id = {n["id"]: n for n in nodes}
    rings = collections.defaultdict(list)
    for i, d in dist.items():
        rings[d].append(i)
    unreached = sorted(set(by_id) - set(dist))
    return {
        "spec": "blast-radius-v1",
        "title": title, "built": TODAY, "source": source,
        "center": center or next((n["id"] for n in nodes if not n.get("responded_to")), ""),
        "nodes": [dict(n, layer=dist.get(n["id"])) for n in nodes],
        "rings": {str(k): sorted(v) for k, v in sorted(rings.items())},
        "max_layer": max(dist.values()) if dist else 0,
        "unreachable": unreached,
        "note": ("Layer = reaction hops from the centred entity, computed by BFS over "
                 "extracted edges. It is NOT the emergence-ladder floor: a state (E12) "
                 "can sit at layer 2. Every edge is our reading of what an act "
                 "references, carries the span that licenses it, and can be overruled."),
    }


# ------------------------------------------------------------------ extract

def extract(case: Path, model_hint: str, dry: bool) -> dict:
    from suites import arena as A
    # arena loads .env inside main(); calling _call directly skips that and the
    # backend selection with it, which surfaces as a misleading "no API key" on
    # a machine configured for the claude-code backend.
    A._load_env()
    title, chron = parse_chronology(case)
    if not chron.strip():
        raise SystemExit("no chronology found in %s" % case)
    body = A._call(model_hint, EXTRACT.format(chronology=chron), dry)
    if dry:
        return {"_dry": True, "nodes": []}
    if body.get("_error"):
        raise SystemExit("extraction failed: %s" % body["_error"])
    if body.get("_unparsed"):
        raise SystemExit("model did not return JSON:\n%s" % body["_unparsed"][:400])
    nodes = body.get("nodes") or []
    if not nodes:
        raise SystemExit("no nodes extracted")
    probs = validate(nodes, chron)
    out = build(nodes, title, "", str(case))
    out["problems"] = probs
    return out


# ------------------------------------------------------------------ test

def run_tests(model_hint: str, dry: bool) -> int:
    """Check the extractor against chronologies whose structure is known.

    The expected layers were hand-coded from each chronology BEFORE this module
    existed, so a disagreement is a real finding rather than a judgement made to
    fit. `must_hold` lists the RELATIVE facts that matter more than the absolute
    numbers -- an extractor that shifts every layer by one is far less wrong than
    one that puts Microsoft on the same ring as Brockman.
    """
    d = ROOT / "arena" / "cases" / "reaction"
    cases = sorted(d.glob("*.md"))
    if not cases:
        print("no known-answer cases in %s" % d)
        return 1
    fails = 0
    for c in cases:
        exp_f = c.with_suffix(".expected.json")
        if not exp_f.exists():
            print("[skip] %s — no expected file" % c.name)
            continue
        exp = json.loads(exp_f.read_text(encoding="utf-8"))
        print("\n== %s ==" % c.name)
        got = extract(c, model_hint, dry)
        if dry:
            print("  [dry] extraction skipped")
            continue
        if got.get("problems"):
            print("  structural problems:")
            for p in got["problems"]:
                print("    ! %s" % p)
            fails += len(got["problems"])
        gl = {n["id"]: n["layer"] for n in got["nodes"]}
        el = exp["expected_layers"]
        # Match on ids the extractor chose; it may legitimately name or split
        # nodes differently, so report coverage rather than demanding identity.
        #
        # Names are NOT the thing under test. The extractor may reasonably name a
        # node by its act ("board-removes-altman") where the expected file named
        # it by its actor ("openai-board"); that is a labelling difference, not a
        # structural disagreement. So fall back to fuzzy id matching, and treat
        # must_hold -- which is about RELATIVE depth -- as the real assertion.
        common = [k for k in el if k in gl]
        if not common:
            alias = {}
            for k in el:
                parts = [p for p in k.split("-") if len(p) > 3]
                for g in gl:
                    if k == g or any(p in g for p in parts):
                        alias.setdefault(k, g)
            if alias:
                print("  no exact id overlap; matched %d by name fragment:" % len(alias))
                for k, g in sorted(alias.items()):
                    print("      %-22s ~ %s" % (k, g))
                gl = dict(gl, **{k: gl[g] for k, g in alias.items()})
                common = [k for k in el if k in gl]
        print("  expected %d entities, extractor found %d, %d ids in common"
              % (len(el), len(gl), len(common)))
        if not common:
            print("    ! no id overlap — cannot compare layers")
            print("      extractor ids: %s" % ", ".join(sorted(gl)))
            fails += 1
            continue
        exact = sum(1 for k in common if gl[k] == el[k])
        print("  exact layer match: %d/%d" % (exact, len(common)))
        for k in sorted(common):
            if gl[k] != el[k]:
                print("    x %-24s expected L%s, got L%s" % (k, el[k], gl[k]))
        # relative constraints matter more than absolute numbers
        for claim in exp.get("must_hold", []):
            m = re.match(r"(\S+) is deeper than (\S+)", claim)
            if not m:
                # A constraint this harness cannot evaluate must SAY so. Silently
                # skipping it reports a pass that was never checked, which is
                # worse than having no constraint at all.
                print("  ?     not machine-checkable, verify by eye: %s" % claim)
                continue
            if m.group(1) not in gl or m.group(2) not in gl:
                print("  ?     entity missing, cannot check: %s" % claim)
                continue
            ok = gl[m.group(1)] > gl[m.group(2)]
            print("  %s %s" % ("ok  " if ok else "FAIL", claim))
            fails += 0 if ok else 1
    return 1 if fails else 0


# ------------------------------------------------------------------ render

def render_html(data: dict, standalone: bool = True) -> str:
    """One self-contained file: data inlined, no fetches, no external scripts.

    Inlined because this is embedded in a blog post via iframe and a chart that
    silently empties when a host is unreachable is worse than no chart.
    """
    tpl = (ROOT / "ui" / "blast.html")
    if not tpl.exists():
        raise SystemExit("missing template: %s" % tpl)
    html = tpl.read_text(encoding="utf-8")
    return html.replace("/*__DATA__*/null",
                        json.dumps(data, ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser(description="Reaction layers of an event.")
    ap.add_argument("--case", default="")
    ap.add_argument("--center", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--html", default="")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--from-json", default="", help="re-centre an existing blast.json")
    ap.add_argument("--model", default="auto")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.test:
        raise SystemExit(run_tests(a.model, a.dry_run))

    if a.from_json:
        d = json.loads(Path(a.from_json).read_text(encoding="utf-8"))
        data = build([{k: v for k, v in n.items() if k != "layer"} for n in d["nodes"]],
                     d["title"], a.center, d.get("source", ""))
    elif a.case:
        data = extract(Path(a.case), a.model, a.dry_run)
        if a.center:
            data = build([{k: v for k, v in n.items() if k != "layer"}
                          for n in data["nodes"]], data["title"], a.center, data.get("source", ""))
    else:
        raise SystemExit("need --case, --from-json or --test")

    for p in data.get("problems", []):
        print("  ! %s" % p)
    print("[blast] %s — centred on %s" % (data["title"], data["center"]))
    for ring, ids in sorted(data["rings"].items(), key=lambda kv: int(kv[0])):
        print("  L%s  %s" % (ring, ", ".join(ids)))
    if data.get("unreachable"):
        print("  unreachable from this centre: %s" % ", ".join(data["unreachable"]))

    if a.out:
        Path(a.out).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print("  -> %s" % a.out)
    if a.html:
        Path(a.html).write_text(render_html(data), encoding="utf-8")
        print("  -> %s" % a.html)


if __name__ == "__main__":
    main()
