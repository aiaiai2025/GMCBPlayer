#!/usr/bin/env python3
"""
generate_songs.py
Scans the current directory for MP3 stem pairs (Instrumental + Vocals)
and writes songs.json for the Unexpected Stories stem player.

Vamp detection: songs with PT1 / VAMP / PT3 suffixes are grouped into a
single song entry with nested vamp/postVamp sections.
"""

import os
import re
import json

SHOW_TITLE = "Unexpected Stories"
OUTPUT_FILE = "songs.json"

# ── helpers ────────────────────────────────────────────────────────────────

def scan_mp3s(directory="."):
    """Return sorted list of .mp3 filenames in directory."""
    files = [f for f in os.listdir(directory) if f.lower().endswith(".mp3")]
    files.sort()
    return files

def is_instrumental(filename):
    return bool(re.search(r'\(instrumental\)', filename, re.IGNORECASE))

def is_vocal(filename):
    return bool(re.search(r'\(vocal', filename, re.IGNORECASE))

def track_number(filename):
    """Extract leading track number, e.g. '07' from '07 - Peddler Song...'"""
    m = re.match(r'^(\d+)', filename)
    return m.group(1) if m else None

def vamp_part(filename):
    """
    Detect vamp sub-part.
    Returns: 'pt1' | 'vamp' | 'pt3' | None
    """
    if re.search(r'PT1', filename, re.IGNORECASE):
        return 'pt1'
    if re.search(r'VAMP', filename, re.IGNORECASE):
        return 'vamp'
    if re.search(r'PT3', filename, re.IGNORECASE):
        return 'pt3'
    return None

def clean_title(filename):
    """
    Derive a human-readable song title from a filename.
    Strips track number prefix, stem type suffix, and file extension.
    e.g. '01 - Our Turn Now - FINAL (Instrumental).mp3' → '01 - Our Turn Now'
    """
    name = os.path.splitext(filename)[0]          # strip .mp3
    name = re.sub(r'\s*-\s*FINAL', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*\(instrumental\)', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*\(vocals?\)', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*-\s*Version\s+(\d+)', r' (Version \1)', name, flags=re.IGNORECASE)
    # strip vamp sub-part labels from title
    name = re.sub(r'\s*PT[13]\s*-\s*', ' - ', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*VAMP\s*-\s*', ' - ', name, flags=re.IGNORECASE)
    name = name.strip().strip('-').strip()
    return name

# ── main ───────────────────────────────────────────────────────────────────

def build_songs(directory="."):
    files = scan_mp3s(directory)

    # Bucket files by track number
    by_track = {}
    for f in files:
        num = track_number(f)
        if num is None:
            continue
        by_track.setdefault(num, []).append(f)

    songs = []

    for num in sorted(by_track.keys()):
        track_files = by_track[num]

        # Separate into vamp sub-parts vs regular
        parts = {'main': {'instr': None, 'vocal': None},
                 'pt1':  {'instr': None, 'vocal': None},
                 'vamp': {'instr': None, 'vocal': None},
                 'pt3':  {'instr': None, 'vocal': None}}

        for f in track_files:
            part = vamp_part(f)
            bucket = part if part else 'main'
            if is_instrumental(f):
                parts[bucket]['instr'] = f
            elif is_vocal(f):
                parts[bucket]['vocal'] = f

        # Build title from the main instrumental (or first file)
        title_src = parts['main']['instr'] or parts['pt1']['instr'] or track_files[0]
        title = clean_title(title_src)

        has_vamp = parts['pt1']['instr'] or parts['vamp']['instr'] or parts['pt3']['instr']

        if has_vamp:
            entry = {
                "title": title,
                "instr": parts['pt1']['instr'],
                "vocal": parts['pt1']['vocal'],
                "vamp": {
                    "instr": parts['vamp']['instr'],
                    "vocal": parts['vamp']['vocal']
                },
                "postVamp": {
                    "instr": parts['pt3']['instr'],
                    "vocal": parts['pt3']['vocal']
                }
            }
        else:
            entry = {
                "title": title,
                "instr": parts['main']['instr'],
                "vocal": parts['main']['vocal']
            }

        songs.append(entry)

    return songs

def main():
    directory = os.path.dirname(os.path.abspath(__file__))
    songs = build_songs(directory)
    output = {"showTitle": SHOW_TITLE, "songs": songs}
    out_path = os.path.join(directory, OUTPUT_FILE)
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(output, fh, indent=2)
    print(f"Written {len(songs)} songs to {out_path}")
    for s in songs:
        print(f"  {s['title']}")

if __name__ == "__main__":
    main()
