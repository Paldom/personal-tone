#!/usr/bin/env python3
"""Self-test for delta.py (stdlib only). Run: python3 test_delta.py"""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
DELTA = HERE / "delta.py"
STYLO = HERE.parent.parent / "voice-profile" / "scripts" / "stylometry.py"
EMAILS = [
    "All good on my side. Send it over when you are ready.",
    "Not this week, sorry. Ping me again after Easter and we can pick a slot.",
    "Can you send the numbers by Friday? A rough cut is fine, we can polish next week.",
    "Quick one: are we still on for Tuesday? I can move it if the morning is bad for you.",
    "Looks good to me. One thing: the pricing table on page three still shows last year's tiers. Fix that and ship it.",
    "Agreed. Let's cut the second section and keep the summary up front, since that is the only part they will actually read.",
    "I read it twice and I still think the intro is too long. Cut it to one paragraph, keep the chart, and it works.",
    "Yes, go ahead. Keep the invoice under the agreed cap, copy me on the confirmation, and tell them we need the signed copy back by Monday.",
    "We got the approval, so start on Monday. Send me the first cut of the plan when you have it, and flag anything that needs a decision from my side.",
    "Two things before Thursday. First, the travel line still has the old number, so swap in the one from the finance sheet. Second, can you add a short slide on hiring and one on timing?",
]
CHATS = ["thx! will check after lunch", "on it, give me an hour", "yep, sending now", "can you resend the link?",
         "no rush, tomorrow is fine", "ha, same here", "ok pushed the fix, try again now", "lunch at one, the usual place?",
         "running late, start without me", "looks good, ship it", "nope, wrong file, check the other folder", "call in ten? need two minutes"]
AI_DRAFT = ("Hi Sarah,\n\nI hope this email finds you well. I wanted to reach out regarding the Q3 numbers we discussed. "
            "It would be greatly appreciated if you could kindly share the finalized figures at your earliest convenience, "
            "as this will enable us to align our planning accordingly.\n\nPlease do not hesitate to contact me should you "
            "have any questions. The deck is at https://example.com/q3 and my colleague is sarah@example.com.\n\nBest regards,\nDom Pal")
SENT = "Hi Sarah,\n\nCan you send the Q3 numbers by Friday? Rough cut is fine.\n\nThanks,\nDom"


def write_corpus(home: Path) -> list:
    rows = []
    for i in range(30):
        text = f"{'Hey' if i % 5 == 4 else 'Hi'} [name],\n\n{EMAILS[i % 10]}\n\n" + ("Thanks,\nDom", "Best,\nDom", "Dom")[i % 3]
        rows.append({"id": f"e-{i:02d}", "register": "email-external", "channel": "email", "audience": "external",
                     "date": f"2026-01-{i + 1:02d}", "lang": "en", "words": len(text.split()), "subject": ("Re: " if i % 2 else "") + "plan",
                     "is_reply": bool(i % 2), "text": text, "source": "sent.mbox", "to_count": 1, "flags": ["redacted:1"]})
    for i, text in enumerate(CHATS):
        rows.append({"id": f"c-{i:02d}", "register": "chat-dm", "channel": "chat", "audience": "internal", "date": f"2026-02-{i + 1:02d}",
                     "lang": "en", "words": len(text.split()), "subject": None, "is_reply": False, "text": text, "source": "slack.json",
                     "to_count": 1, "flags": []})
    (home / "corpus.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return rows


def run(script, *args):
    return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)


class DeltaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        write_corpus(self.home)
        r = run(STYLO, "--home", str(self.home), "--write-profile", "--exemplars")
        self.assertEqual(r.returncode, 0, r.stderr)
        (self.home / "ai.md").write_text(AI_DRAFT, encoding="utf-8")
        (self.home / "good.md").write_text(SENT, encoding="utf-8")
        self.log = self.home / "calibration.jsonl"

    def delta(self, *args, ok=True):
        r = run(DELTA, "--home", str(self.home), *args)
        if ok:
            self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def log_pair(self, *extra):
        self.delta("--draft", str(self.home / "ai.md"), "--sent", str(self.home / "good.md"), "--register", "email-external",
                   "--reason", "too formal", *extra)
        return [json.loads(ln) for ln in self.log.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def profile(self):
        return json.loads((self.home / "profile.json").read_text(encoding="utf-8"))

    def test_log_entry(self):
        entries = self.log_pair()
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertTrue({"LENGTH_CUT", "LESS_FORMAL", "SIGNOFF"} <= set(e["tags"]), e["tags"])
        self.assertEqual(e["reason"], "too formal")
        self.assertTrue(e["removed"] and e["added"])
        self.assertNotIn("draft_text", e)
        self.assertEqual(stat.S_IMODE(os.stat(self.log).st_mode), 0o600)

    def test_keep_text_redacts(self):
        e = self.log_pair("--keep-text")[-1]
        self.assertIn("[email]", e["draft_text"])
        self.assertIn("[url]", e["draft_text"])
        self.assertNotIn("sarah@example.com", e["draft_text"])
        self.assertNotIn("https://", e["draft_text"])

    def test_report_collapses_duplicates(self):
        self.log_pair()
        self.assertEqual(len(self.log_pair()), 2)
        r = self.delta("--report")
        self.assertIn("calibration report: 1 entries", r.stdout)
        self.assertIn("ban candidates", r.stdout)

    def test_promote_ban_needs_confirm(self):
        self.delta("--promote-ban", "please do not hesitate")
        self.assertEqual(self.profile()["bans"], [])
        self.assertFalse((self.home / "profile.v1.json").exists())
        self.delta("--promote-ban", "please do not hesitate", "--confirm")
        bans = self.profile()["bans"]
        self.assertEqual([(b["term"], b["source"]) for b in bans], [("please do not hesitate", "calibration")])
        self.assertTrue((self.home / "profile.v1.json").is_file())
        r = self.delta("--promote-ban", "Please Do Not Hesitate", "--confirm")
        self.assertIn("already present", r.stdout)
        self.assertEqual(len(self.profile()["bans"]), 1)

    def test_report_without_log(self):
        with tempfile.TemporaryDirectory() as empty:
            r = run(DELTA, "--home", empty, "--report")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ERROR", r.stderr)


if __name__ == "__main__":
    unittest.main()
