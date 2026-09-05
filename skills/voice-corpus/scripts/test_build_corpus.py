#!/usr/bin/env python3
"""Self-test for build_corpus.py: synthetic mbox + WhatsApp + Slack + md in a temp dir."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().with_name("build_corpus.py")

MBOX = """From alex@example.com Mon Mar  2 10:00:00 2026
From: Alex Example <alex@example.com>
To: Anna Kovacs <anna@client.com>
Subject: Re: Deck
Date: Mon, 2 Mar 2026 11:00:00 +0100
Content-Type: text/plain; charset="utf-8"

Hi Anna,

Thanks for sending the deck over, I will go through it tonight and call you at +36 30 123 4567 tomorrow.

Best,
Alex

Alex Example
CTO, Example Ltd
+36 30 999 8888
www.example.com

On Mon, 2 Mar 2026 at 10:00, Anna Kovacs <anna@client.com>
wrote:
> Hi Alex, here is the deck we discussed.

From alex@example.com Tue Mar  3 09:00:00 2026
From: Alex Example <alex@example.com>
To: bob@example.com
Subject: standup
Date: Tue, 3 Mar 2026 09:00:00 +0100
Content-Type: text/plain; charset="utf-8"

Quick one, can we move standup to ten tomorrow? I have the dentist at nine.

From alex@example.com Wed Mar  4 09:00:00 2026
From: Alex Example <alex@example.com>
To: bob@example.com
Subject: proposal
Date: Wed, 4 Mar 2026 09:00:00 +0100
Content-Type: text/plain; charset="utf-8"

Certainly! Here's a draft of the proposal you asked for, let me know what you think.

From anna@client.com Thu Mar  5 09:00:00 2026
From: Anna Kovacs <anna@client.com>
To: Alex Example <alex@example.com>
Subject: Re: Deck
Date: Thu, 5 Mar 2026 09:00:00 +0100
Content-Type: text/plain; charset="utf-8"

Great, thanks Alex, looking forward to your comments on the deck.

From noreply@calendar.google.com Fri Mar  6 09:00:00 2026
From: Alex Example via Calendar <noreply@calendar.google.com>
To: bob@example.com
Subject: Invitation: standup
Date: Fri, 6 Mar 2026 09:00:00 +0100
Content-Type: text/plain; charset="utf-8"

You have been invited to the following event, standup at ten, by Alex Example.

From alex@example.com Sat Mar  7 09:00:00 2026
From: Alex Example <alex@example.com>
To: carol@example.com
Subject: standup again
Date: Sat, 7 Mar 2026 09:00:00 +0100
Content-Type: text/plain; charset="utf-8"

Quick one, can we move standup to ten tomorrow? I have the dentist at nine.

"""

WA_DM = """[13/03/2026, 14:03:11] Messages and calls are end-to-end encrypted. No one outside of this chat can read them.
[12/03/2026, 14:03:20] Anna Kovacs: hey, can you send the deck?
[12/03/2026, 14:04:02] Alex Example: Sure, I can send the deck over tonight
after the call, give me an hour or so
[12/03/2026, 14:04:30] Alex Example: <Media omitted>
[12/03/2026, 14:05:00] Alex Example: ok
"""

WA_GROUP = """13/03/2026, 15:00 - Anna Kovacs: who is joining the offsite next week?
12/03/2026, 15:01 - Bob Smith: me
12/03/2026, 15:02 - Alex Example: I am in, will book the train tickets tonight for all of us
"""

USERS = [
    {"id": "U01", "name": "alex", "real_name": "Alex Example", "profile": {"email": "alex@example.com"}},
    {"id": "U02", "name": "bob", "real_name": "Bob Smith", "profile": {"email": "bob@example.com"}},
]
SLACK_DM = [
    {"user": "U01", "ts": "1.0", "text": "Hey <@U02> can you review the PR today? <https://github.com/x/y|link>"},
    {"user": "U02", "ts": "2.0", "text": "sure, on it after lunch, will ping you"},
]
SLACK_CHAN = [
    {"user": "U01", "ts": "3.0", "subtype": "channel_join", "text": "<@U01> has joined the channel"},
    {"user": "U01", "ts": "4.0", "text": "Deploy is done, please smoke test the staging env when you can folks"},
]

EML = """From: Alex Example <alex@example.com>
To: "Kovacs, Anna" <anna@client.com>, bob@partner.io
Cc: Alex Example <alex@example.com>
Subject: =?utf-8?q?Sz=C3=A9p_napot?=
Date: Sun, 1 Mar 2026 09:00:00 +0100
Content-Type: text/html; charset="utf-8"

