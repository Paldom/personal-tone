# Export guide — getting your own sent messages out of each platform

**Contents:** [What to feed the script](#what-to-feed-the-script) · [Gmail](#gmail-google-takeout) ·
[Outlook](#outlook) · [Apple Mail](#apple-mail-macos) · [Thunderbird](#thunderbird) ·
[Slack](#slack) · [WhatsApp](#whatsapp) · [Chat-assistant exports](#chat-assistant-exports-claudeai-chatgpt) ·
[Google Chat, Messages, iMessage](#google-chat-google-messages-imessage) · [Verification status](#verification-status)

Steps quoted from the vendors' help pages on 2026-09-05; items marked *observed* are
community knowledge the official page does not state. UI wording drifts — if a menu item is
missing, search the vendor's help for the article title given.

## What to feed the script

`build_corpus.py` reads `.mbox`, `.eml` (files or folders), a Slack export folder, WhatsApp
`.txt`, plain `.txt`/`.md` samples, and `.jsonl` with a `text` field. It does **not** read
`.pst`, `.olm`, `.msg` or `.zip` — unzip archives first, convert mailbox formats via
Thunderbird or Apple Mail (below). Prefer a **Sent-only** export; if you only have an
"all mail" file, `--me` filtering keeps your messages and drops the rest. Avoid: templated
mail, mailing-list posts, anything a colleague or an assistant wrote for you (use `--until`
for a pre-assistant cut-off if in doubt).

## Gmail (Google Takeout)

Official: "How to download your Google data" (support.google.com/accounts/answer/3024190).
1. Open Google Takeout, deselect everything, keep **Mail**.
2. Under Mail, use the "All Mail data included" button to pick labels (*observed*: untick
   "Include all messages in Mail", tick **Sent**). Google documents the button, not the
   label list.
3. Next step → delivery method, one-time export, **Zip**, archive size (2 GB default,
   *observed*; larger sizes reduce splitting). "Your archive expires in about 7 days";
   "each archive [can] be downloaded 5 times."
4. Unzip. *Observed*: with labels selected you get `Takeout/Mail/Sent.mbox`; without, one
   `All mail Including Spam and Trash.mbox`. Google confirms: "each message's labels are
   preserved in a special X-Gmail-Labels header", and "we don't support timeframe
   exports" — use `--since/--until`.
5. Run: `build_corpus.py Takeout/Mail/Sent.mbox --me you@gmail.com --me "Your Name"`.

Single messages: open the email → More → **Download message** gives one `.eml` (needs a
desktop client to open; fine as a hand-picked sample).

## Outlook

Bulk export is `.pst` (classic and new Outlook for Windows: File → Open & Export →
Import/Export → "Export to a file" → "Outlook Data File (.pst)" → pick the account or the
**Sent Items** folder; new Outlook: Settings → Files → Export). Outlook.com has no web-only
export: "you'll need to use a desktop version of Outlook." Legacy Outlook for Mac exports
`.olm` (Tools → Export). Caveat from Microsoft: "By default, Outlook is set to download
email for the past 1 year" — move the sync slider to All first.

`.pst`/`.olm` are not script inputs. Two documented routes:
- **Per message → `.eml`** (Outlook on the web, Outlook.com, new Outlook): open the message
  → More actions → **Download** ("saved as an EML or MSG, usually in the Downloads
  folder"). Outlook for Mac: drag messages to a Finder folder → `.eml` (*observed*).
- **Bulk → Thunderbird → mbox**: Thunderbird ≡ → Tools → Import → Outlook. Mozilla's
  caveat: "It is not sufficient to have a .pst file, but Outlook must be installed on your
  device." Then export the Sent folder with ImportExportTools NG (below). Alternative: add
  the account to Thunderbird or Apple Mail over IMAP and export from there.

## Apple Mail (macOS)

Official: "Import or export mailboxes in Mail on Mac" (support.apple.com/guide/mail/mlhlp1030).
Select the account's **Sent** mailbox in the sidebar → Mailbox → **Export Mailbox…** →
choose a folder. "Mail exports the mailboxes as .mbox packages." *Observed*: the package is a
folder `Sent.mbox/` containing a file literally named `mbox` — point the script at
`Sent.mbox/mbox`. Apple Mail imports "Files in mbox format" only; it cannot open `.pst`.

## Thunderbird

- Per message: select messages → File → Save As → File (or `Ctrl/Cmd+S`) → `.eml`
  (forum-documented; bulk saves append correspondent and date to the file name).
- Bulk: install **ImportExportTools NG**
  (addons.thunderbird.net/addon/ImportExportToolsNG, version 15.0.1 on 2026-09-05, source
  github.com/thunderbird/import-export-tools-ng). Right-click the Sent folder →
  ImportExportTools NG → **Export folder** (mbox; the output is a file without an extension —
  rename it `sent.mbox`) or **Export all messages in the folder** → EML. IMAP folders must be
  synced for offline use first or bodies are missing.

## Slack

Official: "Export your workspace data" (slack.com/help/articles/201658943) and "Guide to
Slack import and export tools" (204897248).
- Who: Workspace Owners/Admins (Free, Pro, Business+), Org Owners (Enterprise), or the
  Export Admin role. Members have **no self-serve export**; ask an owner.
- Free/Pro: Admin → Workspace settings → Security → Import & export data → Export → date
  range → Start Export → email link → "Ready for download" (ZIP). Contains **public
  channels only**; private channels and DMs require an application Slack "will reject …
  unless Workspace Owners show … (a) valid legal process, or (b) consent of members, or
  (c) a requirement or right under applicable laws."
- Business+: owners can apply for the self-serve tool covering "all channels and
  conversations, including private channels and direct messages, as needed and permitted
  by law." Enterprise: custom export by conversation type or **by member**, JSON or TXT.
- Layout ("How to read Slack data exports", 220556107): `users.json`, `channels.json`,
  `groups.json`, `dms.json`, `mpims.json`, then one folder per conversation with
  `YYYY-MM-DD.json` files. Everyone's messages are included: the script keeps only your
  user id (matched from `users.json` via `--me` name or email) and drops join/bot subtypes.
  Point the script at the unzipped folder.

## WhatsApp

Official: "How to export your chat history" (faq.whatsapp.com/1180414079177245).
Android: open the chat → More options → More → **Export chat** → **Without media**.
iPhone: open the chat → tap the contact or group name → **Export chat** → Without Media →
a ZIP (contains `_chat.txt`, *observed*). WhatsApp: "Your chat history can't be re-imported
because it's a text file." *Observed, not on the official page*: exports are truncated to
the most recent messages (commonly reported as 40,000 without media), and line formats are
`[DD/MM/YYYY, HH:MM:SS] Name: text` (iOS) or `DD/MM/YYYY, HH:MM - Name: text` (Android);
the script accepts both and keeps only lines whose sender matches `--me`. A two-sender
file becomes `chat-dm`, more senders `chat-group`.

## Chat-assistant exports (Claude.ai, ChatGPT)

Both offer a data export (Claude: initials → Settings → Privacy → **Export data**, email
link valid 24 h; ChatGPT: profile → Settings → Data controls → **Export** → Confirm, "up to 7
days", link valid 24 h, not for Business/Enterprise). These are **not a voice corpus**: the
`conversations.json` files interleave your prompts with assistant turns, and your prompts
are instruction-register, not the voice you use with people. If you use them at all, keep
only your own turns (`role: user` / `sender: human`) via a `.jsonl` you build yourself,
tag them `register: doc`, and never let an assistant turn in.

## Google Chat, Google Messages, iMessage

- **Google Chat** exports through Takeout (generic flow above); the layout is undocumented
  officially (*observed*: `Takeout/Google Chat/Groups/<DM …|Space …>/messages.json` with
  `creator.email`, `created_date`, `text`). Convert to `.jsonl` (`text`, `date`,
  `register: chat-dm|chat-group`) keeping only `creator.email == you`.
- **Google Messages** (SMS/RCS): no working Takeout export as of 2026-09 (community
  reports of "0 files exported"); unofficial route: SMS Backup & Restore (XML).
- **iMessage**: Apple documents only File → Print → PDF. Unofficial, widely used:
  `imessage-exporter` (github.com/ReagentX/imessage-exporter, `brew install
  imessage-exporter`, `-f txt`), reading `~/Library/Messages/chat.db` (grant the terminal
  Full Disk Access). Your lines are attributed to "Me"; convert to `.jsonl` keeping those.

## Verification status

Verified live on the vendor page (2026-09-05): Takeout flow, Takeout labels header and
no-timeframe note, Gmail single-message download, Outlook `.pst` steps and sync caveat,
Outlook.com desktop-only note, Outlook `.eml` download, Outlook for Mac `.olm`,
Thunderbird import caveat (search snippet), ImportExportTools NG listing, Apple Mail
export/import, Slack roles/steps/plan scope/ZIP layout, WhatsApp steps, Claude and ChatGPT
export steps, Apple Messages print-to-PDF.
Observed only (not on an official page): Takeout label picker wording and per-label file
names, Apple `.mbox` package internals, WhatsApp line formats and message caps, export
file names for Claude/ChatGPT, Google Chat JSON schema, terminal Full Disk Access for
`imessage-exporter`.
