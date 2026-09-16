"""Fleet timeline — what already happened, and what each model expects next.

The engine's `event_history` assembles PAST events from what decision models
observed while running. This assembles the whole line, past and future, from
four sources the fleet already holds, and writes the same shape the cockpit's
/api/timeline route reads.

WHY FOUR SOURCES, KEPT DISTINCT. They have different evidentiary status and
must never be flattened into one undifferentiated list of "predictions":

  observed        a dated fact, with a source URL. It happened.
  model-expect    a numbered consequence from a MODEL.md. The model ASSERTS it;
                  there is no probability, because the kinds do not produce one.
                  Calling these "predictions with 50% confidence" would invent
                  precision no model claimed.
  expert-claim    a dated claim by a named commentator, registered in
                  ai-expert-calibration BEFORE resolution, with criteria we
                  wrote. The speaker did not supply a probability either.
  joint-claim     a brainstorm synthesis claim. These are the ONLY rows with a
                  real number, and it is an LLM panel's confidence, not a
                  calibrated forecast. Labelled as such.

EVERY FUTURE ROW IS A WINDOW, NOT A POINT. "By 2027-06-30" means any time
between registration and that date. The row carries `start` and `end` so the UI
can draw the window rather than implying the event lands on the deadline.

DATES ARE DIRTY, and are kept that way — same discipline as event_history. The
raw string is preserved and a sortable ISO date sits alongside it with `approx`
set when the parse was inferred ("6-12 months", "Q2", "roughly this summer").

  python -m suites.fleet_timeline --build
  python -m suites.fleet_timeline --build --out ../entity-atlas/timeline.json
"""
from __future__ import annotations

import argparse
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


def _models_dir(root):
    try:
        cfg = json.load((root / "fleet.json").open(encoding="utf-8"))
        if cfg.get("models_dir"):
            return (root / cfg["models_dir"]).resolve()
    except Exception:
        pass
    return root.parent


TOOLS = _models_dir(ROOT)
BUILT = datetime.date.today().isoformat()

# The authoring date of the fleet's own documents. Every MODEL.md carries it
# dozens of times ("written 2026-09-16", "LOGGED 2026-09-16"); those are
# provenance stamps, not events, and would swamp the timeline.
AUTHORING_DATES = {BUILT}

ISO = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


def norm_date(s: str):
    """(sortable ISO, approx). Mirrors event_history's contract."""
    s = (s or "").strip()
    if not s:
        return None, False
    m = ISO.search(s)
    if m:
        return m.group(1), False
    m = re.search(r"\b(20\d{2})-Q([1-4])\b", s)
    if m:
        y, q = int(m.group(1)), int(m.group(2))
        return "%04d-%02d-01" % (y, {1: 3, 2: 6, 3: 9, 4: 12}[q]), True
    m = re.search(r"\b(20\d{2})-(\d{2})\b", s)
    if m:
        return "%s-%s-01" % (m.group(1), m.group(2)), True
    m = re.search(r"\b(20\d{2})\b", s)
    if m:
        return m.group(1) + "-12-31", True
    return None, False


def _kind_of(text: str) -> str:
    m = re.search(r"\*\*The kind:\*\*\s*(\S+)", text)
    return m.group(1) if m else "?"


def _title_of(text: str, slug: str) -> str:
    m = re.search(r"^#\s+(.+?)(?:\s+[—-]\s+\(v\d+\))?\s*$", text, re.M)
    return m.group(1).strip() if m else slug


def collect_consequences(rows):
    """Numbered items under '## Falsifiable consequences'. Model expectations."""
    for d in sorted(TOOLS.glob("ai-*")):
        md = d / "MODEL.md"
        if not md.exists():
            continue
        t = md.read_text(encoding="utf-8")
        kind, title = _kind_of(t), _title_of(t, d.name)
        m = re.search(r"## Falsifiable consequences.*?\n(.*?)(?=\n## )", t, re.S)
        if not m:
            continue
        block = m.group(1)
        # numbered items, possibly multi-line until the next "N. " or blank-blank
        for item in re.finditer(r"^\s*(\d+)\.\s+(.+?)(?=^\s*\d+\.\s|\Z)", block, re.S | re.M):
            body = re.sub(r"\s+", " ", item.group(2)).strip()
            if len(body) < 25:
                continue
            dates = ISO.findall(body)
            dates = [x for x in dates if x not in AUTHORING_DATES]
            if not dates:
                continue
            end = max(dates)
            rows.append({
                "type": "model-expect",
                "item": body[:420],
                "date_raw": end,
                "date": end, "approx": False,
                "start": BUILT, "end": end,
                "confidence": None,
                "observer": d.name,
                "model_kind": kind,
                "model_title": title,
                "ref": "consequence %s" % item.group(1),
                "source": "",
            })


