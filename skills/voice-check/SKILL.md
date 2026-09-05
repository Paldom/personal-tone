---
name: voice-check
description: Detect-only - scores a draft against the user's writing-voice profile (length, opener/sign-off class, bans, caricature, unbriefed identifiers). Use when the user asks does this sound or read like me, would I have written this, is this how I usually write, check or score a draft against my voice, or run the self-test. Not for rewriting, profile building, voice recordings, or AI-slop linting.
license: MIT
argument-hint: "<draft file> --register <register>"
metadata:
  pipeline: "voice-corpus -> voice-profile -> voice-write / voice-check -> voice-calibrate"
---

# voice-check

Answers "would I have written this?" with measurements instead of a hunch. A model
judging holistically is style-biased and inconsistent; the script compares one draft
with the per-message distributions of the user's own register and reports exactly what
is off. It never rewrites.

## When to use

- "does this sound like me?", "check / score / verify this draft against my voice",
  "run the voice check", "is this too formal *for me*?"
- As the gate inside `voice-write`, and in the setup prompt's verification bracket.

## When NOT to use

- Any rewrite ("make it sound like me") → `voice-write`.
- "does this sound like AI?" in general → an AI-slop linter; this checks against *one
  person's* profile, not a generic tell list.
- Grammar, spelling, "is it professional", "is it too long in general" → not voice.
- No `profile.json` → `voice-corpus` + `voice-profile` first. If the user insists on an
  opinion anyway, give it labelled "unmeasured" — never present it as a check result.
- Recorded or spoken voice, "does this sound friendly", "is this too long in general" →
  not this skill.

## Workflow

1. Save the draft to a file (temp is fine). Decide the register from the recipient and
   channel; when unsure ask, or pass the closest one — the script falls back to the same
   channel, then to all-corpus bands, and says so.
2. Run (`--register` is required: register-scoped bans are judged against the register
   you ask for, even when statistics fall back to another one):
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/voice_check.py" draft.md --register email-external \
     [--brief brief.md] [--exemplars picks.json] [--json]
   ```
   An incompatible or malformed `profile.json` exits 2 with a one-line error — rebuild it
   with voice-profile rather than working around it.
   `--brief` enables the unbriefed-identifier check (names, dates, numbers, URLs in the
   draft but not in the brief); `--exemplars` (JSON from `pick_exemplars.py`) enables the
   copied-span check.
3. Report the verdict and the findings, grouped by severity (precedence FAIL > WARN >
   INCONCLUSIVE > PASS; exit 1 only on FAIL, exit 2 on configuration errors):
   - **FAIL**: a user-confirmed ban; length > p90 × 1.25; paragraphs > p90 + 1; an opener
     or sign-off class the user has *never* used in a register of ≥ 60 samples. Length,
     paragraph and class failures need a register with ≥ 10 samples and no fallback —
     otherwise they are reported as WARN.
   - **WARN**: a band exit on a short list of features (sentence length, contractions,
     hedges, politeness markers, question/exclamation share, lowercase starts); a rare
     (< 5 %) or, below 60 samples, never-seen opener/sign-off class; an AI-default phrase
     absent from the corpus (never-candidate, advisory until confirmed); caricature (a
     signature starter used twice, two distinct signature starters under 150 words, the
     same opening 3+ times, a repeated 4-gram); identifiers (names, dates, numbers, URLs)
     absent from the brief — an identifier check, not fact verification; copied 6-word
     spans from the samples; a profile older than 180 days.
   - **INCONCLUSIVE**: under 40 words the distribution checks are skipped; bans, length,
     classes and leakage still run, and a ban still FAILs.
   Quoted lines (`>`) in the draft are ignored; bans match as case-folded whole phrases,
   so ban phrases, not single common words ("best" would hit ordinary prose).
4. Do not fix the draft. Point at what would change the verdict and stop; the user (or
   `voice-write`) edits.
5. When asked whether the warnings can be trusted, run the self-test and read it out:
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/voice_check.py" --selftest --loo [--register R]
   ```
   `--loo` rebuilds each register without the sample being scored (honest for small
   corpora; without it the numbers are in-sample and only a floor). Report the overall
   FAIL/WARN/INCONCLUSIVE shares and the top finding types: a WARN type that fires on 20 %
   of genuine samples is noise for that register; FAIL should be near 0 % on registers
   with ≥ 30 samples. Short-message registers (chat) come back mostly INCONCLUSIVE — say
   that coverage is limited there rather than implying a score.

## Output spec

`VOICE CHECK: <verdict>` plus one line per finding with the measured value and the
user's band or class shares (`63 words — far above your p90 of 29`, `closes with "best
regards" — 0 % of your external mail; you use: best 38 %, thanks 33 %, name-only 28 %`).
`--json` gives `{verdict, register, fallback, flags[{check, severity, message, ...}]}`.

## Gotchas

- Thresholds are repo defaults, not universals; only the self-test tells you how they
  behave on this corpus. The bands are per-message p10–p90, so a genuine message lands
  outside one band roughly one time in five and outside *some* band more often — that is
  why band WARNs are advisory and only bans, length, paragraphs and never-seen classes
  can FAIL.
- Class checks need a register with ≥ 20 samples (WARN) and ≥ 60 to FAIL — with 0 of 60
  the true rate is below ~5 % (rule of three); with fewer, absence proves little. The
  default home is `~/.personal-tone`; pass `--home` for anything else so a shared working
  directory can never supply someone else's profile.
- Lexicon features (contractions, hedges, politeness, AI vocabulary) are English; the
  script skips them for registers the profile marks unreliable.
- Not an AI detector. Detectors false-flag non-native writers at ~61 % (Liang et al.,
  *Patterns* 2023); this tool compares against the user's own baseline only.
- Needs `voice-profile/scripts/stylometry.py` next to this skill (same repo install) or
  `PERSONAL_TONE_STYLOMETRY` pointing at it.

## Files

- `scripts/voice_check.py` — the checker (exit 1 on FAIL) and `--selftest`.
- `scripts/test_voice_check.py` — golden set: a genuine sample passes, a generic
  assistant rewrite fails, a caricature and a wrong-register opener are caught, copied
  spans and unbriefed names are flagged.
- `references/checks.md` — every check with its threshold, severity, rationale and
  evidence, plus the features deliberately excluded as noise on short text.
