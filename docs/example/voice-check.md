# voice-check on two drafts (external email)

## ai.md
```
VOICE CHECK: FAIL  (register email-external, tier directional, 63 words)
  [FAIL ] length: 63 words — far above your p90 of 27.9 for email-external (median 23.5)
  [WARN ] ai-default: “i hope this email finds you well” — an AI-default phrase absent from your email-external samples (confidence low)
  [WARN ] ai-default: “i wanted to reach out” — an AI-default phrase absent from your email-external samples (confidence low)
  [WARN ] ai-default: “please do not hesitate” — an AI-default phrase absent from your email-external samples (confidence low)
  [WARN ] ai-default: “at your earliest convenience” — an AI-default phrase absent from your email-external samples (confidence low)
  [WARN ] band: sent_len_mean: 14.2 vs your typical 4.47–8.93 (median 7.35) (above)
  [WARN ] band: polite_per_100w: 10.53 vs your typical 0.0–0.0 (median 0.0) (above)
exit 1
```

## good.md
```
VOICE CHECK: INCONCLUSIVE  (register email-external, tier directional, 16 words)
  [INCONCLUSIVE] bands: draft is 16 words — distribution checks skipped (need ≥40)
exit 0
```

## --selftest --loo
```
selftest over 20 of your own samples (leave-one-out):
  PASS             0  (0%)
  INCONCLUSIVE    17  (85%)
  WARN             3  (15%)
  FAIL             0  (0%)
  most common findings on genuine text (these are the checker's false alarms):
    warn:length                      3  (15%)
  → read WARN as noise unless it names something specific; FAIL false-alarm rate here is 0%
```