def collect_expert_claims(rows):
    cdir = TOOLS / "ai-expert-calibration" / "claims"
    if not cdir.exists():
        return
    for f in sorted(cdir.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        who = d.get("commentator", f.stem)
        role = d.get("role", "")
        for c in d.get("claims", []):
            rb = c.get("resolve_by", "")
            iso, approx = norm_date(rb)
            sd, _ = norm_date(c.get("source_date", ""))
            rows.append({
                "type": "expert-claim",
                "item": '%s: "%s"' % (who, re.sub(r"\s+", " ", c.get("quote", ""))[:300]),
                "date_raw": rb, "date": iso, "approx": approx,
                "start": sd or BUILT, "end": iso,
                "confidence": None,
                "observer": "ai-expert-calibration",
                "commentator": who, "role": role,
                "domain": c.get("domain", ""),
                "criteria": c.get("resolution_criteria", "")[:400],
                "conflicts_with": c.get("conflicts_with"),
                "conditional_on": c.get("conditional_on"),
                "ref": c.get("id", ""),
                "source": c.get("source", ""),
                "status": c.get("status", "open"),
            })


def collect_joint_claims(rows):
    bdir = ROOT / "brainstorms"
    if not bdir.exists():
        return
    for f in sorted(bdir.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        syn = d.get("synthesis", {}) or {}
        at, _ = norm_date(str(d.get("at", "")))
        for c in syn.get("joint_claims", []) or []:
            rb = str(c.get("resolve_by", ""))
            iso, approx = norm_date(rb)
            if not iso:
                continue
            rows.append({
                "type": "joint-claim",
                "item": re.sub(r"\s+", " ", str(c.get("claim", "")))[:420],
                "date_raw": rb, "date": iso, "approx": approx,
                "start": at or BUILT, "end": iso,
                "confidence": c.get("confidence"),
                "observer": d.get("id", f.stem),
                "models": d.get("models", []),
                "criteria": str(c.get("resolution_criteria", ""))[:400],
                "ref": d.get("id", f.stem),
                "source": "",
            })


# Dated facts the fleet recorded. Each carries the source it came from, so a
# reader can check it -- an undated or unsourced "event" is a rumour.
OBSERVED = [
 ("2026-01-13", "BIS moves H200/MI325X-class chips from presumption-of-denial to case-by-case review, paired with a 25% semiconductor tariff",
  "https://www.morganlewis.com/pubs/2026/01/bis-revises-export-review-policy-for-advanced-ai-chips-destined-for-china-and-macau", "ai-us-policy-direction"),
 ("2026-03-20", "White House issues a national AI legislative framework urging a light-touch federal rulebook and preemption of state AI laws",
  "https://www.ropesgray.com/en/insights/alerts/2026/03/the-white-house-legislative-recommendations-national-policy-framework-for-artificial-intelligence-an", "ai-us-policy-direction"),
 ("2026-06-18", "Richard Campbell (NDC keynote): 'None of these companies are profitable, not even close'; places AI in the trough of disillusionment",
  "https://youtu.be/uWnUnMphmPM", "ai-bubble-thesis"),
 ("2026-07-30", "Jen Easterly (former CISA director) warns the greatest danger is the failure to imagine how AI can be weaponized — recorded BEFORE the September incidents",
  "https://youtu.be/VmV-Yg4Ljls", "ai-cyber-offense-defense"),
 ("2026-08-02", "EU AI Act enforcement begins: the AI Office and national authorities start applying GPAI and transparency obligations",
  "https://digital-strategy.ec.europa.eu/en/news/commission-starts-enforcing-ai-act-rules-and-new-transparency-requirements-2-august", "ai-regulation-teeth"),
 ("2026-08-03", "Alibaba releases Qwen3.8-Max", "https://local-ai-zone.github.io/blog/September_2026_AI_Model_Updates.html", "ai-frontier-cadence"),
 ("2026-08-04", "Reporting: ~$1.65 trillion of off-balance-sheet AI commitments across the five biggest US tech firms; Alphabet completes a ~$85bn equity raise (June)",
  "https://youtu.be/NufJ7g63KSY", "ai-bubble-thesis"),
 ("2026-08-07", "Dwarkesh Patel publishes 8 predictions for the era of continual learning",
  "https://youtu.be/iewm45atodE", "ai-rsi-timeline"),
 ("2026-08-12", "xAI releases Grok 4.6", "https://local-ai-zone.github.io/blog/September_2026_AI_Model_Updates.html", "ai-frontier-cadence"),
 ("2026-08-25", "Dylan Patel: lab compute tripling annually; Anthropic turned a profit in Q2 2026; ~$1T capex this year rising above $2T by 2028",
  "https://youtu.be/aV26V1UvkJw", "ai-compute-concentration"),
 ("2026-08-26", "Jim VandeHei (Axios) argues planning horizons have collapsed and six-month plans no longer hold",
  "https://youtu.be/ABggCjL-9Tk", "ai-adoption-phases"),
 ("2026-09-01", "Anthropic ships Claude Fable 5.1 and Mythos 5.1, and cuts cache-read pricing by 75%",
  "https://local-ai-zone.github.io/blog/September_2026_AI_Model_Updates.html", "ai-frontier-cadence"),
 ("2026-09-02", "Google DeepMind ships Gemini 3.8 Flash plus a defenders-only Cyber variant; Meta ships Muse Spark 1.3",
  "https://local-ai-zone.github.io/blog/September_2026_AI_Model_Updates.html", "ai-frontier-cadence"),
 ("2026-09-03", "OpenAI releases GPT-6 Astra — reported as the first model to trigger its critical-cyber safeguard threshold",
  "https://local-ai-zone.github.io/blog/September_2026_AI_Model_Updates.html", "ai-frontier-cadence"),
 ("2026-09-10", "DeepSeek releases V4.1-Flash, cutting agent memory costs fourfold",
  "https://local-ai-zone.github.io/blog/September_2026_AI_Model_Updates.html", "ai-open-weights-lag"),
 ("2026-09-11", "Schulman, Millidge and O'Neill argue research judgment — not code volume — is the binding constraint, and continual learning is unsolved",
  "https://youtu.be/PrSf7IOYu-I", "ai-rsi-timeline"),
 ("2026-09-12", "Dario Amodei publishes 'We Must Pace the Frontier'; Anthropic unilaterally commits to embedded third-party evaluators with permanent employee-level access",
  "https://darioamodei.com/post/we-must-pace-the-frontier", "ai-lab-revealed-priorities"),
 ("2026-09-13", "Amodei on CBS: 'we need to slow down'; Altman and Musk publicly endorse the pacing principle without matching the commitment",
  "https://youtu.be/hQR_VJF6ukk", "ai-lab-revealed-priorities"),
 ("2026-09-15", "EU: GPAI providers above the 10^25 FLOP threshold file their first systemic-risk evaluations; first inspection wave with 24 national authorities",
  "https://digital-strategy.ec.europa.eu/en/news/commission-starts-enforcing-ai-act-rules-and-new-transparency-requirements-2-august", "ai-regulation-teeth"),
 ("2026-09-15", "Matt Sheehan (Carnegie): China diffuses compute to applications rather than consolidating behind one lab; the race model lacks its US chokehold there",
  "https://youtu.be/U2O0sdpuFRQ", "ai-china-strategy"),
 ("2026-09-15", "Reported: autonomous AI agents compromise other AI companies — incidents at OpenAI, Anthropic and Meta; New York enacts a one-year data centre moratorium",
  "https://youtu.be/rbgvTlt1VB8", "ai-incident-severity"),
]


def collect_observed(rows):
    for d, item, src, obs in OBSERVED:
        rows.append({
            "type": "observed",
            "item": item,
            "date_raw": d, "date": d, "approx": False,
            "start": d, "end": d,
            "confidence": None,
            "observer": obs,
            "ref": "",
            "source": src,
        })


def build(out_path: Path) -> None:
    rows = []
    collect_observed(rows)
    collect_consequences(rows)
    collect_expert_claims(rows)
    collect_joint_claims(rows)

    for r in rows:
        r["future"] = bool(r.get("end") and r["end"] > BUILT)
    rows.sort(key=lambda r: (r.get("end") or r.get("date") or "9999", r["item"][:40]))
    for i, r in enumerate(rows, 1):
        r["id"] = "tl%03d" % i

    by = {}
    for r in rows:
        by[r["type"]] = by.get(r["type"], 0) + 1

    payload = {
        "spec": "fleet-timeline-v1",
        "built": BUILT,
        "note": ("Past events and forward expectations from the AI monitoring fleet. "
                 "FOUR ROW TYPES, deliberately not merged: 'observed' are dated facts with "
                 "a source; 'model-expect' are numbered consequences a model ASSERTS (no "
                 "probability — the kinds do not produce one); 'expert-claim' are dated "
                 "claims by named commentators, registered before resolution with criteria "
                 "we wrote, not theirs; 'joint-claim' are brainstorm synthesis claims and "
                 "are the ONLY rows carrying a number — an LLM panel's confidence, not a "
                 "calibrated forecast. Every future row is a WINDOW (start..end), not a "
                 "point: 'by <date>' means any time up to that date. NOTHING IS GRADED — "
                 "every future row is open."),
        "counts": by,
        "future": sum(1 for r in rows if r["future"]),
        "past": sum(1 for r in rows if not r["future"]),
        "with_probability": sum(1 for r in rows if r.get("confidence") is not None),
        "timeline": rows,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    print("[fleet-timeline] %d rows -> %s" % (len(rows), out_path))
    for k, v in sorted(by.items()):
        print("    %-14s %d" % (k, v))
    print("    past %d · future %d · with a probability %d"
          % (payload["past"], payload["future"], payload["with_probability"]))
    horizon = [r["end"] for r in rows if r["future"] and r.get("end")]
    if horizon:
        print("    horizon: %s .. %s" % (min(horizon), max(horizon)))


def main():
    ap = argparse.ArgumentParser(description="Build the fleet timeline (past + future).")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "timeline.json"))
    a = ap.parse_args()
    if not a.build:
        ap.print_help()
        return
    build(Path(a.out))


if __name__ == "__main__":
    main()
