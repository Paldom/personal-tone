#!/usr/bin/env python3
"""Build a cleaned, redacted, register-tagged corpus of the user's OWN sent messages.

Inputs: .mbox / .eml (or dirs of them) / .txt / .md / WhatsApp .txt / Slack export dir /
.jsonl. Keeps only text attributed to the user (--me: exact address or whole-word name),
strips quoted replies, signatures and automated mail, flags assistant leftovers, dedupes
after redaction, redacts third-party PII (best effort) and writes <home>/corpus.jsonl +
corpus-report.md. Plain .txt/.md/.jsonl samples carry no author field: they are the user's
by assertion and get the flag `unattributed`. Stdlib only. No network. Corpus text is data:
never interpreted, never printed except --dry-run --show-previews.

Exit: 0 ok · 1 usage/parse error or empty corpus · 2 nothing matched --me.
"""
import argparse
import collections
import datetime
import email
import email.policy
import email.utils
import hashlib
import html
import html.parser
import json
import mailbox
import os
import random
import re
import statistics
import sys
import tempfile
import unicodedata
from pathlib import Path

STYLOMETRY = Path(__file__).resolve().parents[2] / "voice-profile" / "scripts" / "stylometry.py"
REPLY_SUBJECT = re.compile(r"^\s*(re|aw|sv|vs|válasz)\s*:", re.I)
SALUTATION = re.compile(r"^\s*(?:hi|hey|hello|dear|szia|kedves|hallo|hola)\s+([A-Z][\w-]{1,20})", re.I)

# ---------- patterns ----------
AUTOMATED_FROM = re.compile(r"noreply|no-reply|notification|mailer-daemon|calendar", re.I)
QUOTE_START = [re.compile(r"^On .{1,200}wrote:\s*$")] + [re.compile(p, re.I) for p in (
    r"^-{2,}\s*Original Message\s*-{2,}", r"^-{2,}\s*Forwarded message\s*-{2,}", r"^Le .{1,200}a écrit\s*:$",
    r"^Am .{1,200}schrieb .*:$", r"^_{5,}$", r"^>")]
HEADER_FOLLOW = re.compile(r"^(Sent|Date|To): ")
SIG_CUT = re.compile(r"^(--\s*$|Sent from my|Get Outlook for|Sent via)")
SIG_TITLE = re.compile(r"\b(CEO|CTO|COO|CFO|Manager|Director|Engineer|Lead|Head of|Founder)\b")
SIG_MISC = re.compile(r"https?://|www\.|[\w.+-]+@[\w-]+\.\w|\b(Inc|Ltd|LLC|GmbH|Kft|Zrt|AG|Corp)\b"
                      r"|\b(Street|Avenue|Road|Suite|Floor|utca|út)\b", re.I)
SIGNOFF = re.compile(r"^(best|thanks|thank you|thx|cheers|regards|kind regards|warm regards|best regards"
                     r"|all the best|many thanks|sincerely|talk soon|take care|br|yours|köszi|köszönöm|üdv"
                     r"|üdvözlettel|szia)\b", re.I)
AI_LEFTOVER = re.compile("|".join(re.escape(p) for p in (
    "would you like me to", "certainly!", "great question", "as an ai", "i hope this helps!",
    "here's a draft", "here is a draft", "let me know if you'd like me to", "i'd be happy to help",
    "feel free to ask")), re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"')\]]+")
# 7–15 digits with optional separators; ISO and d.m.yyyy dates excluded up front
PHONE_RE = re.compile(r"(?<![\w/])(?!\d{4}-\d\d-\d\d(?![\d-]))(?!\d{1,2}[.-]\d{1,2}[.-]\d{4}(?!\d))"
                      r"\+?\(?\d(?:[\s().-]{0,2}\d){6,14}(?![\w/])")
