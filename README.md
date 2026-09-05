# Personal Tone

[![CI](https://github.com/Paldom/personal-tone/actions/workflows/ci.yml/badge.svg)](https://github.com/Paldom/personal-tone/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![skills.sh](https://skills.sh/b/Paldom/personal-tone)](https://skills.sh/Paldom/personal-tone)

Agent Skills that capture your personal writing voice from your own sent emails and chats and draft new messages in your own words, length, openers and sign-offs, with a deterministic check that catches length inflation, wrong sign-offs, AI-default phrases and self-parody. Everything runs locally from stdlib Python; nothing is ever sent on your behalf.

Agent Skills for [Claude Code](https://code.claude.com/docs/en/skills) (and any
[Agent Skills](https://agentskills.io)-compatible tool). Each skill is a folder under
[`skills/`](skills/) with a single-purpose `SKILL.md`, trigger evals, and optional
scripts/references — validated on every write, commit, and PR.

## Quick start

Install with the [skills CLI](https://skills.sh) — auto-detects 70+ agents
(Claude Code, Codex, Cursor, Copilot, pi, …):

```bash
npx skills add Paldom/personal-tone                  # all detected agents
npx skills add Paldom/personal-tone -a codex -a pi   # or target specific agents
```

Or with the [GitHub CLI](https://cli.github.com/manual/gh_skill_install) (≥ 2.90),
including version-pinned installs from releases:

```bash
gh skill install Paldom/personal-tone
gh skill install Paldom/personal-tone <skill> --pin <tag>
```

Or as a Claude Code plugin:

```
/plugin marketplace add Paldom/personal-tone
/plugin install personal-tone@personal-tone
```

Or copy a single skill into a project:

```bash
git clone https://github.com/Paldom/personal-tone.git
cp -r personal-tone/skills/<skill-name> your-project/.claude/skills/
```

Then just describe the task — the skill activates on its description — or invoke it
explicitly with `/<skill-name>`.

## Skills

| Skill | Description |
| --- | --- |
| [voice-corpus](skills/voice-corpus/) | Builds a cleaned, redacted corpus of your own sent messages from mbox/eml, Slack or WhatsApp exports - keeps only what you wrote, strips quoted replies and signatures, tags registers (internal/external email, DM/group chat). |
| [voice-profile](skills/voice-profile/) | Measures that corpus and writes your voice profile: per-register length bands, opener and sign-off shares, hedging and contraction rates, never-candidates you confirm, exemplar ids. Numbers first, prose second. |
| [voice-write](skills/voice-write/) | Drafts, replies and rewrites in your voice from the profile plus five of your own past messages, under a length and skeleton lock, then runs the voice check before showing you the draft. |
| [voice-check](skills/voice-check/) | Detect-only: scores any draft against your profile - length, opener/sign-off class, banned and AI-default phrases, caricature, unbriefed facts - and a self-test that measures its own false-alarm rate on your real mail. |
| [voice-calibrate](skills/voice-calibrate/) | Logs what you actually sent versus the draft, tags what changed, finds corrections that recur, and promotes them to rules only when you say so. |

The five skills form a pipeline: **corpus → profile → write ⇄ check → calibrate** (which
feeds back into the profile). A paste-ready `/goal` that runs the whole thing on a fresh
export lives in [docs/setup-prompt.md](docs/setup-prompt.md).

### What it looks like

[docs/example/](docs/example/) holds a complete run on a synthetic mailbox: the cleaned
[`corpus.jsonl`](docs/example/home/corpus.jsonl), the canonical
[`profile.json`](docs/example/home/profile.json) with its narrative
[`profile.md`](docs/example/home/profile.md), the exemplar block the writer receives, a
[voice check](docs/example/voice-check.md) that fails a generic assistant draft and passes
a genuine one, and a logged draft-vs-sent correction. One line of the corpus:

```json
{"id": "e-08ff95f7c795", "register": "email-external", "date": "2026-01-05", "is_reply": true,
 "words": 26, "text": "Hi [name],\n\nQuick one: can you send the Q3 numbers by Friday? I'd rather have a rough cut than wait for the polished deck.\n\nThanks,\nAlex", "flags": ["redacted:1"]}
```

### How it holds up

- **Your numbers, not adjectives.** Asking a model to describe a writing style hallucinates;
  measured features plus model interpretation holds up (arXiv:2602.23079). The profile stores
  distributions, classes and bans, and the writer gets constraints plus your own samples.
- **The best-documented tell is length.** Generic assistant email runs about 2.7 times longer
  and far more formal than human email (Li et al., WebSci '25); the checker fails a draft
  above your own p90.
- **Bans need your consent.** Zero occurrences in a small corpus proves little, so absent
  AI-default phrases are proposals until you confirm them; the same goes for corrections
  that recur.
- **Local first, stated honestly.** The corpus and profile live in a 0700 directory and are
  never committed, but whatever an agent reads into context goes to your model provider
  under its policy. A voice profile is an attribution key (arXiv:2601.12407), so the skills
  print five samples, never the corpus.
- **Draft only.** No skill sends, posts or replies for you.

## Repository structure

```
skills/                  # distributed skills, one folder per skill (SKILL.md + evals/ + scripts/)
docs/                    # skill-authoring guide, eval methodology, deployment guide, setup prompt
scripts/                 # deterministic validator used by hooks and CI
skills.sh.json           # skills.sh repo-page customization (groupings)
.claude/                 # agentic dev setup: hooks + bundled add-skill / publish-repo skills
.claude-plugin/          # plugin + marketplace manifests (makes this repo installable)
.local/                  # gitignored working area: sources, research, PROMPT.md (see below)
```

## Working on this repo with an agent

This repo is agent-native: canonical agent instructions live in
[AGENTS.md](AGENTS.md) (CLAUDE.md imports it), hooks validate every `SKILL.md` on
write, `make check` runs the full validator, and CI enforces the same gate on every
PR. The bundled `add-skill` skill walks the eval-first authoring workflow described
in [docs/skill-authoring.md](docs/skill-authoring.md). Maintainers drive sessions
with their own (gitignored, personal) `.local/PROMPT.md` goal prompt.

## Contributing

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the skill-proposal
process, the authoring workflow, and the PR checklist. Please note the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Support

Questions, ideas, or something not working? Start with [SUPPORT.md](SUPPORT.md) —
bugs and skill proposals have [issue templates](../../issues/new/choose), and
security concerns go through [SECURITY.md](SECURITY.md) (never a public issue).

## License

[MIT](LICENSE) © 2026 Paldom
