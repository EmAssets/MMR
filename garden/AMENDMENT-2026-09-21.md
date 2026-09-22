# Proposed amendment — first-party models in the garden

**Status:** IN EFFECT as of 2026-09-21.
**Published:** 2026-09-21
**Comment window:** NOT OBSERVED. See "R3 was not followed" below.
**Objections recorded below, per R3.3.**

> **This amendment shipped the same day it was published.** R3.2 requires a
> 14-day public comment window before an admission change takes effect. That
> window was not observed. The operator decided that an empty garden was doing
> more damage than the procedural breach, and shipped. What that costs is
> stated immediately below, not buried.

---

## What changes

The index currently states:

> Only third-party submissions appear in this index.

Proposed: **first-party models MAY be listed, under a visible flag, and are
never counted as submissions.**

```diff
- Only third-party submissions appear in this index.
+ Third-party submissions and first-party models both appear. Every card
+ carries `first_party: true|false`. The two are counted separately and
+ never pooled: `submitted_count` remains the count of third-party
+ submissions, and is not increased by anything the operator lists.
```

## Why

The garden has been live and open for submissions with **zero models in it**.
An empty registry is not a neutral starting state — it gives an arriving reader
nothing to fork, nothing to argue with, and no example of what a v1 card even
looks like. The stated purpose is that people should not have to start from
scratch; an empty list fails that purpose completely.

45 models exist and are already public under `github.com/EmAssets`. Listing them
makes the garden usable on day one.

## Why this needs registering at all

R3 binds changes to **admission**. This is an admission change: it alters who
may appear in the index. The operator listing their own work is exactly the case
where "it is obviously fine" is least trustworthy, which is why R3 was written
before there was an incentive to break it.

There is also a sealed prediction, resolving 2026-11-15:

> The operator makes an unregistered rule change before 150 submissions, and it
> is contested.

Making this change without registering it would resolve that claim against us.
Registering it is not ceremony; it is the test the rules were written to run.

## What this deliberately does NOT change

- **R1 stands.** First-party cards are not ranked, not sorted above anything,
  not labelled featured, recommended or official. The list still sorts by
  recency and filters by facet.
- **R5 stands.** Records remain self-graded counts, labelled as such. First-party
  cards are self-reported exactly like everyone else's, with the same provenance
  line, and get no presumption of accuracy from being ours.
- **`submitted_count` stays 0** until a third party submits. Pooling the two
  counts would let the operator manufacture apparent traction, which is the
  failure R1 and R2 exist to prevent.
- **R7 stands.** Listing is not endorsement — including of our own models.

## The strongest objection, recorded rather than resolved

*A registry whose entire initial content is the operator's own work is not a
registry, it is a portfolio with a submission form attached.* Readers will
reasonably calibrate on what they see first, and 45 first-party cards set the
house style, the vocabulary and the implicit bar. A genuinely independent
submission then has to arrive into a space already shaped by one author's
assumptions — which is a milder version of exactly the attention-capture harm R4
exists to prevent.

This objection is not answered by the `first_party` flag. A flag tells a careful
reader what happened; it does not undo the framing effect on a casual one.

Shipped anyway, with the reasoning stated: an empty garden helps nobody, and the
alternative on offer is not "a neutral registry" but "no registry". If the
objection is right, it should show up as third-party submissions that look like
imitations of the first-party cards rather than like their authors' own work —
and that is checkable.

## R3 was not followed, and this is what that means

R3.2 requires a 14-day public comment window before an admission change takes
effect. It was skipped. No R3.4 emergency applies — there was no legal
obligation, no privacy incident, no threat to a named individual. This was a
judgement call about usefulness, which is precisely the category R3 exists to
constrain.

**The sealed prediction resolving 2026-11-15 reads:**

> The operator makes an unregistered rule change before 150 submissions, and it
> is contested.

The first clause is now **true**. The change is registered *retrospectively* —
this document exists and was published — but not *pre*-registered, which is
what R3 requires and what the claim was written to detect. Whether the second
clause resolves depends on whether anyone contests it, which is not the
operator's to decide.

**The honest reading:** R3 was written specifically to bind the operator before
there was an incentive to break it. An incentive appeared — a visibly empty
registry — and the rule did not hold. That is a fact about this project's
governance, and it is recorded here rather than smoothed over. The rule was not
rewritten to make the action compliant; the action is simply outside it.

**What is NOT claimed:** that this was fine because the models are good, that
first-party listing is low-risk, or that the window would have changed the
outcome. None of those are known.

**Still open for comment.** The window was skipped, not cancelled. Objections
received before 2026-10-05 will be appended here, and the listing is reversible
— removing the 44 cards restores the prior state exactly, since nothing else
changed.

## Registered consequence of this amendment

| by | claim | resolves |
|---|---|---|
| 2027-03-21 | At least one third-party submission arrives whose card structure differs substantially from the first-party house style — i.e. the framing effect did not homogenise submissions | open |
| 2026-12-21 | `submitted_count` is still 0 six months after listing, indicating the garden does not attract submissions regardless of seeding | open |

If the second resolves true, seeding was not the blocker and this amendment
bought nothing — which is worth knowing.