NUM_RE = re.compile(r"\d{9,}")
LETTER_RE = re.compile(r"[^\W\d_]")
HDR_LINE = re.compile(r"^(register|date|channel|audience|subject):\s*(.*)$", re.I)
WA_LINE = re.compile(r"^\[?(\d{1,2}[./]\d{1,2}[./]\d{2,4}),? (\d{1,2}:\d{2}(?::\d{2})?(?:\s?[AaPp]\.?[Mm]\.?)?)\]?"
                     r"\s*[-–]?\s*(?:([^:]{1,60}?): )?(.*)$")
WA_SYSTEM = re.compile(r"^(<media omitted>|\S*\s?(image|video|audio|sticker|gif|document|contact card) omitted"
                       r"|messages and calls are end-to-end encrypted|this message was deleted"
                       r"|you deleted this message)", re.I)
WA_MARKS = dict.fromkeys(map(ord, "‎‏"))  # LRM/RLM that iOS exports sprinkle in
SLACK_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")
SLACK_DM_ID = re.compile(r"^D[A-Z0-9]{6,}$")
# recipient first names that are also everyday words: never redacted globally
NAME_STOPLIST = {"will", "may", "june", "april", "march", "mark", "bill", "grace", "hope", "faith", "joy",
                 "rose", "sky", "ray", "art", "gene", "jack", "pat", "sue", "dawn", "summer", "chase", "chance",
                 "guy", "max", "don", "bob", "al", "ed", "ben", "sam", "van", "lee", "amber", "holly", "ivy", "rob",
                 "read", "page", "kay", "iris", "sunny", "wing", "long", "young", "king", "best", "moon"}
PUBLIC_MAIL = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "yahoo.com", "icloud.com",
               "me.com", "protonmail.com", "proton.me", "aol.com", "gmx.com", "gmx.de", "freemail.hu", "citromail.hu"}


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


# ---------- small helpers ----------
def own_names(me):
    """Lower-case words that are the user's own name: never redacted, protected as sign-off."""
    own = set()
    for m in me:
        own.update(w for w in re.split(r"[\s._-]+", m.split("@", 1)[0]) if len(w) >= 2)
        if "@" not in m:
            own.add(m)
    return own


