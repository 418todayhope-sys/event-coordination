# Evidence and uncertainty

## Find and capture evidence

Use the original interview's disclosed links for the event brief/venue note in
Notion; attendee signals, vendor register, budget allocations, and calendar
constraints in Google Sheets; and the official venue 4F PDF and accessibility
index. Follow those intended access routes when retrieval is authorized. The
interview establishes requirements and routes, not verified spreadsheet figures
or proof that a venue satisfies them. Prior-run material is context, not automatic
proof of current suitability.

For each source, retain its stable ID, role, disclosed locator, actual retrieval
or attempt timestamp, retrieval status, content type, version metadata, content
hash, local reference, and observations as required by the schema. Preserve
original downloaded bytes, including media/PDFs where available, in
`evidence/originals/`; keep the inventory in `evidence/manifest.json` and derived
observations in `evidence/observations/` once capture is implemented. Hash exact
bytes with SHA-256; hash integrity does not establish truth or historical validity.
Keep extracted text and rendered views distinguishable from original downloads.

Attach observation IDs and precise locators: sheet tab and cells; section; PDF
page and region; or video timestamp. Inspect relevant visual media directly before
claiming spatial facts; text extraction alone may miss routes, symbols, or layout.
Separate what was observed from the resulting interpretation. Link derived
records to evidence IDs and retain the inputs and formula for calculations.

Record unavailable, invalid, unverified, or stale sources honestly. Null hashes
and local references are permitted for source records when bytes are unavailable.
Do not hash an error page and label it the requested PDF. If a failed response's
content type is unknown, document that uncertainty explicitly rather than claim a
verified MIME type. Leave observations empty when none were obtained. Record the
attempt time and explain failed retrieval in metadata/unresolved records. Never
substitute repository examples or invented observations for inaccessible sources.

## Apply the two clocks

Evaluate business conditions, including quote expiry, against
`2026-08-26T12:00:00+08:00` in `Asia/Taipei`. Use actual times for retrieval,
execution, snapshot creation, and generated calendar metadata such as DTSTAMP.
Use the evidenced event date for schedule entries. Do not backdate retrievals.

A source retrieved later may not describe its state at the business clock.
Retain effective dates/version history when available; otherwise flag temporal
applicability as unverified. If a quote gives only an expiry date and its cutoff
convention matters, disclose the ambiguity instead of inventing a time. Record
the applicable clock and rationale with validity judgments.

## Interpret the stakeholder's rules

- Success targets are 80% registered-attendee check-in, all fellow demos running,
  and a documented response to accessibility requests. Do not multiply headcount
  by 80% merely because it is the success target.
- Reconcile fellows, partners, staff, speakers, and forecast walk-ins as population
  groups. Preserve signal IDs, quantities, confidence, and source basis. Dietary
  and accessibility needs overlap the population; they do not add people.
- Preserve high/medium/low confidence as qualitative labels. Do not convert them
  to probabilities. Explain buffers, sensitivity scenarios, and refresh triggers
  as assumptions or proposals with rationale, not source facts.
- Hard accessibility requirements are step-free access to the program and
  restrooms, wheelchair seating, live captions, and a staffed quiet room. Verify
  each separately. A floor plan cannot alone confirm service staffing or captions.
- Setup is 07:30–09:30 and teardown 17:00–18:30 local time; vendors must clear by
  18:30. Check source-specific blackouts and access windows as well. A hard
  conflict remains infeasible until the responsible owner resolves it with evidence.
- Check quote service scope, capacity, and expiry, as well as venue seating and
  accessible arrangements. Familiar vendors are a preference. Do not assume
  familiarity identifies a specific vendor unless supported by evidence.
- Compare category allocations, commitments, approval limits, and the overall
  ceiling distinctly. Use decimal monetary calculations and evidenced currency,
  tax, fee, and unit assumptions. Missing charges are unknown, never free.

## Resolve uncertainty without hiding it

Classify records as facts, hard constraints, preferences, assumptions, unknowns,
or conflicts. Keep conflicting values with their sources and consequences; do not
silently average them or select the cheaper value. Give material gaps an owner
when known, a resolution action, affected dependencies, and a refresh trigger or
deadline where supported. Do not invent named owners or deadlines.

A verified hard violation makes an option infeasible. A specific unresolved
condition may make it conditional; insufficient evidence to test it makes it
unverified. Reserve feasible for supported satisfaction of applicable constraints
and identify spending approvals separately. Missing livestream network results
and unconfirmed venue status before walkthroughs are explicit gaps when relevant.
If a gap prevents a recommendation, leave it null and explain what would unblock it.
