#!/usr/bin/env python3
"""Golden-set self-test for voice_check.py (stdlib only). Run: python3 test_voice_check.py"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECK = HERE / "voice_check.py"
STYLO = HERE.parent.parent / "voice-profile" / "scripts" / "stylometry.py"
PICK = HERE.parent.parent / "voice-write" / "scripts" / "pick_exemplars.py"
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
            "have any questions.\n\nBest regards,\nDom Pal")


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


class VoiceCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.rows = write_corpus(self.home)
        r = run(STYLO, "--home", str(self.home), "--write-profile", "--exemplars")
        self.assertEqual(r.returncode, 0, r.stderr)

    def check(self, text, *extra):
        p = self.home / "draft.md"
        p.write_text(text, encoding="utf-8")
        r = run(CHECK, str(p), "--home", str(self.home), "--json", *extra)
        self.assertIn(r.returncode, (0, 1), r.stderr)
        res = json.loads(r.stdout)
        self.assertTrue({"verdict", "register", "flags"} <= set(res))
        return r.returncode, res

    @staticmethod
    def flags(res, check, sev):
        return [f for f in res["flags"] if f["check"] == check and f["severity"] == sev]

    def test_genuine_sample_not_fail(self):
        code, res = self.check(self.rows[0]["text"], "--register", "email-external")
        self.assertIn(res["verdict"], ("PASS", "INCONCLUSIVE", "WARN"))
        self.assertEqual(code, 0)

    def test_generic_assistant_rewrite_fails(self):
        code, res = self.check(AI_DRAFT, "--register", "email-external")
        self.assertEqual((res["verdict"], code), ("FAIL", 1))
        self.assertTrue(self.flags(res, "length", "fail"))
        self.assertTrue(self.flags(res, "signoff", "warn"))  # n=30: never-seen class warns (FAIL needs 60); verdict still FAIL via length
        self.assertGreaterEqual(len(self.flags(res, "ai-default", "warn")), 2)
        self.assertFalse(self.flags(res, "ban", "fail"))

    def test_ban_after_bans_file(self):
        (self.home / "bans.txt").write_text("i hope this email finds you well\n")
        r = run(STYLO, "--home", str(self.home), "--bans", str(self.home / "bans.txt"))
        self.assertEqual(r.returncode, 0, r.stderr)
        _, res = self.check(AI_DRAFT, "--register", "email-external")
        self.assertEqual([f["term"] for f in self.flags(res, "ban", "fail")], ["i hope this email finds you well"])

    def test_caricature_draft(self):
        draft = ("Hi Sarah,\n\nQuick one: the deck is done.\n\nQuick one: the budget line is fixed.\n\n"
                 "Quick one: can you send the numbers by Friday?\n\nThanks,\nDom")
        _, res = self.check(draft, "--register", "email-external")
        self.assertEqual(res["verdict"], "FAIL")
        self.assertTrue(self.flags(res, "structure", "fail"))
        self.assertTrue(self.flags(res, "caricature", "warn"))

    def test_wrong_register_opener(self):
        _, res = self.check("Dear Sir,\n\nCan you send the numbers by Friday? Rough cut is fine.\n\nThanks,\nDom", "--register", "email-external")
        self.assertTrue(self.flags(res, "opener", "warn"))  # n=30 < 60: never-seen class warns; FAIL needs 0 of >= 60

    def test_brief_unbriefed_identifiers(self):
        brief = self.home / "brief.md"
        brief.write_text("Ask Sarah to send the Q3 numbers by Friday; a rough cut is fine.")
        _, res = self.check("Hi Sarah,\n\nCan you loop Marcus in before March 12? Rough cut is fine.\n\nThanks,\nDom",
                            "--register", "email-external", "--brief", str(brief))
        ids = {f["identifier"] for f in self.flags(res, "unbriefed", "warn")}
        self.assertTrue({"Marcus", "March 12"} <= ids, ids)
        self.assertNotIn("Dom", ids)  # the user's own sign-off name is never "unbriefed"

    def test_exemplar_copy(self):
        r = run(PICK, "--home", str(self.home), "--register", "email-external", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        picks = self.home / "picks.json"
        picks.write_text(r.stdout)
        ex = json.loads(r.stdout)["exemplars"][0]
        _, res = self.check(ex["text"].replace("[name]", "Sarah"), "--register", "email-external", "--exemplars", str(picks))
        self.assertIn(ex["id"], [f["sample"] for f in self.flags(res, "exemplar-copy", "warn")])

    def test_unknown_register_falls_back(self):
        _, res = self.check(AI_DRAFT, "--register", "post-public")
        self.assertIsNotNone(res["fallback"])
        self.assertIn(res["verdict"], ("PASS", "INCONCLUSIVE", "WARN", "FAIL"))

    def test_selftest(self):
        r = run(CHECK, "--selftest", "--home", str(self.home))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("selftest over", r.stdout)
        self.assertRegex(r.stdout, r"FAIL\s+0\s+\(0%\)")


if __name__ == "__main__":
    unittest.main()