def load_names(path):
    if not path:
        return set()
    if not Path(path).exists():
        die(f"--redact-names file not found: {path}")
    return {ln.strip().lower() for ln in Path(path).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")}


def norm_date(s):
    try:
        return datetime.date.fromisoformat(str(s)[:10]).isoformat()
    except ValueError:
        return None


def wa_order(dates):
    """Infer d/m vs m/d from the file itself; None when every date is ambiguous."""
    first = [int(m.group(1)) for d in dates for m in [re.match(r"(\d{1,2})[./](\d{1,2})", d)] if m]
    second = [int(m.group(2)) for d in dates for m in [re.match(r"(\d{1,2})[./](\d{1,2})", d)] if m]
    if any(x > 12 for x in first):
        return "dmy"
    if any(x > 12 for x in second):
        return "mdy"
    return None


def wa_date(s, order):
    if order is None:
        return None  # ambiguous export and no --date-order: leave the date unknown rather than guess
    fmts = ("%d/%m/%Y", "%d/%m/%y", "%d.%m.%Y", "%d.%m.%y") if order == "dmy" else ("%m/%d/%Y", "%m/%d/%y", "%m.%d.%Y", "%m.%d.%y")
    for fmt in fmts:
        try:
            return datetime.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def lang_of(text):
    words = text.split()
    non = sum(1 for w in words if any(c.isalpha() and ord(c) > 127 for c in w))
    return "other" if words and non / len(words) > 0.3 else "en"


def tier(n):  # same cut points as voice-profile/stylometry.py
    return "provisional" if n < 10 else "directional" if n < 30 else "solid" if n < 100 else "high"


def matches_me(s, me):
    """Exact address match, or whole-word display-name match — 'ann' must not match 'Joann'."""
    low = s.lower()
    addrs = {a.lower() for _, a in email.utils.getaddresses([s]) if a}
    for m in me:
        if "@" in m:
            if m in addrs or re.search(r"(?<![\w.+-])" + re.escape(m) + r"(?![\w.-])", low):
                return True
        elif re.search(r"(?<!\w)" + re.escape(m) + r"(?!\w)", low):
            return True
    return False


def sample(channel, register, audience, date, text, source, **kw):
    d = {"channel": channel, "register": register, "audience": audience, "date": date, "subject": None,
         "is_reply": None, "text": text, "source": source, "to_count": 0, "to_domains": [], "to_names": [], "flags": []}
    d.update(kw)
    return d


# ---------- email ----------
class _HTMLText(html.parser.HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "table"}

    def __init__(self):
        super().__init__()
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        self.skip += tag in ("script", "style")
        self.out.append("\n" * (tag in self.BLOCK))

    def handle_endtag(self, tag):
        self.skip -= tag in ("script", "style")
        self.out.append("\n" * (tag in self.BLOCK))

    def handle_data(self, data):
        self.out.append(data if self.skip <= 0 else "")


def html_to_text(s):
    p = _HTMLText()
    p.feed(s)
    p.close()
    return "".join(p.out)


def hdr(msg, name):
    try:
        return str(msg.get(name) or "")
    except Exception:  # malformed header: treat as absent
        return ""


def part_text(part):
    raw = part.get_payload(decode=True) or b""
    try:
        return raw.decode(part.get_content_charset() or "utf-8", errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def body_parts(msg):
    """Leaf parts of the message body only — attachments and attached messages
    (message/rfc822, someone else's mail) are skipped as whole subtrees."""
    if msg.get_content_disposition() == "attachment" or msg.get_content_type() == "message/rfc822":
        return
    if msg.is_multipart():
        for sub_ in msg.iter_parts():
            yield from body_parts(sub_)
    else:
        yield msg


def body_of(msg):
    """(text, calendar_only). Prefer text/plain, else text/html converted."""
    plain = html_ = None
    cal = False
    for part in body_parts(msg):
        ct = part.get_content_type()
        if ct == "text/plain" and plain is None:
            plain = part_text(part)
        elif ct == "text/html" and html_ is None:
            html_ = part_text(part)
        elif ct == "text/calendar":
            cal = True
    if plain is not None:
        return plain, False
    return (html_to_text(html_), False) if html_ is not None else (None, cal)


def email_date(msg):
    try:
        return email.utils.parsedate_to_datetime(hdr(msg, "Date")).date().isoformat()
    except (TypeError, ValueError, AttributeError):
        return None


def email_sample(msg, source, me, dropped):
    frm = hdr(msg, "From")
    if not matches_me(frm, me):
        dropped["not_me"] += 1
        return None
    auto = hdr(msg, "Auto-Submitted").lower()
    if AUTOMATED_FROM.search(frm) or (auto and auto != "no"):
        dropped["automated"] += 1
        return None
    body, cal = body_of(msg)
    if body is None:
        dropped["calendar_only" if cal else "empty"] += 1
        return None
    addrs = [x for x in email.utils.getaddresses([hdr(msg, "To"), hdr(msg, "Cc")]) if any(x)]
    names, domains = set(), []
    for name, addr in addrs:
        if "@" in addr:
            domains.append(addr.rsplit("@", 1)[1].lower())
        name = name.strip(" \"'").lower()
        if name and "@" not in name:  # full name + every token, so "Last, First" and surnames are covered too
            names.update([name] + [t for t in re.split(r"[\s,]+", name) if len(t) >= 2 and t.isalpha()])
    subject = hdr(msg, "Subject") or None
    return sample("email", None, None, email_date(msg), body, source, subject=subject,
                  is_reply=bool(hdr(msg, "In-Reply-To")) or bool(subject and REPLY_SUBJECT.match(subject)),
                  to_count=len(addrs), to_domains=domains, to_names=sorted(names),
                  flags=["broadcast"] if len(addrs) > 8 else [])


def load_mbox(path, me, dropped):
    box = mailbox.mbox(str(path), create=False,
                       factory=lambda f: email.message_from_binary_file(f, policy=email.policy.default))
    out = [s for s in (email_sample(m, path.name, me, dropped) for m in box) if s]
    box.close()
    return out


def load_eml(path, me, dropped):
    with open(path, "rb") as f:
        s = email_sample(email.message_from_binary_file(f, policy=email.policy.default), path.name, me, dropped)
    return [s] if s else []


# ---------- cleaning ----------
def cut_quotes(lines):
    n = len(lines)
    for i, ln in enumerate(lines):
        s = ln.rstrip()
        if any(r.match(s) for r in QUOTE_START):
            return lines[:i]
        if s.startswith("On ") and i + 1 < n and QUOTE_START[0].match(s + " " + lines[i + 1].strip()):
            return lines[:i]
        if s.startswith("From: ") and any(HEADER_FOLLOW.match(lines[j]) for j in range(i + 1, min(i + 4, n))):
            return lines[:i]
    return lines


def is_signoff(s, own):
    """1–6 word sign-off ("Best, Dom", "Thanks!", "Cheers") or a lone own first name: never cut."""
    words = s.split()
    return 1 <= len(words) <= 6 and (bool(SIGNOFF.match(s)) or (len(words) == 1 and s.lower().strip(",.!-") in own))


def is_sig_marker(s):
    return len(s.split()) <= 12 and bool(SIG_TITLE.search(s) or SIG_MISC.search(s) or PHONE_RE.search(s))


def cut_signature(lines, own):
    for i, ln in enumerate(lines):
        if SIG_CUT.match(ln):
            lines = lines[:i]
            break
    end = len(lines)
    while end and not lines[end - 1].strip():
        end -= 1
    i, markers = end, 0
    while i:  # walk the trailing block bottom-up; a sign-off line always stops the cut
        s = lines[i - 1].strip()
        if not s or is_signoff(s, own):
            break
        if is_sig_marker(s):
            markers += 1
        elif not (markers and len(s.split()) <= 6 and not s.endswith((".", "?", "!"))
                  and all(w[0].isupper() for w in s.split() if w[0].isalpha())):
            break  # not a Title-Case name/company line sitting above a marker: body text
        i -= 1
    # ponytail: one bare URL/phone line can be body, so cut needs 2 markers or a job title; a lone www. line survives
    cut = markers >= 2 or (markers and any(SIG_TITLE.search(x) for x in lines[i:end]))
    return lines[:i] if cut else lines[:end]


def clean_email(text, own):
    return "\n".join(cut_signature(cut_quotes(text.splitlines()), own))


def tidy(text):
    text = unicodedata.normalize("NFC", text).replace("\xa0", " ")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(ln.rstrip() for ln in text.splitlines())).strip()


def redact(text, names, counter):
    n = 0
    for key, rx, rep in (("email", EMAIL_RE, "[email]"), ("url", URL_RE, "[url]"),
                         ("number", NUM_RE, "[number]"), ("phone", PHONE_RE, "[phone]")):
        text, k = rx.subn(rep, text)
        counter[key] += k
        n += k
    if names:
        # ponytail: word-boundary only; a recipient called "Will" or "May" also hits the common word (stoplist later)
        rx = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(x) for x in sorted(names, key=len, reverse=True))
                        + r")(?!\w)", re.I)
        text, k = rx.subn("[name]", text)
        counter["name"] += k
        n += k
    return text, n


