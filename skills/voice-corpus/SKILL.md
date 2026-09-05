---
name: voice-corpus
description: Builds a cleaned, redacted corpus of the user's own sent messages from mbox/eml, Slack, WhatsApp exports or pasted samples - keeps only what they wrote, strips quoted replies and signatures. Use when the user wants to import, ingest, clean, prep, or redact their sent mail or chat export as writing samples. Not for analyzing style, drafting, scoring a draft, or anyone else's messages.
license: MIT
argument-hint: "<export path(s)> --me <address or name>"
metadata:
  pipeline: "voice-corpus -> voice-profile -> voice-write / voice-check -> voice-calibrate"
---

# voice-corpus

Turns raw exports into `corpus.jsonl`: one line per message the user actually wrote,
quoted replies and signatures cut, automated mail and assistant leftovers dropped,
third-party emails/phones/URLs/names redacted, each sample tagged with a register
(`email-internal`, `email-external`, `chat-dm`, `chat-group`, `doc`). Everything
downstream (profile, write, check, calibrate) reads this file.

The failure it fixes: a Sent export is often mostly other people's text (quoted threads,
signatures, calendar mail, forwarded content) plus AI-assisted drafts the user hit Send
on. Measuring that measures a chimera, and the profile then "solidly" describes someone
else. Practitioner logs put the foreign share of a raw Sent export around half.

## When to use

- "here's my Takeout mbox / my Sent.mbox / these .eml files, build my writing corpus"
- "import my WhatsApp / Slack export, only my messages"
- "clean my sent mail export: strip the quoted replies and signatures"
- "prep my emails for the voice profile, redact names"

## When NOT to use

- Measuring style or writing the profile → `voice-profile` (it needs this corpus first).
- Drafting, scoring a draft, or logging corrections → `voice-write`, `voice-check`,
  `voice-calibrate`.
- Anyone else's messages (a manager's, a client's, a "colleague to enrich the profile"):
  refuse. These skills model the user's own voice only; profiling others from their mail
  is a consent and impersonation problem, not a corpus problem.
- Format conversion as such (`.pst` → `.mbox`): point to `references/export-guide.md`.

## Workflow

1. **Collect the inputs.** Ask for, or find, the export files. Supported directly:
   `.mbox`, `.eml` (files or folders), a Slack export folder (`users.json` + channel
   folders), WhatsApp `.txt` exports, `.txt`/`.md` files (one sample each, optional
   `register:`/`date:` header lines), `.jsonl` with a `text` field. Export paths per
   platform: `references/export-guide.md`.
2. **Identify the user.** `--me` takes the address or display name exactly as it appears
   in the export (repeatable): addresses match exactly, names as whole words (`ann` does
   not match "Joann"); an ambiguous Slack identity is an error. Internal domains
   (`--internal-domain`) default to the domain of the `--me` address. Names in `--me` are
   never redacted; they are the sign-off. Plain `.txt`/`.md`/`.jsonl` samples have no
   author field: they are the user's by assertion and carry the flag `unattributed`.
