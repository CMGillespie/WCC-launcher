#!/usr/bin/env python3
"""
Wordly Capture — Event setup
Version 1.1

Takes the CSV you export from the Wordly portal (after the iframe generator)
and builds everything needed to run a multi-room event:

  • a Chrome profile per room (no sign-in required)
  • the room list written into the extension, so each window just picks its room
  • a launcher per room that opens the Adobe Connect link and a room card
  • START EVENT / END EVENT
  • AC-HOST-SHEET — a trimmed sheet for the Adobe Connect host, with only the
    four things they need: room name, session ID, passcode, iframe URL

IMPORTANT — one-time step per room:
  Current Chrome ignores the --load-extension command line flag, so the
  extension has to be added to each profile once, by hand:
      chrome://extensions  ->  Developer mode ON  ->  Load unpacked
  After that it sticks to that profile forever and future events need nothing.

Usage:
  python3 event-setup.py "SCI Demo Wordly links.csv" --ac-url "https://..."
  python3 event-setup.py rooms.csv --ac-url "https://..." --ext ~/Code/wordly-chrome-capture
"""

import argparse, csv, html, json, os, re, shutil, stat, subprocess, sys
from pathlib import Path

FIELD_ALIASES = {
    "label":    ["title", "roomname", "room", "label", "sessionname"],
    "session":  ["sessionid", "session"],
    "passcode": ["passcode", "accesskey", "key"],
    "iframe":   ["iframeurl", "iframe", "frameurl"],
    "attend":   ["attendurl", "attend"],
    "acname":   ["acname", "adobeconnectname", "displayname"],
}

def norm(s):
    return re.sub(r"[\s_\-]+", "", (s or "").strip().lower())

def build_column_map(headers):
    found = {}
    normalised = {norm(h): h for h in headers if h}
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in normalised:
                found[field] = normalised[alias]
                break
    return found

def sort_key(room):
    """Main room first, then rooms in numeric order (Room 2 before Room 10)."""
    label = room["label"].lower()
    is_main = 0 if "main" in label else 1
    nums = re.findall(r"\d+", label)
    return (is_main, int(nums[-1]) if nums else 0, label)

def slugify(s):
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-") or "room"

def safe_filename(s):
    """Room names often contain '/' which can't go in a filename."""
    cleaned = re.sub(r'[/\\:*?"<>|]+', "-", s).strip()
    return re.sub(r"\s+", " ", cleaned) or "Room"

def write_exec(path: Path, text: str):
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

def sh_quote(p):
    """Wrap a path in single quotes for safe use inside a shell command."""
    return "'" + str(p).replace("'", "'\\''") + "'"

def make_app(app_path: Path, script_path: Path) -> bool:
    """Build a tiny .app that runs the given shell script. Double-clicking an app
    opens no Terminal window at all, so operators don't have to change any
    settings. Falls back to False if osacompile isn't available."""
    if app_path.exists():
        shutil.rmtree(app_path, ignore_errors=True)
    applescript = f'do shell script {chr(34)}{sh_quote(script_path)}{chr(34)}'
    try:
        r = subprocess.run(["osacompile", "-o", str(app_path), "-e", applescript],
                           capture_output=True, text=True)
        return r.returncode == 0
    except FileNotFoundError:
        return False

# ── Parse the portal export ──────────────────────────────────────────────────

def read_rooms(csv_path):
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            sys.exit("ERROR: that CSV appears to be empty.")
        cols = build_column_map(reader.fieldnames)
        missing = [f for f in ("label", "session", "passcode") if f not in cols]
        if missing:
            sys.exit("ERROR: couldn't find these columns in the CSV: " + ", ".join(missing)
                     + "\nColumns present: " + ", ".join(reader.fieldnames))
        rooms = []
        for row in reader:
            label = (row.get(cols["label"]) or "").strip()
            session = (row.get(cols["session"]) or "").strip().upper()
            if not label or not session:
                continue
            rooms.append({
                "label":    label,
                "session":  session,
                "passcode": (row.get(cols["passcode"]) or "").strip(),
                "iframe":   (row.get(cols["iframe"]) or "").strip() if "iframe" in cols else "",
                "acname":   (row.get(cols["acname"]) or "").strip() if "acname" in cols else "",
            })
    if not rooms:
        sys.exit("ERROR: no usable rows found in that CSV.")
    rooms.sort(key=sort_key)
    for r in rooms:
        if not r["acname"]:
            r["acname"] = r["label"]
    return rooms

# ── Outputs ──────────────────────────────────────────────────────────────────

