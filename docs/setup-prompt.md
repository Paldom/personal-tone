# Setup prompt — build your voice profile and write with it

Paste the `/goal` block below into a Claude Code session with the personal-tone skills
installed (`npx skills add Paldom/personal-tone`). Replace the `<...>` placeholders first.
The goal runs the pipeline in its designed order — corpus → profile → check self-test →
one supervised draft — and stops at every point where consent matters: which samples go
in, which bans become rules, what goes into the model's context.

```text
/goal Build my writing-voice profile from my own sent messages and prove it can draft in my voice. Work autonomously except where a step below says ASK. Never send, post or reply anywhere on my behalf; never commit anything; never read corpus.jsonl or metrics.json into the conversation - use the scripts' summaries.

INPUTS: <paths to exports, e.g. ~/Downloads/Takeout/Mail/Sent.mbox, ~/exports/slack/, "~/exports/chat with Anna.txt">
ME: <your address(es) and display name exactly as in the exports, e.g. dom@example.com "Dom Pal">
INTERNAL DOMAINS: <example.com>
HOME: <~/.personal-tone or a project-local .personal-tone>
FIRST DRAFT BRIEF: <one message you need this week: recipient relationship, channel, the ask, the facts>

Method (order is a constraint; one step at a time, no parallel agents - every step writes to the same HOME):
1. voice-corpus: dry-run first with INPUTS, ME and INTERNAL DOMAINS; show me the per-register counts and the dropped-examples list; ASK before the real run if any register is provisional or a drop reason exceeds a third of the input. Then run for real.
2. voice-profile: run the measurement with --write-profile --exemplars; report the summary table and WARN lines; ASK me to confirm the never-candidates that become bans and any nonstandard forms to keep; write profile.md from the numbers only (no adjectives, no signature-move instructions); annotate the exemplar ids.
3. voice-check --selftest on every register and tell me the FAIL and WARN rates on my own samples; if FAIL is above 2% on any register, stop and show me why before continuing.
4. voice-write: draft FIRST DRAFT BRIEF using pick_exemplars for the right register (--reply-to if it is a reply), under the length and skeleton locks, facts only from the brief with [?] for unknowns; run voice-check with --brief and --exemplars; fix FAILs (two passes max) and show me the draft with the verdict. Do not send it.
5. Verification bracket: re-run make-style checks by running each skill's self-test script (test_build_corpus.py, test_stylometry.py, test_voice_check.py, test_pick_exemplars.py, test_delta.py) and voice-check --selftest again; all must pass.
6. Final report: registers with sample counts and tiers, the bans I confirmed, the self-test rates, the draft plus its check verdict, what stays local and what was read into context, and the exact voice-calibrate command to run once I have sent my edited version.

Definition of Done:
- HOME contains corpus.jsonl, corpus-report.md, metrics.json, profile.json, profile.md, exemplars.json, all mode 0600 in a 0700 directory with a .gitignore of *
- every register's tier is stated; provisional registers have no rules
- bans and keeps in profile.json are only the ones I confirmed
- voice-check --selftest FAIL rate <= 2% per register
- one draft passed voice-check (no FAIL) and I saw it before anything else happened with it
- nothing was sent, posted or committed
```

## Notes

- The block is about 2,900 characters, under the 4,000-character `/goal` limit.
- Steps 1–3 run once per corpus; step 4 is the daily loop (`voice-write` → your edit →
  `voice-calibrate --draft --sent --reason`). After ~10 calibration entries, ask for
  `voice-calibrate --report` and rebuild the profile from a fresh export every few months.
- Parallel agents are not safe here: all five skills write to the same home directory.
- If you do not want your samples in the model's context, add `--minimal` to step 4; the
  draft will match structure, length and bans, but less rhythm.
- Exports: see `skills/voice-corpus/references/export-guide.md` for Gmail Takeout,
  Outlook, Apple Mail, Thunderbird, Slack and WhatsApp.
