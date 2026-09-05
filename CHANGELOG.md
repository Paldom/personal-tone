# Changelog

All notable changes to this repository's skills are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning: [SemVer](https://semver.org) on the plugin manifest
(breaking skill-interface change → major, new skill → minor, fix → patch).

## [Unreleased]

Nothing yet.

## [0.1.0] - 2026-09-05

### Added
- `docs/example/`: a complete synthetic run (corpus, profile, exemplar block, check output,
  calibration entry) with the generator script.
- `voice-corpus`: builds a cleaned, redacted, register-tagged corpus of the user's own sent
  messages from mbox/eml, Slack and WhatsApp exports or pasted samples (`build_corpus.py`,
  stdlib only, self-tested).
- `voice-profile`: measures the corpus into `metrics.json` and the canonical `profile.json`
  (per-message p10/p50/p90 bands, opener/sign-off classes, signature moves, never-candidates,
  user-confirmed bans and keeps, exemplar ids) via `stylometry.py`.
- `voice-write`: drafts in the user's voice from one register slice plus length-stratified
  own samples (`pick_exemplars.py`), under skeleton and length locks, gated by voice-check.
- `voice-check`: detect-only checker (`voice_check.py`) with FAIL/WARN/INCONCLUSIVE verdicts,
  leakage checks against the brief and the samples, and a `--selftest` false-alarm report.
- `voice-calibrate`: draft-vs-sent logging, recurrence report and confirmed promotion of bans
  and keeps with profile snapshots (`delta.py`).
- `docs/setup-prompt.md`: paste-ready `/goal` orchestrating the pipeline on a fresh export.
- Repository scaffolded from the skills template.