<html><head><style>p{color:red}</style></head><body>
<div>Hi Anna,</div><div><br></div>
<div>Ping me on +1 (555) 123-4567 or alex@example.com, the spec is at https://example.com/spec?x=1.</div>
<div>Deadline is 2026-03-12 and the order id is 123456789012.</div>
<div><br></div><div>Cheers</div>
<div class="gmail_quote">On Sat, Feb 28, 2026 at 10:00 AM Anna Kovacs &lt;anna@client.com&gt; wrote:<br>
<blockquote>Old text here that must vanish.</blockquote></div>
<script>alert(1)</script></body></html>
"""

POST_MD = """register: post
channel: post
date: 2026-01-15

Shipped the new onboarding flow today, three weeks from idea to production and no rollback needed.
"""


def run(*args):
    p = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


class BuildCorpusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        (root / "sent.mbox").write_text(MBOX, encoding="utf-8")
        (root / "wa_dm.txt").write_text(WA_DM, encoding="utf-8")
        (root / "wa_group.txt").write_text(WA_GROUP, encoding="utf-8")
        (root / "post.md").write_text(POST_MD, encoding="utf-8")
        (root / "eml").mkdir()
        (root / "eml" / "one.eml").write_text(EML, encoding="utf-8")
        slack = root / "slack"
        (slack / "D01ABCDEF").mkdir(parents=True)
        (slack / "general").mkdir()
        (slack / "users.json").write_text(json.dumps(USERS))
        (slack / "D01ABCDEF" / "2026-03-01.json").write_text(json.dumps(SLACK_DM))
        (slack / "general" / "2026-03-02.json").write_text(json.dumps(SLACK_CHAN))
        cls.home = root / "home"
        cls.inputs = [str(root / n) for n in ("sent.mbox", "wa_dm.txt", "wa_group.txt", "post.md", "slack", "eml")]
        code, out, err = run(*cls.inputs, "--me", "alex@example.com", "--me", "Alex Example",
                             "--internal-domain", "example.com", "--home", str(cls.home), "--json")
        assert code == 0, (code, out, err)
        cls.summary = json.loads(out)
        cls.recs = [json.loads(l) for l in (cls.home / "corpus.jsonl").read_text().splitlines()]
        cls.by_reg = {}
        for r in cls.recs:
            cls.by_reg.setdefault(r["register"], []).append(r)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_only_own_messages_kept(self):
        self.assertEqual(len(self.recs), 9)  # incl. the flagged assistant-leftover sample
        texts = " ".join(r["text"] for r in self.recs)
        self.assertNotIn("looking forward to your comments", texts)  # Anna's email
        self.assertNotIn("can you send the deck", texts)  # Anna on WhatsApp
        self.assertNotIn("after lunch", texts)  # Bob on Slack
        self.assertNotIn("invited to the following event", texts)  # noreply

    def test_email_cleaning_and_redaction(self):
        r = next(r for r in self.recs if r["source"] == "sent.mbox" and r["audience"] == "external")
        self.assertNotIn("deck we discussed", r["text"])
        self.assertNotIn("wrote:", r["text"])
        self.assertNotIn("CTO", r["text"])
        self.assertNotIn("999 8888", r["text"])
        self.assertIn("Best,\nAlex", r["text"])
        self.assertTrue(r["text"].endswith("Best,\nAlex"), r["text"])
        self.assertIn("[phone]", r["text"])
        self.assertNotIn("+36", r["text"])
        self.assertIn("Hi [name],", r["text"])
        self.assertNotIn("Anna", r["text"])
        self.assertTrue(any(f.startswith("redacted:") for f in r["flags"]), r["flags"])
        self.assertEqual(r["subject"], "Re: Deck")
        self.assertEqual(r["date"], "2026-03-02")
        self.assertEqual(r["audience"], "external")
        self.assertEqual(r["to_count"], 1)

    def test_html_eml(self):
        r = next(r for r in self.recs if r["source"] == "one.eml")
        self.assertEqual(r["subject"], "Szép napot")  # RFC 2047 decoded
        self.assertEqual(r["text"], "Hi [name],\n\nPing me on [phone] or [email], the spec is at [url]\n\n"
                                    "Deadline is 2026-03-12 and the order id is [number].\n\nCheers")
        self.assertEqual((r["register"], r["to_count"], r["flags"]), ("email-external", 3, ["redacted:5"]))

    def test_drop_reasons(self):
        d = self.summary["dropped"]
        self.assertNotIn("ai_leftover", d)  # kept, flagged (voice-profile skips it); --drop-flagged drops it
        flagged = [r for r in self.recs if "ai_leftover" in r["flags"]]
        self.assertEqual(len(flagged), 1)
        self.assertIn("Certainly", flagged[0]["text"])
        code, out, _ = run(*self.inputs, "--me", "alex@example.com", "--me", "Alex Example", "--internal-domain", "example.com",
                           "--home", str(self.home / "drop"), "--drop-flagged", "--json")
        self.assertEqual(json.loads(out)["dropped"]["ai_leftover"], 1)
        self.assertEqual(d["duplicate"], 1)
        self.assertEqual(d["automated"], 1)
        self.assertEqual(d["not_me"], 5)  # Anna email, Anna WA, Anna+Bob WA group, Bob Slack
        self.assertEqual(d["system"], 2)  # <Media omitted> + channel_join
        self.assertEqual(d["too_short"], 1)  # "ok"

    def test_registers(self):
        regs = {k: len(v) for k, v in self.by_reg.items()}
        self.assertEqual(regs, {"email-external": 2, "email-internal": 2, "chat-dm": 2, "chat-group": 2, "post": 1})
        internal = next(r for r in self.by_reg["email-internal"] if "standup to ten" in r["text"])
        self.assertEqual(internal["audience"], "internal")
        sources = {r["source"] for r in self.by_reg["chat-dm"]}
        self.assertEqual(sources, {"wa_dm.txt", "D01ABCDEF/2026-03-01.json"})
        sources = {r["source"] for r in self.by_reg["chat-group"]}
        self.assertEqual(sources, {"wa_group.txt", "general/2026-03-02.json"})
        (post,) = self.by_reg["post"]
        self.assertEqual((post["channel"], post["date"], post["id"][:2]), ("post", "2026-01-15", "p-"))

    def test_chat_details(self):
        wa = next(r for r in self.recs if r["source"] == "wa_dm.txt")
        self.assertEqual(wa["text"], "Sure, I can send the deck over tonight\nafter the call, give me an hour or so")
        self.assertEqual(wa["date"], "2026-03-12")  # order inferred from the 13/03 line in the same file
        slack = next(r for r in self.recs if r["source"].startswith("D01"))
        self.assertEqual(slack["text"], "Hey [name] can you review the PR today? [url]")

    def test_record_shape_and_order(self):
        keys = ["id", "register", "channel", "audience", "date", "lang", "words", "subject", "is_reply", "text", "source",
                "to_count", "flags"]
        for r in self.recs:
            self.assertEqual(list(r), keys)
            self.assertEqual(r["words"], len(r["text"].split()))
            self.assertEqual(r["lang"], "en")
        self.assertEqual([r["date"] or "9999-99-99" for r in self.recs], sorted(r["date"] or "9999-99-99" for r in self.recs))
        code, out, _ = run(*self.inputs, "--me", "alex@example.com", "--me", "Alex Example",
                           "--internal-domain", "example.com", "--home", str(self.home), "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), self.summary)  # deterministic
        self.assertEqual([json.loads(l) for l in (self.home / "corpus.jsonl").read_text().splitlines()], self.recs)

    def test_home_dir_and_report(self):
        self.assertEqual(stat.S_IMODE(os.stat(self.home).st_mode), 0o700)
        self.assertEqual((self.home / ".gitignore").read_text(), "*\n")
        report = (self.home / "corpus-report.md").read_text()
        for needle in ("| email-external | 2 |", "provisional", "| duplicate | 1 |", "stylometry.py --home",
                       "chmod 700"):
            self.assertIn(needle, report)
        self.assertNotIn("standup to ten", report)  # no message text in the report

    def test_exit_2_when_me_matches_nothing(self):
        code, out, err = run(self.inputs[0], "--me", "nobody@example.com", "--home", str(self.home))
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("ERROR:"), err)
        self.assertIn("--me", err)

    def test_dry_run_writes_nothing(self):
        home = Path(self.tmp.name) / "dry-home"
        code, out, err = run(self.inputs[0], "--me", "alex@example.com", "--home", str(home), "--dry-run", "--show-previews")
        self.assertEqual(code, 0, err)
        self.assertFalse(home.exists())
        self.assertIn("Sample previews", out)

    def test_usage_error_is_exit_1(self):
        code, _, err = run(self.inputs[0])  # missing --me
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("ERROR:"), err)


class GateFixesTest(unittest.TestCase):
    """Regressions from the implementation review: identity matching, MIME attachments, undated cutoffs, name stoplist."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        import email.message, mailbox
        box = mailbox.mbox(str(self.root / "m.mbox"))
        def add(frm, to, subject, body, attach=None, date="Mon, 02 Mar 2026 10:00:00 +0000"):
            m = email.message.EmailMessage()
            m["From"], m["To"], m["Subject"] = frm, to, subject
            if date:
                m["Date"] = date
            m.set_content(body)
            if attach:
                inner = email.message.EmailMessage(); inner["From"] = "Third Party <tp@else.com>"; inner["Subject"] = "fwd"
                inner.set_content(attach)
                m.add_attachment(inner)
            box.add(m)
        add("Ann Lee <ann@corp.com>", "Will Smith <will@else.com>", "hi", "Hi Will,\n\nI will send the deck tonight, will do.\n\nBest,\nAnn")
        add("Joann Other <joann@corp.com>", "x@else.com", "no", "Not Ann's message at all, twenty words of someone else talking about nothing in particular here")
        add("Ann Lee <ann@corp.com>", "y@else.com", "attach", "Outer body from Ann with enough words to pass the minimum easily.", attach="SECRET_CANARY attached third party text")
        add("Ann Lee <ann@corp.com>", "z@else.com", "undated", "This message has no date header but plenty of words to survive cleaning.", date=None)
        box.close()

    def tearDown(self):
        self.tmp.cleanup()

    def run_it(self, *extra):
        return run(str(self.root / "m.mbox"), "--home", str(self.root / "home"), "--json", *extra)

    def test_identity_is_exact_not_substring(self):
        code, out, err = self.run_it("--me", "ann")
        recs = [json.loads(l) for l in (self.root / "home" / "corpus.jsonl").read_text().splitlines()]
        self.assertTrue(all("joann" not in r["source"] for r in recs))
        self.assertEqual(json.loads(out)["dropped"].get("not_me"), 1)  # Joann was rejected
        code, out, err = run(str(self.root / "m.mbox"), "--home", str(self.root / "home2"), "--me", "", "--json")
        self.assertNotEqual(code, 0)

    def test_attached_message_is_not_the_body(self):
        self.run_it("--me", "ann@corp.com")
        text = (self.root / "home" / "corpus.jsonl").read_text()
        self.assertNotIn("SECRET_CANARY", text)
        self.assertIn("Outer body from Ann", text)

    def test_undated_dropped_with_until(self):
        code, out, err = self.run_it("--me", "ann@corp.com", "--until", "2026-12-31")
        self.assertEqual(json.loads(out)["dropped"].get("unknown_date"), 1)
        code, out, err = run(str(self.root / "m.mbox"), "--home", str(self.root / "home3"), "--me", "ann@corp.com",
                             "--until", "2026-12-31", "--include-undated", "--json")
        self.assertNotIn("unknown_date", json.loads(out)["dropped"])

    def test_common_word_names_not_globally_redacted(self):
        self.run_it("--me", "ann@corp.com")
        recs = [json.loads(l) for l in (self.root / "home" / "corpus.jsonl").read_text().splitlines()]
        r = next(r for r in recs if "deck" in r["text"])
        self.assertIn("I will send the deck", r["text"])  # 'will' stays a verb
        self.assertTrue(all(len(x["id"].split("-")[1]) >= 12 for x in recs))
        self.assertEqual(len({x["id"] for x in recs}), len(recs))


if __name__ == "__main__":
    unittest.main(verbosity=2)