# ---------- other sources ----------
def load_doc(path, lines, register):
    meta, i = {}, 0
    while i < len(lines) and HDR_LINE.match(lines[i]):
        m = HDR_LINE.match(lines[i])
        meta[m.group(1).lower()] = m.group(2).strip()
        i += 1
    return [sample(meta.get("channel", "doc"), meta.get("register") or register or "doc", meta.get("audience"),
                   norm_date(meta.get("date")), "\n".join(lines[i:]), path.name, subject=meta.get("subject"),
                   flags=["unattributed"])]


def load_whatsapp(path, lines, me, dropped, date_order=None):
    heads = [WA_LINE.match(ln.translate(WA_MARKS)) for ln in lines]
    order = date_order or wa_order([m.group(1) for m in heads if m])
    if order is None:
        print(f"WARN: {path.name}: day/month order is ambiguous in every date — dates left unknown; pass --date-order dmy|mdy", file=sys.stderr)
    msgs = []  # [sender, date, [lines]] or None for a system line (ends any continuation)
    for ln, m in zip(lines, heads):
        if m:
            msgs.append([m.group(3).strip(), wa_date(m.group(1), order), [m.group(4)]] if m.group(3) else None)
        elif msgs and msgs[-1] is not None:
            msgs[-1][2].append(ln)
    msgs = [x for x in msgs if x]
    senders = {x[0] for x in msgs}
    aud = "dm" if len(senders) == 2 else "group"
    out = []
    for name, date, tl in msgs:
        text = "\n".join(tl).strip()
        if not matches_me(name, me):
            dropped["not_me"] += 1
        elif WA_SYSTEM.match(text):
            dropped["system"] += 1
        else:
            out.append(sample("chat", "chat-" + aud, aud, date, text, path.name, to_count=len(senders) - 1))
    return out


