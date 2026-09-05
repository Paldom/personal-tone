#!/usr/bin/env python3
"""Regenerates docs/example/ from a SYNTHETIC mailbox (fake people, fake company).

Run from the repo root:  python3 docs/example/make_example.py
It writes the mailbox to a temp dir, runs the real pipeline (voice-corpus → voice-profile →
voice-write → voice-check → voice-calibrate) with --home docs/example/home, and captures the
check output. Nothing here is real correspondence.
"""
import datetime, email.message, email.utils, mailbox, os, random, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
S = ROOT / "skills"
OUT = Path(__file__).resolve().parent
HOME = OUT / "home"
random.seed(11)

EXT = [
    "Hi {n},\n\nQuick one: can you send the Q3 numbers by Friday? I'd rather have a rough cut than wait for the polished deck.\n\nThanks,\nAlex",
    "Hi {n},\n\nThanks for the intro. We're happy to take a look. Send the deck when you can and I'll get back to you early next week.\n\nBest,\nAlex",
    "{n}, sorry for the delay. Yes, that works for me. Tuesday 10am?\n\nAlex",
    "Hi {n},\n\nTwo things: the contract is signed, and we still need the DPA. Can you chase legal? I don't think it should take long.\n\nThanks!\nAlex",
    "Hey {n},\n\nSaw the numbers. Honestly I'd push the launch a week. The onboarding flow isn't there yet. Happy to jump on a call if useful.\n\nBest,\nAlex",
    "Hi {n},\n\nNot this week, sorry. Can we do the 14th? I'll bring the draft.\n\nAlex",
    "Hi {n},\n\nLooks good to me. One thing: the pricing table on page 3 still shows last year's tiers. Fix that and ship it.\n\nThanks,\nAlex",
    "Hey {n},\n\nGot it, thanks. I'll loop in Priya on our side and we'll take it from there.\n\nBest,\nAlex",
    "Hi {n},\n\nShort version: yes to the pilot, no to the exclusivity clause. Details in the redline attached.\n\nAlex",
    "Hi {n},\n\nCan we move Thursday to 3pm? I have the board call at 2. If not, Friday morning works too.\n\nThanks,\nAlex",
    "{n}, one more thing on the invoice: the PO number is missing. Resend and I'll approve it today.\n\nAlex",
    "Hey {n},\n\nNice work on the demo. Two nits: the login step is slow, and the empty state needs copy. Otherwise ship it.\n\nBest,\nAlex",
]
INT = [
    "hey, can you look at the PR when you get a sec? small one",
    "Quick q: did the deploy go out? Staging still shows the old build.",
    "yep on it. will have it by lunch",
    "thx! one more: the invoice export is broken again, I'll open a ticket",
    "Let's do tomorrow 9:30. I need the numbers before the board call.",
    "Nope, blocked on the API key. Pinging the vendor now.",
    "can you add me to the retro invite? calendar didn't sync",
    "done. merged and deployed, watch the error rate for an hour",
]
NAMES = ["Sarah", "Tom", "Priya", "Marcus", "Elena", "Chen", "Lucas", "Nora"]


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    box = mailbox.mbox(str(tmp / "sent.mbox"))
    d = datetime.date(2026, 1, 5)

    def add(body, to, subj, reply):
        m = email.message.EmailMessage()
        m["From"] = "Alex Example <alex@example.com>"
        m["To"] = to
        m["Subject"] = ("Re: " if reply else "") + subj
        m["Date"] = email.utils.format_datetime(datetime.datetime(2026, d.month, d.day, 10, 0))
        if reply:
            m["In-Reply-To"] = "<x@y>"
            body += f"\n\nOn {d.isoformat()} at 9:00, {to} wrote:\n> can we get the numbers\n> thanks"
        m.set_content(body + "\n\n--\nAlex Example | CTO | Example Ltd | +1 555 0100 | https://example.com")
        box.add(m)

    for i in range(len(EXT) * 3):
        n = random.choice(NAMES)
        add(EXT[i % len(EXT)].format(n=n), f"{n} Client <{n.lower()}@client.example>", random.choice(["Q3 numbers", "Intro", "Deck", "Contract"]), i % 2 == 0)
        d += datetime.timedelta(days=3)
    for i in range(len(INT) * 3):
        n = random.choice(NAMES)
        add(INT[i % len(INT)], f"{n} <{n.lower()}@example.com>", random.choice(["PR", "deploy", "invoice"]), i % 3 == 0)
        d += datetime.timedelta(days=2)
    m = email.message.EmailMessage(); m["From"] = "Alex Example <alex@example.com>"; m["To"] = "x@client.example"; m["Subject"] = "draft"
    m.set_content("Certainly! Here's a draft you can use. Would you like me to shorten it?"); box.add(m)
    box.close()

    if HOME.exists():
        shutil.rmtree(HOME)
    env = dict(os.environ, PERSONAL_TONE_HOME=str(HOME))
    run = lambda *a: subprocess.run([sys.executable, *a], env=env, text=True, capture_output=True)  # noqa: E731
    r = run(S / "voice-corpus/scripts/build_corpus.py", str(tmp / "sent.mbox"), "--me", "alex@example.com", "--me", "Alex Example",
            "--internal-domain", "example.com", "--home", str(HOME)); assert r.returncode == 0, r.stderr
    r = run(S / "voice-profile/scripts/stylometry.py", "--home", str(HOME), "--write-profile", "--exemplars"); assert r.returncode == 0, r.stderr
    (OUT / "profile-summary.txt").write_text(r.stdout)
    (tmp / "ai.md").write_text("Hi Sarah,\n\nI hope this email finds you well. I wanted to reach out regarding the Q3 numbers we discussed. It would be greatly appreciated if you could kindly share the finalized figures at your earliest convenience, as this will enable us to align our planning accordingly.\n\nPlease do not hesitate to contact me should you have any questions.\n\nBest regards,\nAlex Example")
    (tmp / "good.md").write_text("Hi Sarah,\n\nCan you send the Q3 numbers by Friday? Rough cut is fine.\n\nThanks,\nAlex")
    (tmp / "brief.md").write_text("ask Sarah for the Q3 numbers by Friday; rough is fine")
    r = run(S / "voice-write/scripts/pick_exemplars.py", "--register", "email-external", "--home", str(HOME)); assert r.returncode == 0, r.stderr
    (OUT / "pick-exemplars.txt").write_text(r.stdout)
    lines = ["# voice-check on two drafts (external email)", ""]
    for name in ("ai.md", "good.md"):
        r = run(S / "voice-check/scripts/voice_check.py", str(tmp / name), "--register", "email-external", "--home", str(HOME), "--brief", str(tmp / "brief.md"))
        lines += [f"## {name}", "```", r.stdout.strip(), f"exit {r.returncode}", "```", ""]
    r = run(S / "voice-check/scripts/voice_check.py", "--selftest", "--loo", "--home", str(HOME))
    lines += ["## --selftest --loo", "```", r.stdout.strip(), "```", ""]
    (OUT / "voice-check.md").write_text("\n".join(lines))
    (tmp / "reason.txt").write_text("way too long and too polite")
    r = run(S / "voice-calibrate/scripts/delta.py", "--draft", str(tmp / "ai.md"), "--sent", str(tmp / "good.md"), "--register", "email-external",
            "--reason-file", str(tmp / "reason.txt"), "--home", str(HOME)); assert r.returncode == 0, r.stderr
    (OUT / "delta.txt").write_text(r.stdout)
    for f in list(HOME.iterdir()) + [OUT / n for n in ("profile-summary.txt", "pick-exemplars.txt", "voice-check.md", "delta.txt")]:
        if f.suffix in (".md", ".txt", ".json", ".jsonl"):  # no local absolute paths in a published example
            f.write_text(f.read_text().replace(str(HOME), "~/.personal-tone").replace(str(ROOT), "<repo>"))
    for f in HOME.iterdir():  # example files must be readable in the repo
        os.chmod(f, 0o644)
    os.chmod(HOME, 0o755)
    (HOME / ".gitignore").unlink(missing_ok=True)
    shutil.rmtree(tmp)
    print("example regenerated under", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