def write_extension_config(ext_dir: Path, rooms, backup_dir: Path):
    """Write the room list into the extension. The backup is kept OUTSIDE the
    extension folder — stray files there upset Chrome's unpacked loader."""
    cfg_path = ext_dir / "config.json"
    cfg = {}
    if cfg_path.exists():
        raw = cfg_path.read_text(encoding="utf-8")
        try:
            cfg = json.loads(raw)
        except Exception:
            cfg = {}
        (backup_dir / "config.json.previous").write_text(raw, encoding="utf-8")
    # No language presets — the Wordly session is the source of truth for languages.
    cfg.pop("presets", None)
    cfg["sessionId"] = ""
    cfg["passcode"]  = ""
    cfg["rooms"] = [{
        "label":       r["label"],
        "sessionId":   r["session"],
        "passcode":    r["passcode"],
        "speakerName": r["acname"],
    } for r in rooms]
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

def write_card(path: Path, r, ext_dir: Path, slot: str):
    iframe_block = ""
    if r["iframe"]:
        iframe_block = f"""
 <div class="box"><div class="tag">iFrame URL for the Adobe Connect pod</div>
 <div class="url">{html.escape(r['iframe'])}</div></div>"""
    path.write_text(f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>{html.escape(r['label'])}</title>
<style>
 body{{font-family:-apple-system,system-ui,sans-serif;margin:0;padding:44px;color:#0F172A}}
 .tag{{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#64748B;margin-bottom:6px}}
 h1{{font-size:38px;margin:0 0 28px;color:#017CFF}}
 .box{{border:1.5px solid #CDD2D7;border-radius:10px;padding:18px 22px;margin-bottom:14px;background:#F8FAFC}}
 .val{{font-size:28px;font-weight:700;user-select:all}}
 .url{{font-size:13px;font-family:ui-monospace,Menlo,monospace;word-break:break-all;user-select:all}}
 .hint{{font-size:14px;color:#475569;line-height:1.7;margin-top:26px}}
 .first{{background:#FFFBEB;border:1.5px solid #F59E0B;color:#92400E;border-radius:10px;
         padding:14px 18px;margin-bottom:20px;font-size:13px;line-height:1.7}}
 code{{background:#fff;padding:1px 5px;border-radius:4px;font-size:12px}}
</style></head><body>
 <div class="tag">{html.escape(slot)} &nbsp;·&nbsp; this window is</div>
 <h1>{html.escape(r['label'])}</h1>

 <div class="first"><b>First time this profile is used, ever:</b> go to
 <code>chrome://extensions</code>, turn on <b>Developer mode</b>, click
 <b>Load unpacked</b>, and choose<br><code>{html.escape(str(ext_dir))}</code><br>
 Then pin Wordly Capture to the toolbar. This profile is reused for every future
 event, so you never have to do this again.</div>

 <div class="box"><div class="tag">Type this name into Adobe Connect</div>
 <div class="val">{html.escape(r['acname'])}</div></div>
 <div class="box"><div class="tag">Wordly session</div>
 <div class="val">{html.escape(r['session'])} &nbsp;·&nbsp; {html.escape(r['passcode'])}</div></div>{iframe_block}
 <div class="hint">
  1. Go to the Adobe Connect tab and enter the name above.<br>
  2. Request entry, then wait to be placed in this room.<br>
  3. Click the Wordly icon, pick <b>{html.escape(r['label'])}</b> from the Room list, press Start Capture.<br>
  4. Check the Wordly icon badge turns <b>green</b>.
 </div>
</body></html>
""", encoding="utf-8")

def write_ac_host_sheet(out_dir: Path, rooms):
    with open(out_dir / "AC-HOST-SHEET.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Room", "Session ID", "Passcode", "iFrame URL"])
        for r in rooms:
            w.writerow([r["label"], r["session"], r["passcode"], r["iframe"]])

    rows = "".join(
        f"<tr><td class='rm'>{html.escape(r['label'])}</td>"
        f"<td class='sid'>{html.escape(r['session'])}</td>"
        f"<td class='sid'>{html.escape(r['passcode'])}</td>"
        f"<td class='url'>{html.escape(r['iframe'])}</td></tr>"
        for r in rooms)
    (out_dir / "AC-HOST-SHEET.html").write_text(f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>Wordly links for Adobe Connect</title><style>
 body{{font-family:-apple-system,system-ui,sans-serif;margin:0;padding:40px;color:#0F172A}}
 h1{{font-size:26px;color:#017CFF;margin:0 0 6px}}
 p{{color:#475569;font-size:14px;margin:0 0 24px;line-height:1.6}}
 table{{border-collapse:collapse;width:100%;font-size:13px}}
 th{{text-align:left;background:#F1F5F9;padding:10px;border-bottom:2px solid #CDD2D7;
     font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#475569}}
 td{{padding:12px 10px;border-bottom:1px solid #E2E8F0;vertical-align:top}}
 .rm{{font-weight:700;white-space:nowrap}}
 .sid{{font-weight:700;font-family:ui-monospace,Menlo,monospace;white-space:nowrap}}
 .url{{font-family:ui-monospace,Menlo,monospace;font-size:11px;word-break:break-all;user-select:all}}
 .warn{{background:#FEF2F2;border:1.5px solid #DC2626;color:#991B1B;border-radius:8px;
        padding:12px 16px;margin:0 0 20px;font-size:13px;line-height:1.6}}
</style></head><body>
<h1>Wordly links for Adobe Connect</h1>
<p class="warn"><b>Match each link by ROOM NAME, not by row order.</b> Putting a link in the
wrong room is silent — the room looks like it is working, but attendees hear another
room's translation. Check the room name on every paste.</p>
<p>One row per room. Put each iFrame URL into the Wordly pod in the matching Adobe Connect room.</p>
<table><tr><th>Room</th><th>Session ID</th><th>Passcode</th><th>iFrame URL</th></tr>{rows}</table>
</body></html>
""", encoding="utf-8")

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Build a Wordly Capture event from a portal CSV export.")
    ap.add_argument("csv", nargs="?", help="CSV exported from the Wordly portal")
    ap.add_argument("--seed", type=int, metavar="N",
                    help="Create N blank room profiles and nothing else. Run this "
                         "once on a machine, install the extension in each, and "
                         "every future event then needs no setup at all.")
    ap.add_argument("--rooms-only", action="store_true",
                    help="Only refresh the room list inside the extension from the "
                         "CSV. Touches nothing else — no profiles, launchers or "
                         "cards. Use this when the machine is already set up and "
                         "you just need this week's sessions loaded.")
    ap.add_argument("--ac-url", default="", help="Adobe Connect link (same for all rooms)")
    ap.add_argument("--ext", default="~/Documents/Code/wordly-chrome-capture",
                    help="Path to the Wordly Capture extension folder")
    ap.add_argument("--out", default="~/Documents/WordlyRooms",
                    help="Where to build the event folder")
    a = ap.parse_args()

    if not a.seed and not a.csv:
        sys.exit("ERROR: give a CSV, or use --seed N to create blank room profiles.")
    if a.csv:
        csv_path = Path(a.csv).expanduser()
        if not csv_path.exists():
            sys.exit(f"ERROR: CSV not found: {csv_path}")

    ext_dir = Path(a.ext).expanduser().resolve()
    if not (ext_dir / "manifest.json").exists():
        sys.exit(f"ERROR: no manifest.json in extension folder: {ext_dir}\nUse --ext to point at the right folder.")

    # --rooms-only: just swap this week's sessions into the extension and stop.
    # Nothing else is touched, so an already-configured machine stays as it is.
    if a.rooms_only:
        if not a.csv:
            sys.exit("ERROR: --rooms-only needs a CSV.")
        rooms = read_rooms(Path(a.csv).expanduser())
        write_extension_config(ext_dir, rooms, Path(a.out).expanduser())
        print(f"Room list updated in {ext_dir / 'config.json'}\n")
        for i, r in enumerate(rooms, start=1):
            print(f"  Room-{i:02d}  ->  {r['label']:<22} {r['session']}")
        print("\nOpen each room and pick it from the Room list in the extension.")
        return

    out_dir = Path(a.out).expanduser()
    # Everything that isn't a launcher lives in one folder, so the top level is
    # just: START, STOP, the rooms, and this.
    support = out_dir / "Event files"
    support.mkdir(parents=True, exist_ok=True)

    # Migrate from the older flat layout so previously-installed extensions in
    # existing profiles are preserved rather than orphaned.
    for name in ("profiles", "cards", "scripts"):
        old, new = out_dir / name, support / name
        if old.exists() and not new.exists():
            shutil.move(str(old), str(new))
    old_backup = out_dir / "config.json.previous"
    if old_backup.exists():
        shutil.move(str(old_backup), str(support / "config.json.previous"))

    profiles_dir = support / "profiles"
    cards_dir    = support / "cards"
    scripts_dir  = support / "scripts"
    for d in (profiles_dir, cards_dir, scripts_dir):
        d.mkdir(parents=True, exist_ok=True)

    # Clear the PREVIOUS event's launchers and cards so they can't be opened by
    # mistake. Profiles are deliberately left alone — they're reused every event
    # and carry the installed extension.
    for old in (list(out_dir.glob("*.command")) + list(scripts_dir.glob("*.command"))
                + list(cards_dir.glob("*.html"))):
        try:
            old.unlink()
        except OSError:
            pass
    for old_app in out_dir.glob("*.app"):
        shutil.rmtree(old_app, ignore_errors=True)

    # --seed: blank placeholder rooms, used to pre-create profiles on a machine
    # so the one-time extension install is done well before any event.
    if a.seed:
        rooms = [{"label": f"Room {i:02d}", "session": "—", "passcode": "",
                  "iframe": "", "acname": f"Room {i:02d}"} for i in range(1, a.seed + 1)]
        print(f"Seeding {a.seed} blank room profiles.\n"
              f"Open each one and install the extension; then future events need no setup.\n")
    else:
        rooms = read_rooms(csv_path)
    print(f"Wordly Capture — event setup\n  Extension: {ext_dir}\n  Output:    {out_dir}\n")

    launch_lines, kill_lines, app_results = [], [], []
    for idx, r in enumerate(rooms, start=1):
        # Profiles are GENERIC and PERMANENT (Room-01, Room-02 ...), deliberately
        # not named after this event's rooms. That way the same profiles are
        # reused every event, so the extension only has to be installed once per
        # profile, ever. Which Wordly session a window serves comes from the Room
        # dropdown instead. Chrome creates the profile itself — pre-writing a
        # Preferences file makes Chrome treat it as tampered with and silently
        # drop extension registrations.
        slot = f"Room-{idx:02d}"
        profile_dir = profiles_dir / slot
        profile_dir.mkdir(parents=True, exist_ok=True)

        card = cards_dir / f"{slot}.html"
        write_card(card, r, ext_dir, slot)

        fname = safe_filename(f"{idx:02d} — {r['label']}")
        launcher = scripts_dir / f"{fname}.command"
        # NOTE: no --load-extension here. Current Chrome ignores it; the extension
        # is added to each profile once by hand and then persists.
        write_exec(launcher, f"""#!/bin/zsh
# Wordly Capture — {r['label']}   ({slot})   generated by event-setup.py
open -na "Google Chrome" --args \\
  --user-data-dir="{profile_dir}" \\
  --no-first-run \\
  --no-default-browser-check \\
  --new-window "file://{card}" {a.ac_url}

# Chrome is detached — nothing else to do here.
# To stop these Terminal windows lingering, set Terminal > Settings > Profiles >
# Shell > "When the shell exits" to "Close if the shell exited cleanly".
""")
        made_app = make_app(out_dir / f"{fname}.app", launcher)
        app_results.append(made_app)

        launch_lines.append(f'"$SUP/scripts/{fname}.command"\nsleep 1')
        kill_lines.append(f'pkill -f "user-data-dir={profile_dir}" 2>/dev/null')
        print(f"  {slot}  ->  {r['label']:<22} {r['session']}  AC name: {r['acname']}")

    write_extension_config(ext_dir, rooms, support)
    write_ac_host_sheet(support, rooms)

    # Numeric prefixes so Finder lists these in running order:
    # START, STOP, then the rooms, then the support folder.
    start_sh = scripts_dir / "START EVENT.command"
    write_exec(start_sh,
               '#!/bin/zsh\nSUP="$(cd "$(dirname "$0")/.." && pwd)"\n'
               + "\n".join(launch_lines) + "\n")
    app_results.append(make_app(out_dir / "00 — START EVENT.app", start_sh))

    end_sh = scripts_dir / "STOP EVENT.command"
    write_exec(end_sh,
               '#!/bin/zsh\n' + "\n".join(kill_lines) + "\n")
    app_results.append(make_app(out_dir / "00 — STOP EVENT.app", end_sh))

    print(f"\n{len(rooms)} rooms ready in {out_dir}")
    print("  00 — START EVENT     — opens every room")
    print("  00 — STOP EVENT      — closes them all")
    print("  01..NN               — one launcher per room")
    print("  Event files/         — cards, profiles, scripts")
    print("  Event files/AC-HOST-SHEET.html — send to the Adobe Connect host")
    if not all(app_results):
        print("\nNOTE: couldn't build .app launchers, so these are .command files.")
        print("      They work, but leave a Terminal window open behind them.")
    print("\nFirst time only: in each room window, add the extension via")
    print("  chrome://extensions  ->  Developer mode  ->  Load unpacked")
    print(f"  and choose {ext_dir}")
    os.system(f'open "{out_dir}" 2>/dev/null')

if __name__ == "__main__":
    main()