def load_textfile(path, me, dropped, register, date_order=None):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if any(WA_LINE.match(ln.translate(WA_MARKS)) for ln in [x for x in lines if x.strip()][:5]):
        return load_whatsapp(path, lines, me, dropped, date_order)
    return load_doc(path, lines, register)


def slack_text(t):
    t = re.sub(r"<@[UW][A-Z0-9]+(?:\|[^>]*)?>", "[name]", t)
    t = re.sub(r"<(?:https?|mailto):[^>|]*(?:\|[^>]*)?>", "[url]", t)
    t = re.sub(r"<#[A-Z0-9]+\|([^>]*)>", r"#\1", t)
    return html.unescape(re.sub(r"<!(here|channel|everyone)>", r"@\1", t))


def load_slack(root, me, dropped):
    hits = []
    for u in json.loads((root / "users.json").read_text(encoding="utf-8")):
        pr = u.get("profile") or {}
        fields = [u.get("name"), u.get("real_name"), pr.get("real_name"), pr.get("display_name"), pr.get("email")]
        if any(matches_me(str(f), me) for f in fields if f):
            hits.append(u)
    if not hits:
        die(f"--me {me} matched no user in {root / 'users.json'} (name/real_name/email)", 2)
    if len(hits) > 1:
        die(f"--me {me} is ambiguous in {root / 'users.json'}: " + ", ".join(f"{u['id']}={u.get('name')}" for u in hits) + " — pass the email or exact handle", 2)
    uid = hits[0]["id"]
    dm_ids = set()
    for f in ("dms.json", "mpims.json"):
        if (root / f).exists():
            for c in json.loads((root / f).read_text(encoding="utf-8")):
                dm_ids.update(x for x in (c.get("id"), c.get("name")) if x)
    out = []
    for day in sorted(root.glob("*/*.json")):
        if not SLACK_DAY.match(day.name):
            continue
        folder = day.parent.name
        aud = "dm" if SLACK_DM_ID.match(folder) or folder in dm_ids else "group"
        for msg in json.loads(day.read_text(encoding="utf-8")):
            if msg.get("user") != uid:
                dropped["not_me"] += 1
            elif msg.get("subtype") not in (None, "thread_broadcast"):
                dropped["system"] += 1
            else:
                out.append(sample("chat", "chat-" + aud, aud, day.stem, slack_text(msg.get("text", "")),
                                  f"{folder}/{day.name}"))
    return out


def load_jsonl(path):
    out = []
    for i, ln in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not ln.strip():
            continue
        try:
            d = json.loads(ln)
        except json.JSONDecodeError as e:
            die(f"{path}:{i}: bad JSON ({e.msg})")
        if isinstance(d, dict) and isinstance(d.get("text"), str):
            out.append(sample(d.get("channel") or "doc", d.get("register") or "doc", d.get("audience"),
                              norm_date(d.get("date")), d["text"], path.name, subject=d.get("subject"),
                              flags=["unattributed"]))
    return out


