#!/usr/bin/env python3
"""Deterministic stylometry for a personal writing-voice corpus (stdlib only, Python 3.9+).

Reads `<home>/corpus.jsonl` (written by voice-corpus/scripts/build_corpus.py) and writes:
  metrics.json    per-register aggregate features + per-message distributions (p10/p50/p90),
                  opener/sign-off classes and patterns, sentence starters, n-grams,
                  AI-default vocabulary hits, never-candidates, signature moves
  profile.json    the CANONICAL machine-readable profile (--write-profile): the register
                  slices voice-check/voice-write/voice-calibrate read, plus user-confirmed
                  bans and keeps. profile.md is a narrative the model writes FROM this file.
  exemplars.json  (--exemplars) stratified exemplar ids per register — text is never
                  duplicated; readers inline it from corpus.jsonl by id.

Why a script: asking a model to *describe* a style hallucinates differences between
near-identical texts; quantitative features plus model interpretation holds up
(Zhang & Zhang 2026, arXiv:2602.23079). Numbers first, prose second.

Usage:
    stylometry.py --home DIR                         corpus -> metrics.json + summary
    stylometry.py --home DIR --write-profile         also write/refresh profile.json
        [--bans FILE]        newline-separated terms the USER confirmed as bans
        [--keep FILE]        newline-separated nonstandard forms the USER approved to keep
        [--registers FILE]   JSON {"old-register": "new-register"} relabel map
    stylometry.py --home DIR --exemplars             also write exemplars.json (ids)
    stylometry.py --text FILE                        one document -> per-message features JSON
    stylometry.py --home DIR --json                  print metrics JSON instead of summary

Ceilings (ponytail): regex sentence splitter, English lexicons, no tagger; thousands of
messages run in seconds; nothing streamed; no network. Corpus text is data — nothing in
it is interpreted. Threshold constants below are this repo's defaults, not paper results.

Exit codes: 0 ok (WARN lines for thin registers), 1 missing/invalid input.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

VERSION = 3
PROFILE_VERSION = 2

# Tiers by sample count. Shape from Wang et al. 2025 (arXiv:2509.14543: ~5 in-context samples
# is the tested default for imitation) and Panza (arXiv:2407.10994: fine-tuning fidelity
# saturates by ~75-100 emails); the cut points are engineering defaults, not their numbers.
TIERS = ((100, "high"), (30, "solid"), (10, "directional"), (0, "provisional"))
MIN_SAMPLES_FOR_NEVER = 10  # never-candidates below this are not produced at all
NEVER_LOW_CONFIDENCE_BELOW = 25  # ...and are labelled low-confidence below this
SIGNATURE_MIN_SAMPLES = 20  # a register needs this many messages before anything is "signature"
SIGNATURE_MIN_COUNT = 3
SIGNATURE_MIN_SHARE = 0.05
LEXICON_LANG_SHARE = 0.7  # lexicon features reliable only if >=70% of samples are English

# Per-message features that get p10/p50/p90 bands. voice-check compares a draft to these.
BANDED = ("words", "paras", "sentences", "sent_len_mean", "contractions_per_100w", "hedges_per_100w",
          "question_share", "exclaim_share", "lowercase_start_share", "em_dash_count", "emoji_count",
          "polite_per_100w", "ai_vocab_count")
LEXICON_FEATURES = ("contractions_per_100w", "hedges_per_100w", "polite_per_100w", "ai_vocab_count")

# --- lexicons (small on purpose — closed lists, not a tagger; English)
STOPWORDS = set(
    """a an the and or but if so of to in on at by for with from as is are was were be been
    being am it its it's this that these those i me my mine we us our you your he him his
    she her they them their what which who whom whose will would can could should may might
    must shall do does did done have has had having not no nor than then there here when
    where why how all any both each few more most other some such only own same too very
    just about above after again against also before below between into through during
    up down out off over under once s t ll re ve d m im ive ill id dont cant wont
    [name] [email] [url] [phone] [number]""".split()
)
CONTRACTION_RE = re.compile(
    r"\b(?:\w+n't|\w+'re|\w+'ve|\w+'ll|\w+'d|i'm|it's|that's|there's|here's|what's|who's|"
    r"he's|she's|let's|how's|where's|when's|why's|y'all)\b", re.IGNORECASE)
HEDGES = ("might", "maybe", "perhaps", "possibly", "probably", "somewhat", "roughly", "sort of",
          "kind of", "i think", "i guess", "i believe", "i suppose", "seems", "arguably",
          "in my opinion", "not sure", "could be", "tend to", "a bit", "slightly", "apparently",
          "presumably", "potentially", "more or less")
BOOSTERS = ("very", "really", "extremely", "definitely", "absolutely", "clearly", "obviously",
            "certainly", "totally", "incredibly", "highly", "truly", "super", "strongly",
            "undoubtedly", "of course", "no doubt", "for sure")
# Polite/formal request markers (over-formality is the best-documented LLM email tell:
# Li et al., WebSci'25 — generic LLM email is longer and far more formal than human email).
POLITE = ("please find", "kindly", "regarding", "i wanted to", "reach out", "would you be able",
          "could you please", "i would appreciate", "at your convenience", "as discussed",
          "i am writing to", "i trust", "hope you are well", "hope you're well", "do not hesitate",
          "don't hesitate", "please let me know if", "should you have any", "i look forward to")
# Era vocabulary + stock phrases models default to (WP:AISIGNS; Kobak et al. 2025 Sci. Adv.;
# Liang et al. 2024). REFERENCE ONLY: the user's own corpus decides what is a tell for them.
AI_VOCAB = ("delve", "delves", "delving", "leverage", "leveraging", "utilize", "utilise", "tapestry",
            "testament", "underscore", "underscores", "landscape", "multifaceted", "pivotal",
            "crucial", "robust", "seamless", "seamlessly", "foster", "fostering", "embark", "realm",
            "vibrant", "elevate", "streamline", "cutting-edge", "game-changer", "game-changing",
            "groundbreaking", "holistic", "meticulous", "meticulously", "nuanced", "paramount",
            "transformative", "unlock", "unleash", "intricate", "showcase", "resonate", "harness",
            "empower", "actionable", "synergy", "navigate the")
AI_PHRASES = ("i hope this email finds you well", "i hope this message finds you well",
              "hope this finds you well", "i wanted to reach out", "i just wanted to",
              "please don't hesitate", "please do not hesitate", "at your earliest convenience",
              "it's worth noting", "it is worth noting", "in today's", "as an ai", "great question",
              "in conclusion", "furthermore,", "moreover,", "additionally,", "it's not just",
              "it's not about", "i'd be happy to", "feel free to reach out", "looking forward to hearing",
              "thank you for your understanding", "circle back", "touch base", "per my last email",
              "just checking in", "just following up")
GREETING_RE = re.compile(
    r"^\s*(?P<g>hi|hey|hello|hiya|yo|dear|greetings|good\s+(?:morning|afternoon|evening)|morning|"
    r"afternoon|evening|szia|sziasztok|kedves|hallo|hola|bonjour|ciao|salut|hej|hei|moin|servus)"
    r"(?P<rest>\b.*)$", re.IGNORECASE)
SIGNOFF_RE = re.compile(
    r"^\s*(?P<s>best regards|kind regards|warm regards|best wishes|all the best|many thanks|"
    r"thank you|talk soon|take care|best|regards|warmly|thanks|thx|ty|cheers|sincerely|yours|br|"
    r"have a (?:good|great|nice) (?:one|day|weekend|evening)|ttyl|later|köszi|köszönöm|köszönettel|"
    r"üdv|üdvözlettel|gracias|merci|danke|bye)(?P<rest>[,!.]*\s*(?:[\w\[\]'. -]{0,30})?)$", re.IGNORECASE)
NAME_LINE_RE = re.compile(r"^\s*[-–—~]?\s*(?:\[name\]|[A-Z][\w'-]{1,20}(?:\s+[A-Z][\w'-]{1,20})?|[A-Z]\.?)\s*$")
WORD_RE = re.compile(r"[^\W\d_][\w'’-]*", re.UNICODE)
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿\U0001F1E6-\U0001F1FF]")
EMOTICON_RE = re.compile(r"(?<!\w)[:;=]-?[)(DPpo3]|(?<!\w)x[dD]\b|\^\^")
BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
SENT_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+(?=[\"'(\[]?[A-Z0-9\[])|\n+")
NOT_ADVERB_LY = set("only family reply early likely apply supply july fly ally rely daily holy ugly "
                    "italy belly jelly bully rally tally silly lily assembly monopoly anomaly".split())


# ----------------------------------------------------------------------------- helpers
def norm_text(text: str) -> str:
    return text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')


def words_of(text: str) -> list:
    return WORD_RE.findall(text)


def sentences_of(text: str) -> list:
    parts = [p.strip() for p in SENT_SPLIT_RE.split(text) if p and p.strip()]
    # ponytail: regex splitter; "e.g." and initials over-split. Upgrade: a real tokenizer.
    return [p for p in parts if words_of(p)]


def count_terms(text_lc: str, terms) -> Counter:
    hits: Counter = Counter()
    for term in terms:
        n = len(re.findall(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text_lc))
        if n:
            hits[term] = n
    return hits


def percentile(values: list, q: float):
    if not values:
        return None
    vs = sorted(values)
    k = (len(vs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(vs) - 1)
    return round(vs[lo] + (vs[hi] - vs[lo]) * (k - lo), 3)


def write_private(path: Path, text: str) -> None:
    """Atomic write via an unpredictable 0600 temp file — the home dir holds an attribution key."""
    if path.is_symlink():
        sys.exit(f"ERROR: {path} is a symlink — refusing to write through it")
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, str(path))
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def resolve_home(arg) -> Path:
    # no implicit project-local default: --home or PERSONAL_TONE_HOME, else ~/.personal-tone
    home = Path(arg or os.environ.get("PERSONAL_TONE_HOME") or "~/.personal-tone").expanduser()
    if home.is_symlink():
        sys.exit(f"ERROR: {home} is a symlink — refusing; profile data must live in a real private directory")
    return home


# ----------------------------------------------------------------------------- shape
def split_shape(text: str) -> dict:
    """Separate greeting line, body lines, sign-off lines. Greeting/sign-off are counted as
    classes, never as sentences (otherwise 'Hi Sam,' drags sentence length to 2)."""
    lines = [ln.rstrip() for ln in norm_text(text).splitlines()]
    nonempty = [i for i, ln in enumerate(lines) if ln.strip()]
    if not nonempty:
        return {"greeting": None, "greeting_class": "none", "opener": "", "body": "", "signoff": None,
                "signoff_class": "none", "name_line": False, "lines": 0}
    first, last = nonempty[0], nonempty[-1]
    greeting = None
    m = GREETING_RE.match(lines[first])
    if m and len(words_of(lines[first])) <= 6:
        greeting = lines[first]
        first += 1
    # trailing name-only line, then sign-off keyword line — only when a body line remains
    # before them (a one-line "thx! will check later" is a body, not a sign-off)
    name_line = False
    if last > first and NAME_LINE_RE.match(lines[last]) and len(words_of(lines[last])) <= 3:
        name_line = True
        last -= 1
    signoff = None
    if last > first and SIGNOFF_RE.match(lines[last]) and len(words_of(lines[last])) <= 5:
        signoff = lines[last]
        last -= 1
    body = "\n".join(lines[first : last + 1]).strip()
    g_class = "none"
    opener = ""
    if greeting:
        gm = GREETING_RE.match(greeting)
        g_class = gm.group("g").lower().split()[0]
        opener = g_class + (" {name}" if re.search(r"\[name\]|[A-Z][a-z]", gm.group("rest") or "") else "")
    s_class = "none"
    if signoff:
        s_class = SIGNOFF_RE.match(signoff).group("s").lower()
    elif name_line:
        s_class = "name-only"
    body_lines = [ln for ln in lines[first : last + 1] if ln.strip()]
    if not greeting and body_lines:
        opener = "(none) " + " ".join(x.lower() for x in words_of(body_lines[0])[:2])
    return {"greeting": greeting, "greeting_class": g_class, "opener": opener, "body": body,
            "signoff": signoff, "signoff_class": s_class, "name_line": name_line,
            "lines": len(nonempty)}


# ----------------------------------------------------------------------------- features
def message_features(raw: str) -> dict:
    """Features of ONE message (per-100-words rates are of the body)."""
    shape = split_shape(raw)
    body = shape["body"] or norm_text(raw)
    lc = body.lower()
    w = words_of(body)
    nw = len(w) or 1
    sents = sentences_of(body)
    ns = len(sents) or 1
    sent_lens = [len(words_of(s)) for s in sents]
    lines = [ln for ln in body.splitlines() if ln.strip()]
    hedges = count_terms(lc, HEDGES)
    boosters = count_terms(lc, BOOSTERS)
    polite = count_terms(lc, POLITE)
    ai = count_terms(lc, AI_VOCAB) + count_terms(lc, AI_PHRASES)
    adverbs = sum(1 for x in w if x.lower().endswith("ly") and len(x) > 4 and x.lower() not in NOT_ADVERB_LY)
    per100 = lambda c: round(100 * c / nw, 2)  # noqa: E731
    return {
        "words": len(words_of(norm_text(raw))),
        "body_words": len(w),
        "sentences": len(sents),
        "paras": len([p for p in re.split(r"\n\s*\n", body) if p.strip()]) or 1,
        "sent_len_mean": round(statistics.mean(sent_lens), 1) if sent_lens else 0,
        "sent_len_max": max(sent_lens) if sent_lens else 0,
        "sent_lens": sent_lens,
        "contractions_per_100w": per100(len(CONTRACTION_RE.findall(body))),
        "hedges_per_100w": per100(sum(hedges.values())),
        "boosters_per_100w": per100(sum(boosters.values())),
        "polite_per_100w": per100(sum(polite.values())),
        "adverb_ly_per_100w": per100(adverbs),
        "question_share": round(sum(1 for s in sents if s.rstrip().endswith("?")) / ns, 3),
        "exclaim_share": round(sum(1 for s in sents if s.rstrip().endswith("!")) / ns, 3),
        "lowercase_start_share": round(sum(1 for s in sents if s[0].islower()) / ns, 3),
        "em_dash_count": body.count("—"),
        "spaced_dash_count": len(re.findall(r"\s[–-]\s", body)),
        "semicolon_count": body.count(";"),
        "paren_count": body.count("("),
        "ellipsis_count": len(re.findall(r"\.{3}|…", body)),
        "emoji_count": len(EMOJI_RE.findall(body)) + len(EMOTICON_RE.findall(body)),
        "bullet_line_share": round(sum(1 for ln in lines if BULLET_RE.match(ln)) / (len(lines) or 1), 3),
        "greeting_class": shape["greeting_class"],
        "opener": shape["opener"],
        "signoff_class": shape["signoff_class"],
        "starters": [" ".join(x.lower() for x in words_of(s)[:2]) for s in sents],
        "hedge_hits": hedges, "booster_hits": boosters, "polite_hits": polite, "ai_hits": ai,
        "ai_vocab_count": sum(ai.values()),
        "tokens": [x.lower() for x in w],
    }


def aggregate(msgs: list) -> dict:
    n = len(msgs) or 1
    tokens = [t for m in msgs for t in m["tokens"]]
    sent_lens = [x for m in msgs for x in m["sent_lens"]]
    nw = len(tokens) or 1
    ns = len(sent_lens) or 1
    openers, greetings, signoffs, starters = Counter(), Counter(), Counter(), Counter()
    hedge_hits, booster_hits, polite_hits, ai_hits = Counter(), Counter(), Counter(), Counter()
    for m in msgs:
        openers[m["opener"]] += 1
        greetings[m["greeting_class"]] += 1
        signoffs[m["signoff_class"]] += 1
        starters.update(m["starters"])
        hedge_hits.update(m["hedge_hits"]); booster_hits.update(m["booster_hits"])
        polite_hits.update(m["polite_hits"]); ai_hits.update(m["ai_hits"])

    def wrate(key):  # body-word-weighted rate across the register
        return round(sum(m[key] * m["body_words"] for m in msgs) / nw, 2)

    def srate(key):  # sentence-weighted share
        return round(sum(m[key] * m["sentences"] for m in msgs) / ns, 3)

    features = {
        "words_total": sum(m["words"] for m in msgs),
        "body_words_total": len(tokens),
        "sentences_total": len(sent_lens),
        "sent_len_mean": round(statistics.mean(sent_lens), 1) if sent_lens else 0,
        "sent_len_median": statistics.median(sent_lens) if sent_lens else 0,
        "short_sent_share": round(sum(1 for x in sent_lens if x <= 5) / ns, 3),
        "long_sent_share": round(sum(1 for x in sent_lens if x >= 30) / ns, 3),
        "msg_words_median": statistics.median(m["words"] for m in msgs),
        "msg_words_mean": round(statistics.mean(m["words"] for m in msgs), 1),
        "paras_per_msg_mean": round(statistics.mean(m["paras"] for m in msgs), 2),
        "greeting_share": round(sum(1 for m in msgs if m["greeting_class"] != "none") / n, 3),
        "signoff_share": round(sum(1 for m in msgs if m["signoff_class"] != "none") / n, 3),
        "emoji_msg_share": round(sum(1 for m in msgs if m["emoji_count"]) / n, 3),
        "em_dash_msg_share": round(sum(1 for m in msgs if m["em_dash_count"]) / n, 3),
        "bullet_line_share": round(statistics.mean(m["bullet_line_share"] for m in msgs), 3),
        "avg_word_len": round(statistics.mean(len(t) for t in tokens), 2) if tokens else 0,
        "contractions_per_100w": wrate("contractions_per_100w"),
        "hedges_per_100w": wrate("hedges_per_100w"),
        "boosters_per_100w": wrate("boosters_per_100w"),
        "polite_per_100w": wrate("polite_per_100w"),
        "adverb_ly_per_100w": wrate("adverb_ly_per_100w"),
        "question_share": srate("question_share"),
        "exclaim_share": srate("exclaim_share"),
        "lowercase_start_share": srate("lowercase_start_share"),
        "ai_vocab_per_1kw": round(1000 * sum(m["ai_vocab_count"] for m in msgs) / nw, 2),
    }
    bands = {}
    for key in BANDED:
        vals = [m[key] for m in msgs]
        bands[key] = {"p10": percentile(vals, 0.10), "p50": percentile(vals, 0.50), "p90": percentile(vals, 0.90),
                      "mean": round(statistics.mean(vals), 3),
                      "msg_share": round(sum(1 for v in vals if v > 0) / n, 3)}

    def top(counter, k, denom):
        return [[key, c, round(c / denom, 3)] for key, c in counter.most_common(k)]

    grams: Counter = Counter()
    for size in (2, 3):
        for i in range(len(tokens) - size + 1):
            g = tokens[i : i + size]
            if all(x in STOPWORDS for x in g) or any(x.startswith("[") for x in g):
                continue
            grams[" ".join(g)] += 1
    content = Counter(x for x in tokens if x not in STOPWORDS and len(x) > 2)
    return {
        "features": features, "bands": bands,
        "greeting_classes": top(greetings, 8, n), "signoff_classes": top(signoffs, 8, n),
        "openers": top(openers, 8, n), "starters": top(starters, 10, ns),
        "ngrams": [[g, c] for g, c in grams.most_common(15) if c >= 3],
        "top_words": [[wd, c, round(1000 * c / nw, 2)] for wd, c in content.most_common(20)],
        "hedges": hedge_hits.most_common(8), "boosters": booster_hits.most_common(8),
        "polite": polite_hits.most_common(8), "ai_hits": ai_hits.most_common(15),
        "_ai_terms_seen": set(ai_hits),
    }


def tier_for(samples: int) -> str:
    for floor, name in TIERS:
        if samples >= floor:
            return name
    return "provisional"


def signature_moves(block: dict, samples: int) -> list:
    """Openers/sign-offs/starters frequent enough to be characteristic. voice-check treats
    them as ALLOWED with a budget (never required): a draft may not use a move more often
    than the corpus does, and short drafts get at most one."""
    if samples < SIGNATURE_MIN_SAMPLES:
        return []
    moves = []
    for kind, key in (("opener", "openers"), ("signoff", "signoff_classes"), ("starter", "starters")):
        min_share = SIGNATURE_MIN_SHARE * (2 if kind == "starter" else 1)  # starters are per sentence
        for pattern, c, s in block[key]:
            if not pattern or pattern == "none" or pattern.startswith("(none)"):
                continue
            if c >= SIGNATURE_MIN_COUNT and s >= min_share:
                moves.append({"kind": kind, "pattern": pattern, "count": c, "share": s})
    return moves


def never_candidates(block: dict, samples: int) -> dict:
    if samples < MIN_SAMPLES_FOR_NEVER:
        return {"confidence": "none", "terms": []}
    seen = block["_ai_terms_seen"]
    return {"confidence": "low" if samples < NEVER_LOW_CONFIDENCE_BELOW else "ok",
            "terms": [t for t in AI_PHRASES + AI_VOCAB if t not in seen]}


# ----------------------------------------------------------------------------- corpus
def load_corpus(home: Path, include_flagged: bool = False) -> list:
    path = home / "corpus.jsonl"
    if not path.is_file():
        sys.exit(f"ERROR: {path} not found — run voice-corpus/scripts/build_corpus.py first")
    rows, skipped_flagged = [], []
    with path.open(encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError as exc:
                sys.exit(f"ERROR: {path}:{i} invalid JSON ({exc})")
            if not isinstance(rec.get("text"), str) or not rec["text"].strip():
                continue
            if not include_flagged and "ai_leftover" in (rec.get("flags") or []):
                skipped_flagged.append(rec.get("id"))
                continue  # assistant leftovers stay in the corpus but never in the measurements
            rec.setdefault("register", "default")
            rec.setdefault("channel", rec["register"].split("-")[0])
            rows.append(rec)
    if skipped_flagged:
        print(f"WARN: skipped {len(skipped_flagged)} sample(s) flagged ai_leftover (assistant text); --include-flagged to measure them anyway", file=sys.stderr)
    if not rows:
        sys.exit(f"ERROR: {path} has no usable samples")
    return rows


def analyze(rows: list) -> dict:
    by_reg: dict = {}
    for r in rows:
        by_reg.setdefault(r["register"], []).append(r)
    out = {"version": VERSION, "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "registers": {}, "all": None}
    for reg in sorted(by_reg):
        recs = by_reg[reg]
        block = aggregate([message_features(r["text"]) for r in recs])
        samples = len(recs)
        dates = sorted(str(r.get("date")) for r in recs if r.get("date"))
        en_share = sum(1 for r in recs if r.get("lang", "en") == "en") / samples
        subjects = [r["subject"] for r in recs if isinstance(r.get("subject"), str) and r["subject"].strip()]
        entry = {
            "channel": recs[0].get("channel", reg.split("-")[0]),
            "samples": samples, "words": block["features"]["words_total"], "tier": tier_for(samples),
            "date_range": [dates[0], dates[-1]] if dates else None,
            "reply_share": round(sum(1 for r in recs if r.get("is_reply")) / samples, 3),
            "subject_words_median": statistics.median(len(words_of(s)) for s in subjects) if subjects else None,
            "english_share": round(en_share, 2),
            "lexicon_reliable": en_share >= LEXICON_LANG_SHARE,
            "signature_moves": signature_moves(block, samples),
            "never_candidates": never_candidates(block, samples),
        }
        entry.update({k: v for k, v in block.items() if not k.startswith("_")})
        out["registers"][reg] = entry
    block = aggregate([message_features(r["text"]) for r in rows])
    out["all"] = {"samples": len(rows), "words": block["features"]["words_total"], "tier": tier_for(len(rows)),
                  **{k: v for k, v in block.items() if not k.startswith("_")}}
    return out


def build_profile(metrics: dict, existing: dict, bans_new: list, keep_new: list) -> dict:
    """Canonical profile.json. User-confirmed bans/keeps survive re-analysis."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    bans = list(existing.get("bans", [])) if existing else []
    keep = list(existing.get("keep", [])) if existing else []
    known_b = {b["term"].lower() for b in bans}
    known_k = {k["form"].lower() for k in keep}
    for term in bans_new:
        t = term.strip()
        if t and not t.startswith("#") and t.lower() not in known_b:
            bans.append({"term": t, "scope": "all", "source": "user-confirmed", "added": now}); known_b.add(t.lower())
    for form in keep_new:
        f = form.strip()
        if f and not f.startswith("#") and f.lower() not in known_k:
            keep.append({"form": f, "source": "user-approved", "added": now}); known_k.add(f.lower())
    registers = {}
    for reg, e in metrics["registers"].items():
        registers[reg] = {k: e[k] for k in ("channel", "samples", "words", "tier", "reply_share",
                                             "subject_words_median", "lexicon_reliable", "bands",
                                             "greeting_classes", "signoff_classes", "openers",
                                             "signature_moves", "never_candidates")}
        registers[reg]["greeting_share"] = e["features"]["greeting_share"]
        registers[reg]["signoff_share"] = e["features"]["signoff_share"]
    a = metrics["all"]
    all_slice = {"channel": "all", "samples": a["samples"], "words": a["words"], "tier": a["tier"],
                 "reply_share": None, "subject_words_median": None, "lexicon_reliable": True,
                 "bands": a["bands"], "greeting_classes": a["greeting_classes"],
                 "signoff_classes": a["signoff_classes"], "openers": a["openers"],
                 "signature_moves": [], "never_candidates": {"confidence": "none", "terms": []},
                 "greeting_share": a["features"]["greeting_share"], "signoff_share": a["features"]["signoff_share"]}
    return {"version": PROFILE_VERSION, "generated": now, "metrics_version": metrics["version"],
            "corpus": {"samples": a["samples"], "words": a["words"], "tier": a["tier"]},
            "registers": registers, "all": all_slice, "bans": bans, "keep": keep,
            "notes": existing.get("notes", []) if existing else []}


