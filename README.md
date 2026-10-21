# WCC Launcher

Sets up multi-room events for Wordly Chrome Capture.

Kept separate from the extension folder on purpose — Chrome dislikes extra files
inside an unpacked extension.

---

## One-time setup, once per machine

Chrome no longer lets a script install an extension, so each profile needs it
added by hand **once ever**.

Profiles are generic and permanent — `Room-01`, `Room-02`, and so on. They are
**not** named after any particular event, so the same profiles are reused every
time. Install the extension once per profile and you never touch this again.

In each room window:

1. Go to `chrome://extensions`
2. Turn on **Developer mode**
3. Click **Load unpacked**
4. Choose `~/Documents/Code/wordly-chrome-capture`
5. Pin Wordly Capture to the toolbar (puzzle-piece icon)

Each room card reminds you of this.

> Tip: set up a few more profiles than you need today (run the script with a
> larger CSV once) so future bigger events need no setup at all.

> The proper long-term fix is publishing the extension privately to the Chrome
> Web Store and force-installing it by policy — then it appears in every profile
> automatically, like Google Docs Offline does. That needs IT to push the policy.

---

## Recommended: set up the machine once

Create ten reusable room profiles up front, then install the extension in each.
After this, no event ever needs setup again.

```
cd ~/Documents/Code/WCC-launcher
python3 event-setup.py --seed 10
```

Open each room launcher, do the Load unpacked steps, close it. Done forever.

---

## Before each event

Export your sessions from the Wordly portal, run them through the iframe
generator, save as CSV. Then:

```
cd ~/Documents/Code/WCC-launcher
python3 event-setup.py ~/Downloads/"your file.csv" --ac-url "https://their-ac-link"
```

It reads the portal export as-is — no cleanup needed.

You get `~/Documents/WordlyRooms` containing:

- **00 — START EVENT** — opens every room
- **00 — STOP EVENT** — closes them all
- **01, 02, 03…** — one launcher per room
- **Event files/** — everything else, including **AC-HOST-SHEET.html** to send
  to the Adobe Connect host (room name, session ID, passcode, iFrame URL — nothing else)

---

## Already set up? Just swap in this week's sessions

If the machine already has its profiles and the extension installed, you don't
need to rebuild anything — just load the new room list:

```
python3 event-setup.py ~/Downloads/"this week.csv" --rooms-only
```

That rewrites only the room list inside the extension. No profiles, launchers or
cards are touched. Open each room, pick it from the Room dropdown, go.

Good fit for recurring work — a different event each week on the same machine.

---

## On the day

1. Double-click **START EVENT**
2. In each window: copy the name from the card into Adobe Connect, request entry
3. Once placed, click the Wordly icon, pick the room, **Start Capture**
4. Check the badge goes **green**
5. **END EVENT** when finished

---

## Badge colours

| Badge | Meaning |
|---|---|
| Green | Working |
| Amber | Paused |
| Blue | Connecting |
| **Flashing red** | **Stopped — fix this room** |

---

## Notes

- Needs `python3` (comes with Xcode command line tools).
- Writes the room list into the extension's `config.json`; the old one is saved
  as `config.json.previous` in the event folder, not in the extension.
- Rooms are sorted automatically: main room first, then numerically.
- **Match iFrame links by room name, not row order.** A mismatch is silent.