def load_input(path, me, dropped, register, date_order=None):
    if path.is_dir():
        if (path / "users.json").exists():
            return load_slack(path, me, dropped)
        files = sorted(p for p in path.rglob("*") if p.suffix.lower() in (".eml", ".mbox", ".txt", ".md", ".jsonl"))
        return [s for f in files for s in load_input(f, me, dropped, register, date_order)]
    ext = path.suffix.lower()
    if ext == ".mbox":
        return load_mbox(path, me, dropped)
    if ext == ".eml":
        return load_eml(path, me, dropped)
    if ext == ".jsonl":
        return load_jsonl(path)
    if ext in (".txt", ".md"):
        return load_textfile(path, me, dropped, register, date_order)
    die(f"unsupported input (expected .mbox/.eml/.txt/.md/.jsonl, a dir of them, or a Slack export dir): {path}")


# ---------- assemble ----------
def finalize(raw, a, own, names, internal, since, until, dropped, redactions, previews):
    seen, out, ids = set(), [], set()
    for s in raw:
        text = tidy(clean_email(s["text"], own) if s["channel"] == "email" else s["text"])
        words = len(text.split())
        flags = list(s["flags"])
        rnames = set(names) if a.no_redact_recipients else set(names) | (set(s["to_names"]) - own - NAME_STOPLIST)
        if not a.no_redact_recipients:  # the salutation names the user typed are recipients too
            first = next((ln for ln in text.splitlines() if ln.strip()), "")
            m = SALUTATION.match(first)
            if m and m.group(1).lower() not in own:
                if m.group(1).lower() in NAME_STOPLIST:  # "Hi Will," — redact in the greeting only, never the verb
                    text = text.replace(first, first[: m.start(1)] + "[name]" + first[m.end(1):], 1)
                    redactions["name"] += 1
                else:
                    rnames.add(m.group(1).lower())
        text, n = redact(text, rnames, redactions)
        norm = " ".join(text.lower().split())  # dedupe AFTER redaction: same text to two people is one template
        ai = bool(AI_LEFTOVER.search(text.replace("’", "'")))
        reason = ("unknown_date" if (since or until) and not s["date"] and not a.include_undated else
                  "before_since" if since and s["date"] and s["date"] < since else
                  "after_until" if until and s["date"] and s["date"] > until else
                  "too_short" if words < a.min_words else
                  "too_long" if words > a.max_words else
                  "no_letters" if not LETTER_RE.search(text) else
                  "ai_leftover" if ai and a.drop_flagged else
                  "duplicate" if norm in seen else None)
        if reason:
            dropped[reason] += 1
            if len(previews[reason]) < 5:
                previews[reason].append(f"{s['source']}: {text[:60]!r}")
            continue
        if ai:
            flags.append("ai_leftover")
        seen.add(norm)
        subject = None
        if s["subject"]:
            subject, k = redact(s["subject"], rnames, redactions)
            n += k
        register, audience = s["register"], s["audience"]
        if s["channel"] == "email":
            doms = s["to_domains"]
            audience = "internal" if doms and all(d in internal for d in doms) else "external"
            register = "email-" + audience
        sid = f"{s['channel'][0]}-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]}"
        while sid in ids:  # dedupe makes this near-impossible; keep ids unique regardless
            sid += "x"
        ids.add(sid)
        out.append({
            "id": sid,
            "register": a.register or register, "channel": s["channel"], "audience": audience,
            "date": s["date"], "lang": lang_of(text), "words": len(text.split()), "subject": subject,
            "is_reply": s["is_reply"], "text": text, "source": s["source"], "to_count": s["to_count"],
            "flags": flags + ([f"redacted:{n}"] if n else []),
        })
    out.sort(key=lambda r: (r["date"] or "9999-99-99", r["id"]))
    return out