def exemplar_ids(rows: list, per_register: int = 5) -> dict:
    """Stratified by length quartile, deterministic. Ids only — text stays in corpus.jsonl."""
    out = {}
    by_reg: dict = {}
    for r in rows:
        by_reg.setdefault(r["register"], []).append(r)
    for reg in sorted(by_reg):
        recs = sorted(by_reg[reg], key=lambda r: (r.get("words", len(words_of(r["text"]))), r.get("id", "")))
        n = len(recs)
        q = max(1, n // 4)
        buckets = [recs[i * q : (i + 1) * q] if i < 3 else recs[3 * q :] for i in range(4)]
        picks, i = [], 0
        while len(picks) < min(per_register, n) and i < 80:
            b = buckets[i % 4]
            if b:
                cand = b[((i // 4) * 7) % len(b)]
                if cand not in picks:
                    picks.append(cand)
            i += 1
        out[reg] = [{"id": r.get("id"), "words": r.get("words"), "date": r.get("date"), "note": ""} for r in picks]
    return out


def summary(metrics: dict) -> str:
    keys = ("msg_words_median", "sent_len_median", "contractions_per_100w", "hedges_per_100w", "polite_per_100w",
            "question_share", "exclaim_share", "greeting_share", "signoff_share", "lowercase_start_share",
            "emoji_msg_share", "em_dash_msg_share", "ai_vocab_per_1kw")
    out = ["register | n | words | tier | " + " | ".join(keys), "--- | --- | --- | --- | " + " | ".join("---" for _ in keys)]
    for reg, e in metrics["registers"].items():
        f = e["features"]
        out.append(f"{reg} | {e['samples']} | {e['words']} | {e['tier']} | " + " | ".join(str(f[k]) for k in keys))
    out.append("")
    for reg, e in metrics["registers"].items():
        b = e["bands"]
        out.append(f"## {reg} — length p10/p50/p90: {b['words']['p10']}/{b['words']['p50']}/{b['words']['p90']} words, "
                   f"paragraphs p90: {b['paras']['p90']}, replies: {e['reply_share']:.0%}")
        out.append("greetings: " + "; ".join(f"{p} ({s:.0%})" for p, c, s in e["greeting_classes"][:5]))
        out.append("sign-offs: " + "; ".join(f"{p} ({s:.0%})" for p, c, s in e["signoff_classes"][:5]))
        out.append("signature moves: " + ("; ".join(f"{m['kind']}:{m['pattern']} ({m['share']:.0%})" for m in e["signature_moves"])
                                           or f"none (needs ≥{SIGNATURE_MIN_SAMPLES} samples and ≥{SIGNATURE_MIN_COUNT} uses)"))
        if e["ai_hits"]:
            out.append("AI-default vocabulary present in YOUR corpus (not tells for you): " + ", ".join(f"{t}×{c}" for t, c in e["ai_hits"][:8]))
        nc = e["never_candidates"]
        out.append(f"never-candidates: {len(nc['terms'])} AI-default terms absent (confidence {nc['confidence']}; proposals — confirm via --bans)")
        if not e["lexicon_reliable"]:
            out.append(f"WARN: {reg} is {e['english_share']:.0%} English — lexicon features (contractions/hedges/polite/AI-vocab) unreliable")
        if e["tier"] == "provisional":
            out.append(f"WARN: {reg} is provisional ({e['samples']} samples) — exemplars only; do not trust its bands")
        out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--home", help="profile home (default: $PERSONAL_TONE_HOME, ./.personal-tone, ~/.personal-tone)")
    ap.add_argument("--text", help="analyze one document instead of the corpus; prints per-message feature JSON")
    ap.add_argument("--exemplars", action="store_true", help="also write exemplars.json (ids per register)")
    ap.add_argument("--write-profile", action="store_true", help="write/refresh the canonical profile.json")
    ap.add_argument("--bans", help="file of USER-CONFIRMED ban terms, one per line (implies --write-profile)")
    ap.add_argument("--keep", help="file of USER-APPROVED nonstandard forms to keep, one per line (implies --write-profile)")
    ap.add_argument("--registers", help='JSON file {"old": "new"} to relabel registers before analysis')
    ap.add_argument("--include-flagged", action="store_true", help="measure samples flagged ai_leftover too")
    ap.add_argument("--json", action="store_true", help="print metrics JSON to stdout")
    args = ap.parse_args()

    if args.text:
        p = Path(args.text)
        if not p.is_file():
            sys.exit(f"ERROR: {p} not found")
        m = message_features(p.read_text(encoding="utf-8", errors="replace"))
        for k in ("tokens", "hedge_hits", "booster_hits", "polite_hits", "sent_lens"):
            m.pop(k, None)
        m["ai_hits"] = dict(m["ai_hits"])
        print(json.dumps(m, ensure_ascii=False, indent=1))
        return 0

    home = resolve_home(args.home)
    rows = load_corpus(home, args.include_flagged)
    if args.registers:
        remap = json.loads(Path(args.registers).read_text(encoding="utf-8"))
        for r in rows:
            r["register"] = remap.get(r["register"], r["register"])
    metrics = analyze(rows)
    metrics["home"] = str(home)
    write_private(home / "metrics.json", json.dumps(metrics, ensure_ascii=False, indent=1))
    written = [home / "metrics.json"]
    if args.write_profile or args.bans or args.keep:
        pj = home / "profile.json"
        existing = {}
        if pj.is_file():
            existing = json.loads(pj.read_text(encoding="utf-8"))
            snap = int(existing.get("_snapshot", 0)) + 1
            write_private(home / f"profile.v{snap}.json", json.dumps(existing, ensure_ascii=False, indent=1))
        bans_new = Path(args.bans).read_text(encoding="utf-8").splitlines() if args.bans else []
        keep_new = Path(args.keep).read_text(encoding="utf-8").splitlines() if args.keep else []
        profile = build_profile(metrics, existing, bans_new, keep_new)
        profile["_snapshot"] = int(existing.get("_snapshot", 0)) + 1 if existing else 0
        write_private(pj, json.dumps(profile, ensure_ascii=False, indent=1))
        written.append(pj)
    if args.exemplars:
        write_private(home / "exemplars.json", json.dumps(exemplar_ids(rows), ensure_ascii=False, indent=1))
        written.append(home / "exemplars.json")
    if args.json:
        print(json.dumps(metrics, ensure_ascii=False, indent=1))
    else:
        print(summary(metrics))
        print("wrote " + ", ".join(str(p) for p in written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
