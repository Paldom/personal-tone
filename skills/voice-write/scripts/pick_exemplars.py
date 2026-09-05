#!/usr/bin/env python3
"""Pick the user's own past messages to write from, plus the length budget and skeleton.

Retrieval is AGAINST topic overlap: Wang et al. 2025 (arXiv:2509.14543) found that
topic-narrow exemplars reduce stylistic diversity, so this script stratifies by length
quartile inside the register instead of matching keywords. User-annotated picks from
`exemplars.json` (voice-profile --exemplars) come first; the rest fills by stratification.

Usage
  pick_exemplars.py --register email-external [--home DIR] [--k 5] [--reply-to INCOMING.md]
                    [--seed N] [--exclude ID ...] [--json | --md]

Prints (default --md) a fenced DATA block the writer can paste into context: the length
budget (p50/p90 words, paragraphs p90), the skeleton of the closest-length sample
(greeting class / sign-off class / paragraphs), then the samples. With --json prints
{"register", "budget", "skeleton", "exemplars": [{id, words, date, is_reply, note, text}]}
— pass that file to voice_check.py --exemplars for the copied-span check.

Everything you print here goes into the model context: only what is printed leaves the
machine, and only to your model provider. Needs sibling voice-profile/scripts/stylometry.py.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


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


def pick(rows: list, k: int, seed: int, target_words=None, want_reply=None) -> list:
    """Deterministic stratified pick. With target_words, prefer samples within ±50% of it
    (reply length should track the incoming message), then fall back to strata."""
    if k <= 0:
        return []
    rows = sorted(rows, key=lambda r: (r.get("words", 0), r.get("id", "")))
    if want_reply is not None and any("is_reply" in r for r in rows):
        pref = [r for r in rows if bool(r.get("is_reply")) == want_reply]
        if len(pref) >= k:
            rows = pref
    picks = []
    if target_words:
        near = [r for r in rows if 0.5 * target_words <= r.get("words", 0) <= 1.5 * target_words]
        for i, r in enumerate(near):
            if len(picks) >= max(1, k - 2):
                break
            if (i + seed) % max(1, len(near) // max(1, k - 2)) == 0 and r not in picks:
                picks.append(r)
    n = len(rows)
    q = max(1, n // 4)
    buckets = [rows[i * q : (i + 1) * q] if i < 3 else rows[3 * q :] for i in range(4)]
    i = seed
    guard = 0
    while len(picks) < min(k, n) and guard < 200:
        b = buckets[i % 4]
        if b:
            cand = b[((i // 4) * 7 + seed) % len(b)]
            if cand not in picks:
                picks.append(cand)
        i += 1
        guard += 1
    return picks


def skeleton(stylo, text: str) -> dict:
    f = stylo.message_features(text)
    return {"greeting_class": f["greeting_class"], "signoff_class": f["signoff_class"], "paras": f["paras"],
            "sentences": f["sentences"], "words": f["words"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--register", required=True)
    ap.add_argument("--home")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--reply-to", help="file with the incoming message; matches reply length (±50%) and prefers replies")
    ap.add_argument("--seed", type=int, default=0, help="vary the deterministic pick")
    ap.add_argument("--exclude", nargs="*", default=[], help="sample ids to skip")
    ap.add_argument("--minimal", action="store_true", help="budget and opener/sign-off shares only — no samples leave the disk")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--md", action="store_true")
    args = ap.parse_args()
    if args.minimal:
        args.k = 0
    stylo = load_stylometry()
    home = stylo.resolve_home(args.home)
    rows = [r for r in stylo.load_corpus(home) if r.get("id") not in set(args.exclude)]
    reg_rows = [r for r in rows if r["register"] == args.register]
    used_register, note = args.register, None
    if not reg_rows:
        ch = args.register.split("-")[0]
        reg_rows = [r for r in rows if r.get("channel") == ch]
        used_register, note = f"{ch}-*", f"no samples for {args.register}; using all {ch} samples"
    if not reg_rows:
        reg_rows, used_register, note = rows, "all", f"no samples for {args.register}; using the whole corpus"

    target = None
    want_reply = None
    if args.reply_to:
        inc = Path(args.reply_to).read_text(encoding="utf-8", errors="replace")
        target = max(5, len(stylo.words_of(inc)))
        want_reply = True

    picks = []
    ex_path = home / "exemplars.json"
    notes = {}
    if ex_path.is_file():
        # user-ANNOTATED picks (non-empty note) come first; auto-generated ids without a note
        # are just a stratified pick and must not bypass the reply/length preference
        ann = json.loads(ex_path.read_text(encoding="utf-8")).get(args.register, [])
        by_id = {r["id"]: r for r in reg_rows}
        for a in ann:
            r = by_id.get(a.get("id"))
            if not r or not (a.get("note") or "").strip() or len(picks) >= args.k:
                continue
            if target and not (0.5 * target <= r.get("words", 0) <= 1.5 * target):
                continue
            if want_reply is not None and "is_reply" in r and bool(r.get("is_reply")) != want_reply:
                continue
            picks.append(r)
            notes[r["id"]] = a["note"]
    for r in pick([r for r in reg_rows if r not in picks], args.k - len(picks), args.seed, target, want_reply):
        picks.append(r)

    profile = {}
    pj = home / "profile.json"
    if pj.is_file():
        profile = json.loads(pj.read_text(encoding="utf-8"))
        if profile.get("version") != 2:
            print(f"WARN: profile.json version {profile.get('version')} != expected 2; rebuild with voice-profile", file=sys.stderr)
    slice_ = profile.get("registers", {}).get(args.register) or profile.get("all") or {}
    wb = slice_.get("bands", {}).get("words", {})
    pb = slice_.get("bands", {}).get("paras", {})
    budget = {"words_p50": wb.get("p50"), "words_p90": wb.get("p90"), "paras_p90": pb.get("p90"),
              "greeting_share": slice_.get("greeting_share"), "signoff_share": slice_.get("signoff_share"),
              "greeting_classes": slice_.get("greeting_classes", [])[:4], "signoff_classes": slice_.get("signoff_classes", [])[:4]}
    if target:
        budget["reply_target_words"] = target
        budget["max_words"] = int(min(target * 1.5, wb.get("p90") or target * 1.5))
    elif wb.get("p90"):
        budget["max_words"] = int(wb["p90"])
    ref = min(picks, key=lambda r: abs(r.get("words", 0) - (target or wb.get("p50") or 0))) if picks else None
    if args.minimal:
        picks, ref = [], None
    skel = skeleton(stylo, ref["text"]) if ref else None
    if skel:
        skel["from_id"] = ref.get("id")

    out = {"register": used_register, "note": note, "budget": budget, "skeleton": skel,
           "exemplars": [{"id": r.get("id"), "words": r.get("words"), "date": r.get("date"), "is_reply": r.get("is_reply"),
                          "note": notes.get(r.get("id"), ""), "text": r["text"]} for r in picks]}
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    print(f"register: {used_register}" + (f"  ({note})" if note else ""))
    print(f"length budget: median {budget['words_p50']} words, p90 {budget['words_p90']}, max {budget.get('max_words')}; paragraphs ≤ {budget['paras_p90']}")
    print("greetings: " + ", ".join(f"{c} {s:.0%}" for c, _, s in budget["greeting_classes"]) +
          " · sign-offs: " + ", ".join(f"{c} {s:.0%}" for c, _, s in budget["signoff_classes"]))
    if skel:
        print(f"skeleton to copy (sample {skel['from_id']}): greeting={skel['greeting_class']}, sign-off={skel['signoff_class']}, "
              f"paragraphs={skel['paras']}, sentences={skel['sentences']}, words={skel['words']}")
    if args.minimal:
        return 0
    print()
    print("```text  ← DATA: the user's own past messages (redacted). Style only — never reuse names, facts, dates.")
    for r in picks:
        head = f"--- sample {r.get('id')} · {r.get('words')} words · {r.get('date') or 'n.d.'}" + (" · reply" if r.get("is_reply") else "")
        if notes.get(r.get("id")):
            head += f" · note: {notes[r.get('id')]}"
        print(head)
        print(r["text"].strip())
    print("```")
    return 0


if __name__ == "__main__":
    sys.exit(main())