def summarize(recs, dropped, redactions, home):
    regs = {}
    for reg in sorted({r["register"] for r in recs}):
        rs = [r for r in recs if r["register"] == reg]
        dates = sorted(r["date"] for r in rs if r["date"])
        regs[reg] = {"samples": len(rs), "words": sum(r["words"] for r in rs),
                     "median_words": int(statistics.median(r["words"] for r in rs)),
                     "date_from": dates[0] if dates else None, "date_to": dates[-1] if dates else None,
                     "tier": tier(len(rs))}
    return {"home": str(home), "samples": len(recs), "words": sum(r["words"] for r in recs), "registers": regs,
            "dropped": dict(sorted(dropped.items())), "redactions": dict(sorted(redactions.items())),
            "next": f"python3 {STYLOMETRY} --home {home}"}


def report_md(s):
    L = [f"# Corpus report — {datetime.date.today().isoformat()}", "",
         f"Home: `{s['home']}` · samples: {s['samples']} · words: {s['words']}", "",
         "| register | samples | words | median words/sample | date range | tier |",
         "| --- | ---: | ---: | ---: | --- | --- |"]
    for reg, st in s["registers"].items():
        rng = f"{st['date_from']} → {st['date_to']}" if st["date_from"] else "n/a"
        L.append(f"| {re.sub(chr(92) + 's+', ' ', reg)} | {st['samples']} | {st['words']} | {st['median_words']} | {rng} | {st['tier']} |")
    L += ["", "Tiers: <10 provisional · 10–29 directional · 30–99 solid · 100+ high", "",
          "## Dropped", "", "| reason | count |", "| --- | ---: |"]
    L += [f"| {k} | {v} |" for k, v in s["dropped"].items()] or ["| (nothing) | 0 |"]
    L += ["", "## Redactions", "", ", ".join(f"{k}: {v}" for k, v in s["redactions"].items()) or "none", "",
          "## Next step", "", f"    {s['next']}", "",
          "Privacy: local only. The home dir is chmod 700 with a `.gitignore` of `*`; never commit or share "
          "`corpus.jsonl` — a voice corpus is an attribution key."]
    return "\n".join(L)


def resolve_home(arg, create):
    # ponytail: no implicit project-local default — a repo-controlled ./.personal-tone must be
    # chosen explicitly (--home or PERSONAL_TONE_HOME), never picked up because it exists
    home = Path(arg or os.environ.get("PERSONAL_TONE_HOME") or "~/.personal-tone").expanduser()
    if home.is_symlink() or any((home / n).is_symlink() for n in ("corpus.jsonl", "corpus-report.md")):
        die(f"{home} (or an output file in it) is a symlink — refusing; the profile home must be a real private directory")
    if create:
        home.mkdir(parents=True, exist_ok=True)
        os.chmod(home, 0o700)
        gi = home / ".gitignore"
        if not gi.exists():
            gi.write_text("*\n", encoding="utf-8")
        elif "*" not in [ln.strip() for ln in gi.read_text(encoding="utf-8").splitlines()]:
            die(f"{gi} exists but does not ignore '*' — refusing to write an attribution key into a tracked folder")
    return home


