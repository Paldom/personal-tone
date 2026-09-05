#!/usr/bin/env python3
"""Draft-vs-sent calibration: log the gap, mine recurring corrections, promote on confirmation.

"The gap between the draft and the send is your voice." Each entry stores the diff hunks
(removed/added lines, redacted), feature deltas and auto-tags, plus the reason the user
gave. A single edit is not a rule: --report only proposes a rule when the same removed or
added phrase recurs in 2+ entries, and nothing changes profile.json until the user
confirms with --promote-ban/--promote-keep --confirm (profile.v<N>.json snapshot first).

Usage
  delta.py --draft DRAFT.md --sent SENT.md --register email-external [--reason "..."]
           [--tags TOO_FORMAL,LENGTH] [--keep-text] [--home DIR]
  delta.py --report [--register R] [--home DIR]
  delta.py --promote-ban "phrase" --confirm [--scope email-external] [--home DIR]
  delta.py --promote-keep "form" --confirm [--home DIR]
Options: --reason-file FILE (reason from a file, no shell quoting), --metrics-only (store tags
and metrics but no diff lines), --keep-text (store full redacted texts).

Tags (auto-detected, user can add): LENGTH_CUT LENGTH_ADD LESS_FORMAL MORE_FORMAL OPENER
SIGNOFF LLM_ISM STRUCTURE HEDGE_CUT HEDGE_ADD NOT_ME WRONG_WORD FACT
Log: <home>/calibration.jsonl (append-only, 0600, redacted). Stdlib only. No network.
Needs sibling voice-profile/scripts/stylometry.py.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1
MIN_RECURRENCE = 2
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
URL_RE = re.compile(r"https?://\S+|www\.\S+")
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{6,}\d)(?!\w)")
FACT_TAGS = {"FACT"}


def load_stylometry():
    here = Path(__file__).resolve().parent
    cands = [Path(os.environ["PERSONAL_TONE_STYLOMETRY"])] if os.environ.get("PERSONAL_TONE_STYLOMETRY") else []
    cands += [here.parent.parent / "voice-profile" / "scripts", here]
    for c in cands:
        if (c / "stylometry.py").is_file():
            sys.path.insert(0, str(c))
            import stylometry  # noqa: E402
            return stylometry
    sys.exit("ERROR: voice-profile/scripts/stylometry.py not found — install the voice-profile skill from the same repo")


def redact(text: str) -> str:
    # ponytail: the same three regexes as voice-corpus; names are NOT redacted here — the
    # user is looking at their own drafts. Add a name list via voice-corpus if needed.
    return PHONE_RE.sub("[phone]", URL_RE.sub("[url]", EMAIL_RE.sub("[email]", text)))


def auto_tags(d: dict, s: dict) -> list:
    tags = []
    if s["words"] < 0.7 * d["words"]:
        tags.append("LENGTH_CUT")
    elif s["words"] > 1.3 * d["words"]:
        tags.append("LENGTH_ADD")
    if s["contractions_per_100w"] > d["contractions_per_100w"] + 1.5 or s["polite_per_100w"] < d["polite_per_100w"] - 1.5:
        tags.append("LESS_FORMAL")
    elif s["contractions_per_100w"] < d["contractions_per_100w"] - 1.5 or s["polite_per_100w"] > d["polite_per_100w"] + 1.5:
        tags.append("MORE_FORMAL")
    if s["greeting_class"] != d["greeting_class"]:
        tags.append("OPENER")
    if s["signoff_class"] != d["signoff_class"]:
        tags.append("SIGNOFF")
    if d["ai_vocab_count"] > s["ai_vocab_count"]:
        tags.append("LLM_ISM")
    if abs(s["paras"] - d["paras"]) >= 2:
        tags.append("STRUCTURE")
    if s["hedges_per_100w"] < d["hedges_per_100w"] - 1.5:
        tags.append("HEDGE_CUT")
    elif s["hedges_per_100w"] > d["hedges_per_100w"] + 1.5:
        tags.append("HEDGE_ADD")
    return tags


def hunks(draft: str, sent: str):
    dl = [ln.strip() for ln in draft.splitlines() if ln.strip()]
    sl = [ln.strip() for ln in sent.splitlines() if ln.strip()]
    removed, added = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=dl, b=sl).get_opcodes():
        if tag in ("replace", "delete"):
            removed += dl[i1:i2]
        if tag in ("replace", "insert"):
            added += sl[j1:j2]
    ratio = round(difflib.SequenceMatcher(a=draft, b=sent).ratio(), 3)
    return removed, added, ratio


def subset(f: dict) -> dict:
    keys = ("words", "paras", "sentences", "sent_len_mean", "contractions_per_100w", "hedges_per_100w", "polite_per_100w",
            "question_share", "exclaim_share", "greeting_class", "signoff_class", "ai_vocab_count", "em_dash_count", "emoji_count")
    return {k: f[k] for k in keys}


def log_entry(stylo, home: Path, args) -> int:
    draft = Path(args.draft).read_text(encoding="utf-8", errors="replace")
    sent = Path(args.sent).read_text(encoding="utf-8", errors="replace")
    d, s = stylo.message_features(draft), stylo.message_features(sent)
    removed, added, ratio = hunks(draft, sent)
    tags = sorted(set(auto_tags(d, s)) | {t.strip().upper() for t in (args.tags or "").split(",") if t.strip()})
    reason = Path(args.reason_file).read_text(encoding="utf-8").strip() if args.reason_file else (args.reason or "").strip()
    entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "version": VERSION,
             "register": args.register or "default", "tags": tags, "reason": redact(reason),
             "similarity": ratio, "draft": subset(d), "sent": subset(s),
             "removed": [] if args.metrics_only else [redact(x) for x in removed],
             "added": [] if args.metrics_only else [redact(x) for x in added], "status": "logged"}
    if args.keep_text:
        entry["draft_text"], entry["sent_text"] = redact(draft), redact(sent)
    log = home / "calibration.jsonl"
    fd = os.open(str(log), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"logged → {log}")
    print(f"similarity {ratio}; words {d['words']}→{s['words']}; paragraphs {d['paras']}→{s['paras']}; "
          f"contractions/100w {d['contractions_per_100w']}→{s['contractions_per_100w']}; polite/100w {d['polite_per_100w']}→{s['polite_per_100w']}; "
          f"hedges/100w {d['hedges_per_100w']}→{s['hedges_per_100w']}; opener {d['greeting_class']}→{s['greeting_class']}; "
          f"sign-off {d['signoff_class']}→{s['signoff_class']}")
    print("tags: " + (", ".join(tags) or "none"))
    if removed:
        print("removed: " + " | ".join(x[:80] for x in removed[:5]))
    if added:
        print("added:   " + " | ".join(x[:80] for x in added[:5]))
    if not entry["reason"]:
        print("tip: add --reason \"...\" — the stated reason is the most useful signal for the next draft")
    return 0


def grams(lines, n=3):
    out = set()
    for ln in lines:
        toks = re.findall(r"[^\W\d_][\w'’-]*", ln.lower())
        out |= {" ".join(toks[i : i + n]) for i in range(len(toks) - n + 1)}
    return out


def report(home: Path, register) -> int:
    log = home / "calibration.jsonl"
    if not log.is_file():
        sys.exit(f"ERROR: {log} not found — log a draft-vs-sent pair first")
    entries, seen = [], set()
    for ln in log.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        e = json.loads(ln)
        key = (e.get("register"), tuple(e.get("removed", [])), tuple(e.get("added", [])))
        if key in seen:
            continue  # the same pair logged twice is one observation, not two
        seen.add(key)
        entries.append(e)
    if register:
        entries = [e for e in entries if e.get("register") == register]
    if not entries:
        sys.exit("ERROR: no calibration entries" + (f" for {register}" if register else ""))
    by_reg = Counter(e["register"] for e in entries)
    tags = Counter(t for e in entries for t in e["tags"])
    removed_g, added_g = Counter(), Counter()
    for e in entries:
        if FACT_TAGS & set(e["tags"]):
            continue  # fact corrections are not voice
        for g in grams(e.get("removed", [])):
            removed_g[g] += 1
        for g in grams(e.get("added", [])):
            added_g[g] += 1
    print(f"calibration report: {len(entries)} entries " + ", ".join(f"{r} {c}" for r, c in by_reg.most_common()))
    print("tags: " + ", ".join(f"{t} {c}" for t, c in tags.most_common()))
    reasons = [e["reason"] for e in entries if e.get("reason")]
    if reasons:
        print("reasons given: " + " | ".join(r[:70] for r in reasons[-6:]))
    ban_c = [(g, c) for g, c in removed_g.most_common(30) if c >= MIN_RECURRENCE and g not in added_g]
    keep_c = [(g, c) for g, c in added_g.most_common(30) if c >= MIN_RECURRENCE and g not in removed_g]
    print(f"\nrecurring REMOVED phrases (≥{MIN_RECURRENCE} entries) — ban candidates; confirm with --promote-ban \"...\" --confirm:")
    print("  " + ("; ".join(f"“{g}” ×{c}" for g, c in ban_c[:10]) or "none yet"))
    print(f"recurring ADDED phrases (≥{MIN_RECURRENCE} entries) — keep/prefer candidates; confirm with --promote-keep \"...\" --confirm:")
    print("  " + ("; ".join(f"“{g}” ×{c}" for g, c in keep_c[:10]) or "none yet"))
    if tags:
        top = tags.most_common(1)[0]
        print(f"\nmost frequent correction: {top[0]} ({top[1]}/{len(entries)}) — tell voice-write about it in the brief until the profile is rebuilt")
    return 0


def promote(stylo, home: Path, term: str, kind: str, confirm: bool, scope: str = "all") -> int:
    pj = home / "profile.json"
    if not pj.is_file():
        sys.exit(f"ERROR: {pj} not found")
    profile = json.loads(pj.read_text(encoding="utf-8"))
    if profile.get("version") != 2:
        print(f"WARN: profile.json version {profile.get('version')} != expected 2; rebuild with voice-profile", file=sys.stderr)
    key, field = ("bans", "term") if kind == "ban" else ("keep", "form")
    if any(x[field].lower() == term.lower() for x in profile.get(key, [])):
        print(f"already present in {key}: {term}")
        return 0
    if not confirm:
        print(f"would add to {key}: “{term}” (scope {scope}) — re-run with --confirm to apply (profile is snapshotted first)")
        return 0
    snap = int(profile.get("_snapshot", 0)) + 1
    stylo.write_private(home / f"profile.v{snap}.json", json.dumps(profile, ensure_ascii=False, indent=1))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    profile.setdefault(key, []).append({field: term, "scope": scope, "source": "calibration", "added": now} if kind == "ban"
                                       else {field: term, "source": "calibration", "added": now})
    profile["_snapshot"] = snap
    stylo.write_private(pj, json.dumps(profile, ensure_ascii=False, indent=1))
    print(f"added to {key}: “{term}” (scope {scope}; snapshot profile.v{snap}.json written; roll back by copying it over profile.json)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--home")
    ap.add_argument("--draft"); ap.add_argument("--sent"); ap.add_argument("--register")
    ap.add_argument("--reason"); ap.add_argument("--reason-file"); ap.add_argument("--tags")
    ap.add_argument("--keep-text", action="store_true"); ap.add_argument("--metrics-only", action="store_true")
    ap.add_argument("--scope", default="all", help="register a promoted ban applies to (default: all)")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--promote-ban"); ap.add_argument("--promote-keep"); ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args()
    stylo = load_stylometry()
    home = stylo.resolve_home(args.home)
    if args.promote_ban:
        return promote(stylo, home, args.promote_ban, "ban", args.confirm, args.scope)
    if args.promote_keep:
        return promote(stylo, home, args.promote_keep, "keep", args.confirm)
    if args.report:
        return report(home, args.register)
    if args.draft and args.sent:
        return log_entry(stylo, home, args)
    ap.error("give --draft and --sent, or --report, or --promote-ban/--promote-keep")
    return 1


if __name__ == "__main__":
    sys.exit(main())
