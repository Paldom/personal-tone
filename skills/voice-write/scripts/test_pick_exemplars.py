#!/usr/bin/env python3
"""Self-test for pick_exemplars.py (stdlib only). Run: python3 test_pick_exemplars.py"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PICK = HERE / "pick_exemplars.py"
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
INCOMING = ("Hi Dom,\n\nWe reviewed the proposal with the board and they are happy with the scope. Two points: the timeline "
            "for phase two and who owns the contract. Can we talk on Thursday?\n\nBest,\nSarah")  # 35 words


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


class PickExemplarsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.rows = write_corpus(self.home)
        r = run(STYLO, "--home", str(self.home), "--write-profile", "--exemplars")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.annotated = [x["id"] for x in json.loads((self.home / "exemplars.json").read_text())["email-external"]]
        self.incoming = self.home / "incoming.md"
        self.incoming.write_text(INCOMING, encoding="utf-8")

    def pick(self, *args):
        r = run(PICK, "--home", str(self.home), "--register", "email-external", *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_json_k5(self):
        out = json.loads(self.pick("--json", "--k", "5"))
        ids = [e["id"] for e in out["exemplars"]]
        self.assertEqual(len(ids), 5)
        self.assertEqual(len(set(ids)), 5)
        self.assertTrue(set(ids) <= {r["id"] for r in self.rows})
        self.assertIsNotNone(out["budget"]["words_p90"])
        self.assertTrue({"greeting_class", "signoff_class", "paras", "from_id"} <= set(out["skeleton"]))

    def test_reply_to_budget_and_reply_preference(self):
        self.assertEqual(len(re.findall(r"[^\W\d_][\w'’-]*", INCOMING)), 35)
        out = json.loads(self.pick("--json", "--reply-to", str(self.incoming)))
        self.assertEqual(out["budget"]["reply_target_words"], 35)
        self.assertLessEqual(out["budget"]["max_words"], 52)
        # ids listed in exemplars.json fill the slots first and bypass the reply filter, so
        # assert the preference on the stratified picks only (exclude the annotated ids)
        out = json.loads(self.pick("--json", "--reply-to", str(self.incoming), "--exclude", *self.annotated))
        self.assertTrue(out["exemplars"])
        self.assertTrue(all(e["is_reply"] for e in out["exemplars"]), [(e["id"], e["is_reply"]) for e in out["exemplars"]])
    def test_reply_to_respects_k(self):
        out = json.loads(self.pick("--json", "--k", "5", "--reply-to", str(self.incoming)))
        self.assertEqual(len(out["exemplars"]), 5)

    def test_exclude(self):
        out = json.loads(self.pick("--json", "--exclude", self.annotated[0]))
        self.assertNotIn(self.annotated[0], [e["id"] for e in out["exemplars"]])

    def test_markdown_default(self):
        md = self.pick()
        self.assertIn("length budget:", md)
        self.assertTrue(any(ln.startswith("```text") for ln in md.splitlines()), md)
        self.assertTrue(md.rstrip().endswith("```"))

    def test_unknown_register_falls_back(self):
        r = run(PICK, "--home", str(self.home), "--register", "post-public", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertIsNotNone(out["note"])
        self.assertTrue(out["exemplars"])

    def test_deterministic(self):
        args = ("--json", "--k", "4", "--seed", "3", "--reply-to", str(self.incoming))
        self.assertEqual(self.pick(*args), self.pick(*args))


if __name__ == "__main__":
    unittest.main()