def parse_args(argv):
    class P(argparse.ArgumentParser):
        def error(self, message):  # usage errors exit 1; argparse's default 2 is reserved for "nothing matched --me"
            die(message, 1)

    ap = P(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", metavar="INPUT", help=".mbox/.eml/.txt/.md/.jsonl, dir of them, Slack export")
    ap.add_argument("--me", action="append", required=True, help="your address or display-name substring (repeatable)")
    ap.add_argument("--internal-domain", action="append", default=[], help="domain counted as internal (repeatable)")
    ap.add_argument("--home", help="profile home (default: $PERSONAL_TONE_HOME, else ~/.personal-tone; never implicit ./.personal-tone)")
    ap.add_argument("--register", help="force this register on every sample")
    ap.add_argument("--min-words", type=int, default=3)
    ap.add_argument("--max-words", type=int, default=1500)
    ap.add_argument("--redact-names", metavar="FILE", help="one name per line to replace with [name]")
    ap.add_argument("--no-redact-recipients", action="store_true")
    ap.add_argument("--since", metavar="YYYY-MM-DD")
    ap.add_argument("--until", metavar="YYYY-MM-DD", help="ignore samples after this date (e.g. pre-AI-assistant mail)")
    ap.add_argument("--include-undated", action="store_true", help="with --since/--until: keep records whose date is unknown (dropped by default)")
    ap.add_argument("--drop-flagged", action="store_true", help="drop samples with assistant leftovers instead of keeping them flagged (voice-profile skips flagged samples by default)")
    ap.add_argument("--date-order", choices=("dmy", "mdy"), help="WhatsApp date order when the export is ambiguous")
    ap.add_argument("--show-previews", action="store_true", help="with --dry-run: print short sample/drop previews (they enter the agent's context)")
    ap.add_argument("--dry-run", action="store_true", help="print the report, write nothing")
    ap.add_argument("--json", action="store_true", help="print the summary as JSON instead of the report")
    return ap.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)
    me = [m.strip().lower() for m in a.me if m.strip()]
    if not me or any(len(m) < 2 for m in me):
        die("--me must be a non-empty address or name (at least 2 characters)")
    own = own_names(me)
    internal = {d.lower().lstrip("@") for d in a.internal_domain} or {m.split("@", 1)[1] for m in me if "@" in m}
    if not a.internal_domain and internal & PUBLIC_MAIL:
        print(f"WARN: {sorted(internal & PUBLIC_MAIL)} is a public mail provider, not an internal domain — all email counts as external; pass --internal-domain to change", file=sys.stderr)
        internal -= PUBLIC_MAIL
    names = load_names(a.redact_names) - own
    since = norm_date(a.since) if a.since else None
    until = norm_date(a.until) if a.until else None
    if (a.since and not since) or (a.until and not until):
        die("--since/--until must be YYYY-MM-DD")
    previews = collections.defaultdict(list)
    dropped, redactions, raw = collections.Counter(), collections.Counter(), []
    for p in a.inputs:
        if not Path(p).exists():
            die(f"input not found: {p}")
        raw.extend(load_input(Path(p), me, dropped, a.register, a.date_order))
    if not raw and dropped["not_me"]:
        die(f"no message matched --me {a.me} but {dropped['not_me']} came from others: pass your exact From "
            "address or display name as it appears in the export", 2)
    recs = finalize(raw, a, own, names, internal, since, until, dropped, redactions, previews) if raw else []
    if not recs:
        die(f"zero samples left after cleaning; dropped: {dict(sorted(dropped.items()))}")
    home = resolve_home(a.home, create=not a.dry_run)
    summary = summarize(recs, dropped, redactions, home)
    for reg, st in summary["registers"].items():
        if st["tier"] == "provisional":
            print(f"WARN: register {reg} has {st['samples']} sample(s): provisional, aim for 25+", file=sys.stderr)
    if not a.dry_run:
        staged = []
        try:  # stage both outputs as unpredictable 0600 temp files, then rotate — never a half-written corpus
            for name, payload in (("corpus.jsonl", "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs)),
                                  ("corpus-report.md", report_md(summary) + "\n")):
                fd, tmp = tempfile.mkstemp(prefix=f".{name}.", dir=str(home))
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(payload)
                staged.append((tmp, home / name))
            if (home / "corpus.jsonl").exists():
                os.replace(str(home / "corpus.jsonl"), str(home / "corpus.prev.jsonl"))  # one backup of the last build
            for tmp, dest in staged:
                os.replace(tmp, str(dest))
        except BaseException:
            for tmp, _ in staged:
                Path(tmp).unlink(missing_ok=True)
            raise
    if a.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(report_md(summary))
        if a.dry_run and not a.show_previews:
            print("\n(dry run: counts and reasons only; add --show-previews to see sample and drop excerpts — they enter the agent's context)")
        if a.dry_run and a.show_previews:
            print("\nSample previews (dry run, seeded):")
            for r in random.Random(0).sample(recs, min(3, len(recs))):
                print(f"  [{r['register']}] {r['text'][:80]!r}")
            if previews:
                print("\nDropped examples (up to 5 per reason; adjust --min-words / --max-words / --include-undated to keep):")
                for reason, items in sorted(previews.items()):
                    for it in items:
                        print(f"  {reason}: {it}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
