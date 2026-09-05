#!/usr/bin/env python3
"""Self-test for stylometry.py (stdlib only). Run: python3 test_stylometry.py"""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "stylometry.py"
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


def write_corpus(home: Path) -> list:
    """30 email-external (hi/hey openers; thanks/best/name-only sign-offs; half replies) + 12 chat-dm one-liners."""
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


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


class StylometryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.rows = write_corpus(self.home)
        r = run("--home", str(self.home), "--write-profile", "--exemplars")
        self.assertEqual(r.returncode, 0, r.stderr)

    def features(self, text):
        p = self.home / "draft.md"
        p.write_text(text, encoding="utf-8")
        r = run("--text", str(p))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_text_email(self):
        f = self.features("Hi Sarah,\n\nCan you send the numbers by Friday? Rough cut is fine.\n\nThanks,\nDom")
        self.assertEqual((f["greeting_class"], f["opener"], f["signoff_class"]), ("hi", "hi {name}", "thanks"))
        self.assertLess(f["body_words"], f["words"])
        self.assertEqual(f["sentences"], 2)  # greeting / sign-off lines are not sentences

    def test_text_chat(self):
        f = self.features("thx! will check after lunch")
        self.assertEqual((f["greeting_class"], f["signoff_class"]), ("none", "none"))
        self.assertGreater(f["body_words"], 0)

    def test_corpus_outputs(self):
        regs = json.loads((self.home / "metrics.json").read_text())["registers"]
        self.assertEqual(set(regs), {"email-external", "chat-dm"})
        self.assertEqual((regs["email-external"]["tier"], regs["chat-dm"]["tier"]), ("solid", "directional"))
        w = regs["email-external"]["bands"]["words"]
        self.assertTrue(w["p10"] <= w["p50"] <= w["p90"], w)
        self.assertTrue(regs["email-external"]["greeting_classes"])
        self.assertTrue(regs["email-external"]["never_candidates"]["terms"])
        p = json.loads((self.home / "profile.json").read_text())
        self.assertTrue({"version", "registers", "all", "bans", "keep"} <= set(p))
        self.assertEqual(p["bans"], [])
        for name in ("metrics.json", "profile.json", "exemplars.json"):
            self.assertEqual(stat.S_IMODE(os.stat(self.home / name).st_mode), 0o600, name)
        ids = {r["id"] for r in self.rows}
        for reg, picks in json.loads((self.home / "exemplars.json").read_text()).items():
            self.assertLessEqual(len(picks), 5, reg)
            self.assertTrue({x["id"] for x in picks} <= ids, reg)

    def test_bans_rerun_snapshots(self):
        (self.home / "bans.txt").write_text("i hope this email finds you well\n")
        r = run("--home", str(self.home), "--bans", str(self.home / "bans.txt"))
        self.assertEqual(r.returncode, 0, r.stderr)
        p = json.loads((self.home / "profile.json").read_text())
        self.assertEqual([(b["term"], b["source"]) for b in p["bans"]], [("i hope this email finds you well", "user-confirmed")])
        self.assertTrue((self.home / "profile.v1.json").is_file())

    def test_symlink_home_refused(self):
        link = self.home / "link"
        os.symlink(self.home, link)
        r = run("--home", str(link), "--write-profile")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("symlink", r.stderr)


if __name__ == "__main__":
    unittest.main()
