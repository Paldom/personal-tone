# Calibration: tags, recurrence rule, log schema, evidence

**Contents:** [Tags](#tags) · [Recurrence rule](#recurrence-rule) · [Log schema](#log-schema) ·
[Evidence](#evidence)

## Tags

Auto-detected from the draft→sent metric deltas; the user can add any tag with `--tags`.

| tag | fires when |
| --- | --- |
| `LENGTH_CUT` / `LENGTH_ADD` | sent words < 70 % / > 130 % of the draft |
| `LESS_FORMAL` / `MORE_FORMAL` | contractions up / politeness markers down by > 1.5 per 100 words (or the reverse) |
| `OPENER` / `SIGNOFF` | greeting / sign-off class changed |
| `LLM_ISM` | fewer AI-default phrases in the sent text |
| `STRUCTURE` | paragraph count changed by ≥ 2 |
| `HEDGE_CUT` / `HEDGE_ADD` | hedges down / up by > 1.5 per 100 words |
| `FACT` (user) | a name, date, number or commitment was corrected — excluded from voice mining |
| `NOT_ME`, `WRONG_WORD` (user) | free labels for the report |

## Recurrence rule

- A phrase (3-gram) removed in ≥ 2 *distinct* entries is a ban candidate; added in ≥ 2 is a
  keep candidate. Identical pairs logged twice count once. Entries tagged `FACT` are skipped.
- Candidates are proposals. `--promote-ban/--promote-keep` without `--confirm` prints what
  would change; with `--confirm` it snapshots `profile.v<N>.json` and appends the rule with
  `source: calibration` and the given `--scope` (a register, or `all`). voice-check applies
  a ban only inside its scope.
- Explicit standing instructions from the user are not inferences and may be promoted
  directly; inferred rules need recurrence.
- Why two, not one: a single edit is often task- or recipient-specific. Why the user, not
  the count: repeated edits can be correlated (one thread, one bad week); the profile is
  theirs.

## Log schema

`calibration.jsonl`, one object per line, append-only, mode 0600:

```json
{"ts": "...", "version": 1, "register": "email-external", "tags": ["LENGTH_CUT", "LESS_FORMAL"],
 "reason": "too long, too polite", "similarity": 0.26,
 "draft": {"words": 63, "paras": 2, "contractions_per_100w": 0.0, "polite_per_100w": 10.5, "greeting_class": "hi", "signoff_class": "best regards", ...},
 "sent":  {"words": 16, ...},
 "removed": ["I hope this email finds you well. …"], "added": ["Can you send the Q3 numbers by Friday? …"],
 "status": "logged"}
```

`--keep-text` adds `draft_text` and `sent_text`; `--metrics-only` stores no diff lines.
Emails, URLs and phone numbers are redacted in every stored field including `reason`; names
are not — the user is reading their own drafts.

## Evidence

- Stored draft-vs-edit pairs with the user's stated reason, reused as strategies, cut total
  drafting time by 42 % and articulation time by 58.5 % vs a standard LLM email UI (n = 16,
  lab study) — Yao et al., PersonaMail, IUI 2026, arXiv:2602.17340. The same paper notes
  that such logs form a "social graph of vulnerability" (whom the user softens for) — hence
  local-only, minimal text, 0600.
- Practitioner rule "a single edit is not a rule; a pattern needs 2+ occurrences; show a
  changelog and wait for approval" (independent build logs, 2025–2026).
- Voices drift over months (a five-year mailbox analysis found the month hedges, exclamation
  marks and length changed) — practitioner evidence; hence periodic rebuilds rather than
  rule stacking.
