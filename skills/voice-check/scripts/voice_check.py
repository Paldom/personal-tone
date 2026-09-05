#!/usr/bin/env python3
"""Detect-only voice check: scores a draft against the user's canonical profile.json.

Compares ONE draft with the per-message distributions of a register (p10–p90 bands),
opener/sign-off classes, user-confirmed bans, never-candidates, signature-move budgets,
and — optionally — a brief and the exemplars used to write it (leakage checks).

Verdicts (precedence: FAIL > WARN > INCONCLUSIVE > PASS)
  FAIL          a user-confirmed ban is present, the draft is far too long (> p90 × 1.25),
                has too many paragraphs (> p90 + 1), or opens/closes with a class the user
                has NEVER used in a register of ≥ 60 samples (0/60 bounds the rate under 5 %).
                Exit 1. Statistical FAILs are
                downgraded to WARN when the register had to fall back (same channel / all).
  WARN          advisory findings: band exits, rare (< 5 %) opener/sign-off class,
                never-candidate hits, caricature, identifiers not in the brief, copied spans.
  PASS          nothing found.
  INCONCLUSIVE  draft under 40 words: distribution checks skipped; bans, length, classes and
                leakage still run (a ban on a short draft is still FAIL).
Exit 2 = configuration/runtime error (no profile, missing files).

Thresholds are this repo's defaults, not measured universals: run `--selftest` (in-sample,
a floor) or `--selftest --loo` (leave-one-out, honest for small corpora) to see the FAIL/WARN
rates the checker produces on the user's OWN sent samples, and read WARNs with that in mind.

Usage
  voice_check.py DRAFT.md --register email-external [--home DIR] [--brief BRIEF.md]
                 [--exemplars picks.json] [--json]
  voice_check.py --selftest [--loo] [--register R] [--home DIR]

Needs the sibling skill voice-profile (scripts/stylometry.py) installed next to this skill,
or PERSONAL_TONE_STYLOMETRY=/path/to/voice-profile/scripts. Stdlib only. No network.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1
PROFILE_VERSION = 2
SHORT_DRAFT_WORDS = 40
LONG_FAIL_FACTOR = 1.25
RARE_CLASS_MASS = 0.05
CLASS_MIN_SAMPLES = 20  # below this, opener/sign-off classes are never flagged
CLASS_FAIL_MIN_SAMPLES = 60  # 0 of 60 bounds the true rate below ~5 % (rule of three) → FAIL; 20-59 → WARN
STAT_FAIL_MIN_SAMPLES = 10  # length/paragraph FAILs need a directional register
STALE_DAYS = 180
BAND_FEATURES = ("sent_len_mean", "contractions_per_100w", "hedges_per_100w", "polite_per_100w",
                 "question_share", "exclaim_share", "lowercase_start_share")
PRESENCE_FEATURES = ("em_dash_count", "emoji_count")  # zero-heavy: compare presence to msg_share
MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
DATE_RE = re.compile(r"\b\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\b|\b(?:%s)\w*\s+\d{1,2}\b|\b\d{1,2}\s+(?:%s)\w*\b" % (MONTHS, MONTHS), re.I)
NUM_RE = re.compile(r"\b\d[\d,.]{2,}\b")
URL_RE = re.compile(r"https?://\S+|www\.\S+")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
NOT_NAMES = set("i i'm i'll i've i'd monday tuesday wednesday thursday friday saturday sunday january february march april "
                "may june july august september october november december ok okay thanks thank hi hey hello dear best "
                "regards cheers yes no re fyi ps pps q a".split())


CTRL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def load_stylometry():
    here = Path(__file__).resolve().parent
    candidates = [Path(os.environ["PERSONAL_TONE_STYLOMETRY"])] if os.environ.get("PERSONAL_TONE_STYLOMETRY") else []
    candidates += [here.parent.parent / "voice-profile" / "scripts", here]
    for c in candidates:
        if (c / "stylometry.py").is_file():
            sys.path.insert(0, str(c))
            import stylometry  # noqa: E402
            return stylometry
    die("voice-profile/scripts/stylometry.py not found next to this skill — install the voice-profile "
        "skill from the same repo, or set PERSONAL_TONE_STYLOMETRY to its scripts directory")


def load_profile(home: Path) -> dict:
    p = home / "profile.json"
    if not p.is_file():
        die(f"{p} not found — run voice-profile/scripts/stylometry.py --write-profile first")
    try:
        profile = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        die(f"cannot read {p}: {exc}")
    if not isinstance(profile, dict) or profile.get("version") != PROFILE_VERSION:
        die(f"profile.json version {profile.get('version') if isinstance(profile, dict) else '?'} != expected {PROFILE_VERSION} — rebuild it with voice-profile")
    return profile


def choose_register(profile: dict, wanted: str):
    regs = profile.get("registers", {})
    if wanted in regs:
        return wanted, regs[wanted], None
    channel = (wanted or "").split("-")[0]
    same = [(r, e) for r, e in regs.items() if e.get("channel") == channel]
    if same:
        r, e = max(same, key=lambda x: x[1]["samples"])
        return r, e, f"register '{wanted}' not in profile; using '{r}' (same channel)"
    if profile.get("all"):
        return "all", profile["all"], f"register '{wanted}' not in profile; using all-corpus bands"
    if regs:
        r, e = max(regs.items(), key=lambda x: x[1]["samples"])
        return r, e, f"register '{wanted}' not in profile; using largest register '{r}'"
    die("profile.json has no registers")


def term_hits(text_lc: str, term: str) -> int:
    return len(re.findall(r"(?<!\w)" + re.escape(term.lower()) + r"(?!\w)", text_lc))


def band_msg(name, value, band, unit=""):
    return f"{name}: {value}{unit} vs your typical {band['p10']}–{band['p90']}{unit} (median {band['p50']})"


def check(stylo, draft_text: str, profile: dict, register: str, brief_text=None, exemplars=None) -> dict:
    reg_name, reg, fallback = choose_register(profile, register)
    draft_text = "\n".join(ln for ln in draft_text.splitlines() if not ln.lstrip().startswith(">"))  # quoted thread = not the draft
    n = reg.get("samples", 0)
    # statistics borrowed from another register, or from a provisional one (< 10 samples), never hard-fail
    stat_sev = "warn" if (fallback or n < STAT_FAIL_MIN_SAMPLES) else "fail"
    f = stylo.message_features(draft_text)
    lc = stylo.norm_text(draft_text).lower()
    flags = []
    add = lambda check_, sev, msg, **kw: flags.append({"check": check_, "severity": sev, "message": msg, **kw})  # noqa: E731
    short = f["words"] < SHORT_DRAFT_WORDS
    bands = reg.get("bands", {})

    # 1 user-confirmed bans → FAIL (scope is judged against the REQUESTED register, never the fallback)
    for b in profile.get("bans", []):
        if b.get("scope", "all") not in ("all", register):
            continue
        k = term_hits(lc, b["term"])
        if k:
            add("ban", "fail", f"banned phrase present: “{b['term']}” ×{k}", term=b["term"])

    # 2 length / structure
    wb, pb = bands.get("words"), bands.get("paras")
    if wb and wb.get("p90"):
        if f["words"] > wb["p90"] * LONG_FAIL_FACTOR:
            add("length", stat_sev, f"{f['words']} words — far above your p90 of {wb['p90']} for {reg_name} (median {wb['p50']})",
                value=f["words"], band=wb)
        elif f["words"] > wb["p90"]:
            add("length", "warn", f"{f['words']} words — above your p90 of {wb['p90']} for {reg_name} (median {wb['p50']})",
                value=f["words"], band=wb)
    if pb and pb.get("p90") is not None and f["paras"] > pb["p90"] + 1:
        add("structure", stat_sev, f"{f['paras']} paragraphs — you use at most ~{pb['p90']} in {reg_name}", value=f["paras"], band=pb)

    # 3 opener / sign-off classes
    gmass = {c: s for c, _, s in reg.get("greeting_classes", [])}
    smass = {c: s for c, _, s in reg.get("signoff_classes", [])}
    if n >= CLASS_MIN_SAMPLES:
        g, s = f["greeting_class"], f["signoff_class"]
        for check_, cls, mass in (("opener", g, gmass), ("signoff", s, smass)):
            if not mass:
                continue
            share = mass.get(cls, 0.0)
            if share == 0.0:  # never observed: FAIL only when n is large enough to mean it
                sev = stat_sev if n >= CLASS_FAIL_MIN_SAMPLES else "warn"
            elif share < RARE_CLASS_MASS:
                sev = "warn"
            else:
                continue
            verb = "opens with" if check_ == "opener" else "closes with"
            add(check_, sev, f"{verb} “{cls}” — {share:.0%} of your {reg_name} messages; you use: "
                + ", ".join(f"{c} ({p:.0%})" for c, p in sorted(mass.items(), key=lambda x: -x[1])[:4]), value=cls, share=share)

    # 4 never-candidates (AI-default terms absent from the corpus) → WARN
    nc = reg.get("never_candidates", {}) or {}
    for term in nc.get("terms", []):
        k = term_hits(lc, term)
        if k:
            add("ai-default", "warn", f"“{term}” — an AI-default phrase absent from your {reg_name} samples (confidence {nc.get('confidence')})", term=term)

    # 5 band checks (skip on short drafts and unreliable lexicon registers)
    if short:
        add("bands", "inconclusive", f"draft is {f['words']} words — distribution checks skipped (need ≥{SHORT_DRAFT_WORDS})")
    else:
        for key in BAND_FEATURES:
            b = bands.get(key)
            if not b or b.get("p10") is None:
                continue
            if key in stylo.LEXICON_FEATURES and not reg.get("lexicon_reliable", True):
                continue
            v = f[key]
            if v < b["p10"] or v > b["p90"]:
                direction = "below" if v < b["p10"] else "above"
                add("band", "warn", band_msg(key, v, b) + f" ({direction})", feature=key, value=v, band=b)
        for key in PRESENCE_FEATURES:
            b = bands.get(key)
            if b and f[key] > 0 and b.get("msg_share", 0) < 0.1:
                add("presence", "warn", f"{key.replace('_count', '')}: present, but appears in only {b['msg_share']:.0%} of your {reg_name} messages",
                    feature=key, value=f[key])

    # 6 caricature: starter moves are allowed, never required; budget = observed share
    moves = reg.get("signature_moves", [])
    starters = Counter(f["starters"])
    used = []
    for m in moves:
        if m["kind"] != "starter":
            continue
        k = starters.get(m["pattern"], 0)
        if k:
            used.append(m["pattern"])
            if k >= 2 and m["share"] < 0.5:
                add("caricature", "warn", f"starter “{m['pattern']}” used {k}× in one draft; you use it in {m['share']:.0%} of sentences", pattern=m["pattern"])
    if f["words"] < 150 and len(used) > 1:
        add("caricature", "warn", f"{len(used)} distinct signature starters in a {f['words']}-word draft ({', '.join(used)}) — reads as an impression", patterns=used)
    rep = [g for g, c in Counter(" ".join(f["starters"][i : i + 1]) for i in range(len(f["starters"]))).items() if c >= 3 and g]
    if rep:
        add("caricature", "warn", "the same sentence opening appears 3+ times: " + ", ".join(f"“{g}”" for g in rep))
    toks = stylo.words_of(lc)
    four = Counter(" ".join(toks[i : i + 4]) for i in range(len(toks) - 3))
    for g, c in four.items():
        if c >= 2:
            add("repetition", "warn", f"phrase repeated in the draft: “{g}”")
            break

    # 7 leakage: identifiers not in the brief; copied spans from exemplars
    if brief_text is not None:
        blc = brief_text.lower()
        ids = set(URL_RE.findall(draft_text)) | set(EMAIL_RE.findall(draft_text)) | set(DATE_RE.findall(draft_text)) | set(NUM_RE.findall(draft_text))
        sentences = stylo.sentences_of(stylo.norm_text(draft_text))
        starts = {stylo.words_of(s)[0] for s in sentences if stylo.words_of(s)}
        nonempty = [ln for ln in draft_text.splitlines() if ln.strip()]
        edge = " ".join(nonempty[:1] + nonempty[-2:])  # greeting + sign-off lines: the user's and recipient's names
        for tok in re.findall(r"\b[A-Z][a-z]{2,}\b", draft_text):
            if tok not in starts and tok.lower() not in NOT_NAMES and tok not in edge:
                ids.add(tok)
        for ident in sorted(ids):
            if ident.lower() not in blc:
                add("unbriefed", "warn", f"identifier “{ident}” is not in the brief — a name/date/number/URL the model may have invented or copied (this is an identifier check, not fact verification)", identifier=ident)
    if exemplars:
        for ex in exemplars:
            et = stylo.words_of(stylo.norm_text(ex.get("text", "")).lower())
            egrams = {" ".join(et[i : i + 6]) for i in range(len(et) - 5)}
            hit = next((g for g in (" ".join(toks[i : i + 6]) for i in range(len(toks) - 5)) if g in egrams), None)
            if hit:
                add("exemplar-copy", "warn", f"6-word span copied from sample {ex.get('id')}: “{hit}”", sample=ex.get("id"))

    # 8 staleness
    try:
        gen = datetime.fromisoformat(profile["generated"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - gen).days
        if age > STALE_DAYS:
            add("stale", "warn", f"profile is {age} days old — rebuild it from recent sent messages (voices drift)")
    except (KeyError, ValueError):
        pass

    sev = {x["severity"] for x in flags}
    verdict = "FAIL" if "fail" in sev else "WARN" if "warn" in sev else "INCONCLUSIVE" if "inconclusive" in sev else "PASS"
    return {"version": VERSION, "verdict": verdict, "register": reg_name, "fallback": fallback, "tier": reg.get("tier"),
            "words": f["words"], "paras": f["paras"], "greeting_class": f["greeting_class"], "signoff_class": f["signoff_class"],
            "flags": flags}


def render(result: dict) -> str:
    out = [CTRL_RE.sub("", f"VOICE CHECK: {result['verdict']}  (register {result['register']}, tier {result['tier']}, {result['words']} words)")]
    if result["fallback"]:
        out.append(CTRL_RE.sub("", "note: " + result["fallback"]))
    for fl in result["flags"]:
        out.append(CTRL_RE.sub("", f"  [{fl['severity'].upper():5}] {fl['check']}: {fl['message']}"))
    if not result["flags"]:
        out.append("  no findings")
    return "\n".join(out)


def loo_profile(stylo, profile: dict, rows: list, feats: list, reg: str, skip_idx: int):
    """Profile whose register slice is rebuilt without one sample (leave-one-out); None when
    fewer than two other samples remain (then the sample is not LOO-testable)."""
    others = [feats[i] for i, r in enumerate(rows) if r["register"] == reg and i != skip_idx]
    if len(others) < 2:
        return None
    block = stylo.aggregate(others)
    slice_ = dict(profile["registers"][reg])
    slice_.update({"samples": len(others), "tier": stylo.tier_for(len(others)), "bands": block["bands"],
                   "greeting_classes": block["greeting_classes"], "signoff_classes": block["signoff_classes"],
                   "openers": block["openers"], "signature_moves": stylo.signature_moves(block, len(others)),
                   "never_candidates": stylo.never_candidates(block, len(others)),
                   "greeting_share": block["features"]["greeting_share"], "signoff_share": block["features"]["signoff_share"]})
    p2 = dict(profile); p2["registers"] = dict(profile["registers"]); p2["registers"][reg] = slice_
    return p2


def selftest(stylo, home: Path, profile: dict, register, loo: bool = False) -> int:
    rows = stylo.load_corpus(home)
    if register:
        rows = [r for r in rows if r["register"] == register]
    if not rows:
        die("no corpus samples for --selftest")
    feats = [stylo.message_features(r["text"]) for r in rows] if loo else []
    tally = Counter()
    reasons = Counter()
    untestable = 0
    for i, r in enumerate(rows):
        prof = profile
        if loo and r["register"] in profile.get("registers", {}):
            prof = loo_profile(stylo, profile, rows, feats, r["register"], i)
            if prof is None:
                untestable += 1
                continue
        res = check(stylo, r["text"], prof, r["register"])
        tally[res["verdict"]] += 1
        for fl in res["flags"]:
            if fl["severity"] in ("fail", "warn"):
                reasons[f"{fl['severity']}:{fl['check']}"] += 1
    n = len(rows) - untestable
    if untestable:
        print(f"note: {untestable} sample(s) in registers with < 3 samples are not leave-one-out testable and were skipped")
    if n == 0:
        die("no LOO-testable samples")
    print(f"selftest over {n} of your own samples{' in ' + register if register else ''} ({'leave-one-out' if loo else 'in-sample: a floor, not an estimate'}):")
    for v in ("PASS", "INCONCLUSIVE", "WARN", "FAIL"):
        print(f"  {v:12} {tally[v]:5}  ({tally[v] / n:.0%})")
    print("  most common findings on genuine text (these are the checker's false alarms):")
    for k, c in reasons.most_common(8):
        print(f"    {k:28} {c:5}  ({c / n:.0%})")
    fail_rate = tally["FAIL"] / n
    print(f"  → read WARN as noise unless it names something specific; FAIL false-alarm rate here is {fail_rate:.0%}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("draft", nargs="?", help="draft file to check")
    ap.add_argument("--register", default="", help="register to compare against (e.g. email-external)")
    ap.add_argument("--home", help="profile home (default: $PERSONAL_TONE_HOME, ./.personal-tone, ~/.personal-tone)")
    ap.add_argument("--brief", help="the brief the draft was written from (enables unbriefed-identifier check)")
    ap.add_argument("--exemplars", help="JSON list of exemplars used (from pick_exemplars.py --json); enables copy check")
    ap.add_argument("--selftest", action="store_true", help="run the checker over the corpus' own samples and report rates")
    ap.add_argument("--loo", action="store_true", help="with --selftest: rebuild each register without the sample being scored (leave-one-out)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()
    stylo = load_stylometry()
    home = stylo.resolve_home(args.home)
    profile = load_profile(home)
    if args.selftest:
        return selftest(stylo, home, profile, args.register or None, args.loo)
    if not args.draft:
        die("DRAFT is required unless --selftest")
    if not args.register:
        die("--register is required in draft mode (register-scoped bans would otherwise be skipped)")
    p = Path(args.draft)
    if not p.is_file():
        die(f"{p} not found")
    try:
        draft = p.read_text(encoding="utf-8", errors="replace")
        brief = Path(args.brief).read_text(encoding="utf-8", errors="replace") if args.brief else None
        exemplars = json.loads(Path(args.exemplars).read_text(encoding="utf-8")) if args.exemplars else None
    except (OSError, ValueError) as exc:
        die(f"cannot read input: {exc}")
    if isinstance(exemplars, dict):
        exemplars = exemplars.get("exemplars", [])
    if exemplars is not None and not isinstance(exemplars, list):
        die("--exemplars must be a JSON list or the pick_exemplars.py --json object")
    result = check(stylo, draft, profile, args.register, brief, exemplars)
    print(json.dumps(result, ensure_ascii=False, indent=1) if args.json else render(result))
    return 1 if result["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