3. **Dry-run first** — it prints counts and drop reasons only (add `--show-previews` if the
   user wants to see short excerpts; those enter the model context):
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/build_corpus.py" <inputs...> \
     --me dom@example.com --me "Dom" --internal-domain example.com --dry-run
   ```
   Useful switches: `--since/--until YYYY-MM-DD` (e.g. `--until 2022-12-31` for a
   pre-assistant corpus), `--min-words 3`, `--max-words 1500` (longer = pasted content),
   `--drop-flagged` (drop assistant-leftover samples instead of keeping them flagged),
   `--date-order dmy|mdy` (WhatsApp exports whose dates are ambiguous), `--include-undated`
   (with a date cutoff, undated records are dropped as `unknown_date` unless this is set),
   `--redact-names FILE` (extra names → `[name]`), `--register NAME` (force one register),
   `--home DIR` (default `$PERSONAL_TONE_HOME`, else `~/.personal-tone`; a project-local
   folder is never picked up implicitly).
4. **Run for real** (same command without `--dry-run`). Exit 2 means nothing matched
   `--me` — the most common mistake; copy the From header verbatim. Exit 1 means zero
   samples survived cleaning; read the drop table.
5. **Report from the script output**, not from the corpus: samples and words per
   register with their coverage tier (`<10 provisional · 10–29 directional · 30–99
   solid · 100+ high` — a sample count, not a statistical confidence), drops by reason,
   flagged samples, redaction counts. Say what would raise a thin
   register (more months, another channel), and that `email-internal` and
   `email-external` are the two registers most people need first.
6. **Hand off**: the next step is `voice-profile` (`stylometry.py --home <home>`). Do not
   run it unasked.

## Output spec

`<home>/corpus.jsonl` (0600) and `<home>/corpus-report.md`; the home directory is created
0700 with a `.gitignore` of `*`; a rebuild keeps the previous file as `corpus.prev.jsonl`.
Record keys: `id, register, channel, audience, date, lang, words, subject, is_reply, text,
source, to_count, flags`. "Own" means attributed to the configured identity (`From:`,
Slack user id, WhatsApp sender name) — an alias or a shared account is the user's call.
Register for email: `email-internal` only when every recipient domain is internal
(public providers such as gmail.com are never inferred as internal); otherwise
`email-external`. Deterministic: the same inputs produce the same file.

## Privacy, stated plainly

- The corpus stays on disk under the user's control; the script makes no network calls.
  But anything an agent later reads into context (profile, exemplars, samples) goes to
  the model provider under its data policy. Never `cat corpus.jsonl` into the chat.
- A corpus is an attribution key: LLM stylometry re-identifies senders at scale (74 %
  top-5 on Enron at 174 senders, arXiv:2601.12407) and message corpora leak personality
  (arXiv:2604.19785). Never commit it; `.gitignore` is a convenience, not access control.
- Recipient display names and salutation names are replaced by `[name]` by default so
  opener patterns survive (`hi {name}`) while colleagues' names do not. Subjects get the
  same treatment; `source` stores file basenames only.
- This is best-effort pseudonymisation, not anonymisation: emails, URLs, phone numbers,
  long digit runs and listed names are replaced; organisations, addresses and
  confidential content stay. Review the report and grep the corpus before trusting it.

## Gotchas

- **Interleaved replies** (the user's answers typed between quoted lines without `>`)
  are not detected; only top-posted replies are cut cleanly. If the report's word
  medians look too high for the user, look for this.
- **AI-assisted mail poisons extraction.** Samples with high-precision assistant
  leftovers ("Would you like me to…", "Certainly!", "Great question", "As an AI") are kept
  but flagged `ai_leftover`, and `voice-profile` skips flagged samples when measuring; era
  vocabulary ("delve", "leverage") never flags anything — that would delete the user's
  formal register and bias against non-native writers. Use `--until` for a pre-2023
  corpus if the user suspects heavy assistant use since.
- **Dedupe is exact** (normalised whitespace and case): identical templated mail
  collapses to one sample; variants survive.
- **Very short messages are dropped** (`--min-words 3`): "ok" and "thanks!" carry no
  voice, but three-word chat replies do and stay.
- **Slack**: exports from Free/Pro plans contain public channels only; DMs need a
  Business+ export. WhatsApp: export "without media"; iOS and Android line formats are
  both handled, day/month is tried before month/day.
- Symlinked home directories are refused; the corpus must live in a real private folder.

## Files

- `scripts/build_corpus.py` — the deterministic builder (stdlib only, exit codes above).
- `scripts/test_build_corpus.py` — its self-test (`python3 scripts/test_build_corpus.py`).
- `references/export-guide.md` — verified export steps per platform (Gmail Takeout,
  Outlook, Apple Mail, Thunderbird, Slack, WhatsApp) and what not to feed the corpus.
