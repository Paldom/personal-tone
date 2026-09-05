# Checks, thresholds, and what is deliberately excluded

**Contents:** [Check table](#check-table) · [Reading the self-test](#reading-the-self-test) ·
[Excluded features](#excluded-on-purpose) · [Evidence](#evidence)

## Check table

| check | severity | threshold | why |
| --- | --- | --- | --- |
| `ban` | FAIL | any user-confirmed ban term present (word-boundary, case-folded) | the only rules with explicit consent |
| `length` | FAIL / WARN | words > p90 × 1.25 / > p90 of the register's per-message distribution; FAIL needs ≥ 10 samples and no fallback | length inflation is the best-documented LLM tell |
| `structure` | FAIL | paragraphs > p90 + 1 (same conditions as length) | 3-paragraph LLM email vs 1-paragraph human email |
| `opener`, `signoff` | FAIL / WARN | never observed in ≥ 60 samples → FAIL; never observed in 20–59 or observed < 5 % → WARN | "Dear …" / "Best regards" where the user never does that; 0/60 bounds the true rate under 5 % (rule of three), a class seen once must not fail the sample that established it |
| `ai-default` | WARN | never-candidate phrase present | absent from the corpus, common in model output |
| `band` | WARN | value outside p10–p90 for: sentence length, contractions, hedges, politeness markers, question share, exclamation share, lowercase starts | advisory: a genuine message exits one band ~1 in 5 |
| `presence` | WARN | em dash / emoji present but in < 10 % of the user's messages | zero-heavy features compared by presence |
| `caricature` | WARN | a signature starter used ≥ 2× (share < 50 %); > 1 distinct starter under 150 words; same 2-word opening 3+ times | tics over budget |
| `repetition` | WARN | a 4-gram repeated inside the draft | template echo |
| `unbriefed` | WARN | capitalised names (not sentence-initial, not greeting/sign-off lines), dates, numbers ≥ 3 digits, URLs, emails absent from `--brief` | invented or copied identifiers — an identifier check, not fact verification |
| `exemplar-copy` | WARN | a 6-word span shared with a sample in `--exemplars` | content leakage from samples |
| `stale` | WARN | profile older than 180 days | voices drift |
| `bands` | INCONCLUSIVE | draft under 40 words | rates on 20 words are noise |

Exit code 1 only on FAIL, 2 on configuration errors (no/incompatible/malformed profile,
missing `--register`, unreadable inputs). Precedence FAIL > WARN > INCONCLUSIVE > PASS.
Register fallback: exact → same channel (largest) → `all` → largest; statistics from a
fallback or provisional (< 10) register never FAIL; ban scope is always judged against the
requested register. Quoted (`>`) lines are removed first. `--selftest --loo` skips samples
in registers with fewer than 3 samples and says how many.

## Reading the self-test

`--selftest` runs the checker over every corpus sample of the register (or all). Without
`--loo` it is in-sample (the bands were derived from these very messages), so it
*under*-estimates the false-alarm rate on new text — a floor. `--loo` rebuilds the register
without the scored sample each time (leave-one-out); use it for corpora under ~100 samples.
Expected:
FAIL ≈ 0 % (bans are absent from the corpus by construction, length p90 × 1.25 is above
almost all genuine samples, classes with ≥ 5 % mass pass); WARN types that fire on a large
share of genuine samples are noise for that register — say so when reporting a WARN of that
type on a draft. Many short-message registers come back mostly INCONCLUSIVE; that is
correct, not a defect.

## Excluded on purpose

Per-draft checks do **not** use: MATTR / type-token ratio (unstable under ~100 tokens),
pronoun ratios (noise on two sentences), boosters, comma/semicolon rates, long-sentence
share, n-gram drift, readability formulas, generic AI-vocabulary as a rate. They remain in
`metrics.json` for the profile narrative. Reviewer consensus (four independent model
reviews, 2026-09-05) and the short-text literature agree these produce false alarms on
40–200-word messages.

## Evidence

- Length and formality gap of generic LLM email — Li et al., WebSci '25 (see voice-write
  references).
- Holistic LLM judges are style-biased — "Style Wins, Substance Loses", arXiv:2608.01666;
  quantitative stylometry + LLM reasoning is the reliable combination — arXiv:2602.23079.
- Rule-of-three bound: zero events in n samples leaves a 95 % upper bound of ~3/n — hence
  no "never" without confirmation (Hanley & Lippman-Hand, JAMA 1983).
- AI detectors false-flag non-native writers (~61 % average false-positive rate on TOEFL
  essays) — Liang et al., *Patterns* 2023, arXiv:2304.02819. This checker compares only
  against the user's own baseline and is not a detector.
