# The bypass role is parked — 2026-09-23

The three-role loop (extract → control → bypass) ran once. The BYPASS role
asks a model to produce a concrete, actionable route for defeating named
security controls, from the standpoint of an agent that has already
demonstrated intrusion behaviours. A safety classifier stopped that generation,
and correctly: it is a request for offensive technical instructions.

This is not a phrasing problem. The classifier fires on the TASK, so rewording
the prompt does not help and should not be attempted -- the useful signal is
that the exercise, as designed, asks for content that should not be generated.

## What survives, and is kept

- EXTRACTOR: reads an incident report, lists emergent behaviours a system BUILT
  (an invention, not a use of granted capability), quotes the evidence, and
  rules out what only looks emergent. This ran cleanly both times: 4 behaviours
  extracted, 4 correctly ruled not-emergent, on this report.
- DESIGNER: proposes controls per behaviour with layer, cost, and how you would
  know it works. Also ran cleanly.

The value the user asked for -- a list of risky emergent behaviours, and
possible controls -- comes from the first two roles. The third was meant to
pressure-test the controls, and that is the part that cannot be run this way.

## If the pressure-test is wanted later, without generating an attack

Options that do not ask a model to author a bypass:
- score a control against the behaviours it must stop using DEFENSIVE reasoning
  only: "does this control observe the earliest rung; if the rung is invisible,
  say so" -- a coverage check, not an attack
- have the designer state each control's OWN honest_gap (the field already
  exists) and treat the union of gaps as the residual risk, with no adversary
- read real published post-incident analyses where defenders describe what a
  control missed, and extract the gap from the record rather than inventing it

All three produce the residual-risk picture the loop was for, from defensive or
documentary sources rather than by generating offensive steps.
