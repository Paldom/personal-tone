# Drafting rules and evidence

**Contents:** [Brief template](#brief-template) · [The locks](#the-locks) ·
[High-stakes list](#high-stakes-list) · [What goes into context](#what-goes-into-context) ·
[Evidence](#evidence)

## Brief template

Ask for what is missing, at most three questions, bundled:

```
Ask:        what must this message achieve (one line)
To:         relationship (peer / senior / report / client / vendor / friend) + channel → register
Facts:      names, dates, numbers, commitments that MUST appear (everything else gets [?])
Reply to:   the incoming message, verbatim, if this is a reply
Constraints: anything the user wants this time ("under three lines", "firm on the deadline")
```

## The locks

| lock | rule | catches |
| --- | --- | --- |
| skeleton | copy greeting class, sign-off class and paragraph count of the closest-length sample | 3-paragraph LLM email, "Dear" openers, "Best regards" sign-offs |
| length | ≤ `max_words` (register p90, or 1.5× the incoming message for replies); the checker fails above p90 × 1.25 | ~2.7× length inflation |
| facts | only from the brief; `[?]` for unknowns | invented dates, commitments, copied names |
| bans | none of `bans`; avoid never-candidates | "I hope this email finds you well" |
| no performance | no signature moves on purpose; no manufactured typos/slang; nonstandard forms only from `keep` | caricature, fake humanity |
| wrapper | register changes the wrapper, never the content | a softened decline that no longer declines |
| reply length | within ±50 % of the incoming message | lecture / brush-off |

Two check passes maximum. If the second pass still FAILs on a class or length finding,
present the draft with the finding named rather than looping into sludge.

## High-stakes list

Resignation, HR complaints, legal or contractual commitments, condolences, apologies for
harm, conflict escalation, money. Say it is high-stakes, draft minimal, recommend the user
writes the first and last line, never auto-send.

## What goes into context

- One register block of `profile.md`, `bans`, `keep`.
- Up to five samples from `pick_exemplars.py` (`--minimal` prints none).
- Never `corpus.jsonl`, `metrics.json`, or the whole profile. Everything printed is sent to
  the model provider under its data policy — the disk is local, the inference is not.

## Evidence

- Generic LLM email vs human email: ~2.7× the words (193 vs 73 on average), far more
  formal, more "we", fewer past/future references; readers rated it "unnecessarily wordy"
  (83 %) — Li, Lai, Soni & Saha, "Emails by LLMs", WebSci '25, DOI 10.1145/3717867.3717872.
- Prompting a model to sound human does not remove its stylistic differentiators; genre and
  model matter more than the prompt — Rallapalli et al., arXiv:2604.14111.
- Topic-narrow exemplars reduce stylistic diversity; ~5 exemplars suffice; seeding with the
  author's first ~50 words helps perceived human-likeness — Wang et al., arXiv:2509.14543.
- Retrieval of the author's own emails beat a textual profile in production (Shortwave
  Ghostwriter engineering talk, 2024) — practitioner evidence, not a study.
- Heavy AI assistance costs trust: manager messages rated sincere fell from ~83 % (low
  assistance) to 40–52 % (high), professional from ~95 % to 69–73 %, while still rated more
  effective — Cardon & Coman, *International Journal of Business Communication* 2025, DOI
  10.1177/23294884251350599 (n = 1,100 professionals).
- Uncanny valley: a profile that is "almost right" felt worse to users than a generic
  response — Shang et al., ASPECT, arXiv:2603.26922 (n = 20).
- Caricature is the most-reported practitioner failure ("one 'So,' opener becomes every
  opener"); fixes that worked: anti-performative rules, ordinary samples next to
  distinctive ones, rules as diagnostics not commandments (independent build logs,
  2025–2026).
