# Corpus report — 2026-09-05

Home: `~/.personal-tone` · samples: 21 · words: 377

| register | samples | words | median words/sample | date range | tier |
| --- | ---: | ---: | ---: | --- | --- |
| email-external | 13 | 285 | 23 | 2026-01-05 → 2026-02-07 | directional |
| email-internal | 8 | 92 | 11 | 2026-04-23 → 2026-05-07 | provisional |

Tiers: <10 provisional · 10–29 directional · 30–99 solid · 100+ high

## Dropped

| reason | count |
| --- | ---: |
| duplicate | 40 |

## Redactions

email: 0, name: 36, number: 0, phone: 0, url: 0

## Next step

    python3 <repo>/skills/voice-profile/scripts/stylometry.py --home ~/.personal-tone

Privacy: local only. The home dir is chmod 700 with a `.gitignore` of `*`; never commit or share `corpus.jsonl` — a voice corpus is an attribution key.
