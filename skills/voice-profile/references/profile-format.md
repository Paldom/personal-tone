# Profile format and evidence

**Contents:** [profile.json](#profilejson-canonical) · [profile.md template](#profilemd-template) ·
[Feature definitions](#feature-definitions) · [Thresholds](#thresholds-repo-defaults) ·
[Evidence](#evidence)

## profile.json (canonical)

Written by `stylometry.py --write-profile`; read by voice-write, voice-check, voice-calibrate.
Never edit numbers by hand — rebuild from the corpus. `bans` and `keep` survive rebuilds.

```json
{
  "version": 2, "generated": "2026-09-05T10:14:00+00:00", "metrics_version": 3,
  "corpus": {"samples": 45, "words": 957, "tier": "solid"},
  "registers": {
    "email-external": {
      "channel": "email", "samples": 39, "words": 887, "tier": "solid",
      "reply_share": 0.46, "subject_words_median": 2, "lexicon_reliable": true,
      "bands": {"words": {"p10": 13, "p50": 25, "p90": 29, "mean": 22.7, "msg_share": 1.0},
                "paras": {...}, "sentences": {...}, "sent_len_mean": {...},
                "contractions_per_100w": {...}, "hedges_per_100w": {...}, "polite_per_100w": {...},
                "question_share": {...}, "exclaim_share": {...}, "lowercase_start_share": {...},
                "em_dash_count": {...}, "emoji_count": {...}, "ai_vocab_count": {...}},
      "greeting_share": 0.87, "signoff_share": 1.0,
      "greeting_classes": [["hi", 25, 0.64], ["hey", 9, 0.23], ["none", 5, 0.13]],
      "signoff_classes": [["best", 15, 0.38], ["thanks", 13, 0.33], ["name-only", 11, 0.28]],
      "openers": [["hi {name}", 25, 0.64], ...],
      "signature_moves": [{"kind": "opener", "pattern": "hi {name}", "count": 25, "share": 0.64}],
      "never_candidates": {"confidence": "ok", "terms": ["i hope this email finds you well", ...]}
    }
  },
  "all": { "...same shape, whole corpus..." },
  "bans": [{"term": "i hope this email finds you well", "scope": "all", "source": "user-confirmed", "added": "..."}],
  "keep": [{"form": "thx", "source": "user-approved", "added": "..."}],
  "notes": [], "_snapshot": 0
}
```

- `bands.<feature>`: per-message distribution — p10/p50/p90, mean, and `msg_share` (share of
  messages where the feature is > 0; the right statistic for zero-heavy features such as em
  dashes and emoji).
- `greeting_classes` / `signoff_classes`: `[class, count, share]`. Classes: greeting word
  (`hi`, `hey`, `hello`, `dear`, `good`, …) or `none`; sign-off keyword (`best`, `thanks`,
  `cheers`, `best regards`, …), `name-only`, or `none`.
- `signature_moves`: only when the register has ≥ 20 samples and the move appears ≥ 3 times
  (openers/sign-offs ≥ 5 % of messages, starters ≥ 10 % of sentences). A budget for the
  checker, never an instruction for the writer.
- `never_candidates`: AI-default phrases and words *absent* from this register. Proposals.
  `confidence` is `none` below 10 samples, `low` below 25, else `ok`.
- `lexicon_reliable`: false when fewer than 70 % of the register's samples are English; the
  checker then skips contraction/hedge/politeness/AI-vocabulary bands.

## profile.md template

Keep it under ~120 lines. voice-write loads one register block, not the file.

```markdown
# Voice profile — <first name>   (built <date> from <N> samples / <W> words; tier <tier>)

Languages: <en 92 %, hu 8 %>. Keep (user-approved): <thx; lowercase chat openers>.
Never (user-confirmed bans): <"I hope this email finds you well"; "please do not hesitate">.

## email-external  (<n> samples, <tier>; replies <r> %)
- Length: median <p50> words, p90 <p90>; <p90_paras> paragraph(s). Subject lines ~<k> words.
- Opens: hi {name} <64 %> · hey {name} <23 %> · no greeting <13 %>.
- Closes: Best, <38 %> · Thanks, <33 %> · name only <28 %>. First name only, never full name.
- Sentences: median <m> words; questions <q> % of sentences; no exclamation marks.
- Contractions <c>/100w (uses them); hedges <h>/100w; politeness markers <p>/100w (none).
- Structure: the ask in sentence one; context after; one paragraph; no bullets.
- Avoid here: <never-candidates the user endorsed>.

## chat-dm  (<n> samples, <tier>)
- Length: median <p50> words, p90 <p90>; one line. No greeting, no sign-off.
- Lowercase starts <l> %; "thx"/"pls" are normal here; one emoji in <e> % of messages.
- Answers first, reason second; questions as "quick q:".
```

Rules are constraints phrased from the numbers ("under 30 words", "no greeting in 13 %",
"never X"). No identity paragraph, no adjectives, no "signature moves to use".

## Feature definitions

Computed on the *body* (greeting line and sign-off/name lines removed). Rates per 100 body
words unless stated. Sentence split is a regex on `.?!…` and newlines (initials and "e.g."
over-split; accepted).

| feature | meaning |
| --- | --- |
| `words` | all words of the message incl. greeting/sign-off |
| `paras` | blank-line separated blocks in the body |
| `sent_len_mean` | mean words per body sentence |
| `contractions_per_100w` | `n't`, `'re`, `'ve`, `'ll`, `'d`, `I'm`, `it's`, … |
| `hedges_per_100w` | closed list: might, maybe, perhaps, probably, I think, sort of, … |
| `polite_per_100w` | formal request markers: "I wanted to", "reach out", "kindly", "regarding", "please find", … |
| `question_share`, `exclaim_share` | share of body sentences ending in `?` / `!` |
| `lowercase_start_share` | share of body sentences starting lowercase |
| `em_dash_count`, `emoji_count` | counts; compared by presence (`msg_share`) |
| `ai_vocab_count` | hits from the AI-default word/phrase reference list |
| `greeting_class`, `signoff_class`, `opener` | see above; `opener` normalises names to `{name}` |

Aggregate-only (in `metrics.json`, not used per draft): n-grams, top words, boosters,
adverb rate, average word length, sentence-length spread, bullet share.

## Thresholds (repo defaults)

| constant | value | why |
| --- | --- | --- |
| tiers | <10 provisional · 10–29 directional · 30–99 solid · 100+ high | engineering defaults; see Evidence for the shape |
| never-candidates | ≥ 10 samples (low confidence < 25) | zero in 10 messages bounds a per-message rate only loosely (rule of three ≈ 30 %) — hence proposals only |
| signature move | register n ≥ 20, count ≥ 3, share ≥ 5 % (starters ≥ 10 %) | below that one thread can create a "signature" |
| lexicon reliability | ≥ 70 % English samples | lexicons are English |
| bands | per-message p10 / p50 / p90 | a single draft is compared to what single messages look like, not to a corpus mean |

## Evidence

- Quantitative features + model interpretation beat model-only style description; lexical
  features carry most signal; qualitative comparison hallucinated differences between
  near-identical texts — Zhang & Zhang, "Assessing Deanonymization Risks with
  Stylometry-Assisted LLM Agent", arXiv:2602.23079 (2026).
- ~5 in-context samples is the tested default for imitating an author; 2→10 changes little;
  imitation works for email/news, fails for informal forums — Wang et al., "Catch Me If You
  Can? Not Yet", EMNLP 2025 Findings, arXiv:2509.14543.
- Fine-tuning fidelity: 25 emails ≈ 90 % of max BLEU, saturation by ~75–100 emails (a
  fine-tuning curve, not a stylometric confidence tier) — Panza, arXiv:2407.10994.
- Structure of a persona profile matters more than volume (+1.91 pp for a schema over raw
  transcripts on a homogeneous benchmark; no gain on heterogeneous tasks) — Ye, Deng &
  Candogan, arXiv:2608.20344.
- Separate a bounded behaviour/style track with correction history from capability —
  COLLEAGUE.SKILL, arXiv:2605.31264 (architecture precedent; it claims no fidelity result).
- A stored profile is an attribution key: 74 % Rank@5 sender identification on Enron at
  174 senders — "De-Anonymization at Scale via Tournament-Style Attribution",
  arXiv:2601.12407, ACL 2026. Chat corpora leak personality — arXiv:2604.19785.
- Contraction rates differ ~25× across current models (model idiolects) — Rudnicka & Juzek,
  arXiv:2608.06589. Re-check after model upgrades.
- Practitioner failure logs (multiple independent build logs, 2025–2026): caricature from
  majority rules, format conventions mistaken for voice, AI-assisted samples poisoning
  extraction, "never" lists more valuable than "always" lists.
