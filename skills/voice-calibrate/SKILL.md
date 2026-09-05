---
name: voice-calibrate
description: Logs draft-versus-sent pairs and corrections to the user's writing voice, tags what changed, and promotes recurring corrections to rules only when the user confirms. Use when the user says here's what I actually sent, that was too formal remember that, I never sign off like that, ban it or never-list it, or what keeps getting corrected. Not for building the profile, drafting, or scoring a draft.
license: MIT
argument-hint: "--draft FILE --sent FILE [--reason ...]"
metadata:
  pipeline: "voice-corpus -> voice-profile -> voice-write / voice-check -> voice-calibrate"
---

# voice-calibrate

"The gap between the draft and the send is your voice." This skill records that gap —
what was removed, what was added, how the measurements moved, and the reason the user
gives — and turns *recurring* corrections into confirmed rules. Two things it refuses
to do: change the profile from a single edit, and change it without the user saying yes.

Why: corrections are otherwise lost between sessions; a one-off edit generalised into a
rule distorts the profile; and stored draft-vs-edit pairs with the user's stated reason
are the highest-value signal for the next draft (PersonaMail, IUI '26,
arXiv:2602.17340: reuse of edit-derived strategies cut total drafting time 42 %, n = 16).

## When to use

- "here's what I actually sent", "I edited your draft — learn from it"
- "that was too formal / too long, remember that", "I never say X, cut it always"
- "what keeps getting corrected?", "make 'I hope this finds you well' a rule"

## When NOT to use

- First profile or a full rebuild from the corpus → `voice-profile`.
- Drafting → `voice-write`; judging a draft → `voice-check`.
- Fact corrections (a date, a name, an amount) are not voice: log them tagged `FACT`,
  never mine rules from them.
- Generic "which email is better" or file diffs → not this skill.

## Workflow

1. **Log the pair.** Save the draft and the sent text to files, then:
   ```bash
   work=$(mktemp -d)   # private scratch files; delete when done
   python3 "${CLAUDE_SKILL_DIR}/scripts/delta.py" --draft "$work/draft.md" --sent "$work/sent.md" \
     --register email-external --reason-file "$work/reason.txt" [--tags FACT] [--metrics-only]
   ```
   Put the reason in a file (`--reason-file`) rather than on the command line: reasons are
   user text and must never be interpolated into a shell string. `--metrics-only` stores
   tags and metrics without diff lines when the pair is sensitive.
   The script prints the metric deltas (words, paragraphs, contractions, politeness
   markers, hedges, opener and sign-off classes), the auto tags (`LENGTH_CUT`,
   `LESS_FORMAL`, `OPENER`, `SIGNOFF`, `LLM_ISM`, `STRUCTURE`, `HEDGE_CUT`, …) and the
   removed/added lines. Report those; add the user's reason if they gave one — it is the
   most useful field.
2. **Explicit corrections** ("I never write 'I wanted to reach out'") are logged the same
   way with the offending sentence as the draft and the fix as the sent text, or promoted
   directly (step 4) when the user is unambiguous.
3. **Report** on request or after every ~5 entries:
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/delta.py" --report [--register R]
   ```
   Recurring removed phrases (≥ 2 independent entries) are ban candidates; recurring
   added phrases are keep candidates; tag counts show the dominant correction. Suggest
   putting the dominant correction into the next `voice-write` brief until the profile
   is rebuilt.
4. **Promote only on confirmation.** Show the exact phrase and scope, get a yes, then:
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/delta.py" --promote-ban "i hope this finds you well" \
     --scope email-external --confirm       # --scope defaults to all; use the register the correction came from
   python3 "${CLAUDE_SKILL_DIR}/scripts/delta.py" --promote-keep "thx" --confirm
   ```
   Without `--confirm` the script only says what it would do. Every promotion snapshots
   `profile.v<N>.json` first; rollback is copying it back over `profile.json`. An explicit
   standing instruction from the user ("never sign off with Best regards") may be promoted
   directly — that is the user's rule, not an inference; inferred rules need recurrence.
5. **Rebuild when the log says so**: many `LENGTH_*` or `*_FORMAL` entries in one
   register mean the bands are stale or the corpus was thin — run `voice-profile` on a
   refreshed corpus rather than stacking rules.

## Output spec

One appended line in `<home>/calibration.jsonl` per pair (0600; removed/added lines,
metrics, tags and the reason, all with emails/URLs/phones redacted — the diff lines are
still message content, so use `--metrics-only` for sensitive pairs; full texts only with
`--keep-text`); on `--report`, tag counts, recurring phrases and reasons; on
`--promote-* --confirm`, an updated `profile.json` plus a snapshot.

## Gotchas

- **A single edit is not a rule.** The report needs the phrase in ≥ 2 entries; identical
  pairs logged twice count once. Even then the user confirms — repeated edits can be
  task-specific or from one recipient.
- **Reasons beat diffs.** "concise" often means "no pleasantries", not "shorter"; ask for
  the reason when it is missing.
- The log describes whom the user softens for and where they cut — a map of their
  relationships. It lives in the 0700 home, is never committed, full texts are off by
  default, and the user can delete lines from it or the whole file at any time.
- A mixed edit (a date fixed *and* a sentence cut) tagged `FACT` is excluded whole; log
  the style part separately if it matters.
- Promotions add bans with `source: calibration`; `voice-profile` re-runs keep them.
- Needs `voice-profile/scripts/stylometry.py` next to this skill.

## Files

- `scripts/delta.py` — log / report / promote (append-only, snapshots).
- `scripts/test_delta.py` — self-test.
- `references/calibration.md` — tag definitions, the recurrence rule, log schema, and
  the evidence.
