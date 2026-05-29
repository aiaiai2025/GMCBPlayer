#!/usr/bin/env python3
"""
generate_songs.py
Scans the current directory for MP3 stem pairs (Instrumental + Vocals)
and writes songs.json for the Unexpected Stories stem player.

Vamp detection: songs with PT1 / VAMP / PT3 suffixes are grouped into a
single song entry with nested vamp/postVamp sections.

Cue detection: files ending in (Cue) or -Cue are standalone music cues
(no vocal stems). They appear in songs.json with "type": "cue" and a
single "src" field. Named with alphanumeric prefixes (01a, 01b, etc.)
so they sort between songs in Show W/Cues mode.
"""

import os
import re
import json

SHOW_TITLE  = "Unexpected Stories"
OUTPUT_FILE = "songs.json"
AUDIO_DIR   = "audio"   # subfolder where MP3s live (matches GitHub repo structure)

# ── helpers ────────────────────────────────────────────────────────────────

def scan_mp3s(audio_dir):
    """Return sorted list of .mp3 filenames in the audio subfolder."""
    files = [f for f in os.listdir(audio_dir) if f.lower().endswith(".mp3")]
    files.sort()
    return files

def audio_path(filename):
    """Prefix a filename with the audio subfolder for use in songs.json."""
    return AUDIO_DIR + "/" + filename

def is_instrumental(filename):
    return bool(re.search(r'\(instrumental\)', filename, re.IGNORECASE))

def is_vocal(filename):
    return bool(re.search(r'\(vocal', filename, re.IGNORECASE))

def is_cue(filename):
    """Detect cue files: must end in (Cue) or -Cue before the .mp3 extension."""
    name = os.path.splitext(filename)[0].strip()
    return bool(re.search(r'\(cue\)$', name, re.IGNORECASE)) or \
           bool(re.search(r'-\s*cue$', name, re.IGNORECASE))

def track_number(filename):
    """
    Extract leading track prefix, including optional trailing letters.
    e.g. '07' from '07 - Peddler Song...'
         '01a' from '01a - Playout Music (Cue).mp3'
         '01b' from '01b - Scene Change (Cue).mp3'
    """
    m = re.match(r'^(\d+[a-zA-Z]*)', filename)
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
    name = os.path.splitext(os.path.basename(filename))[0]   # strip dir + .mp3
    name = re.sub(r'\s*-\s*FINAL', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*\(instrumental\)', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*\(vocals?\)', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*\(cue\)', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*-\s*cue$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*-\s*Version\s+(\d+)', r' (Version \1)', name, flags=re.IGNORECASE)
    # strip vamp sub-part labels from title
    name = re.sub(r'\s*PT[13]\s*-\s*', ' - ', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*VAMP\s*-\s*', ' - ', name, flags=re.IGNORECASE)
    name = name.strip().strip('-').strip()
    return name

# ── main ───────────────────────────────────────────────────────────────────

def build_songs(directory="."):
    audio_dir = os.path.join(directory, AUDIO_DIR)
    files = scan_mp3s(audio_dir)

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

        # ── Cue detection ───────────────────────────────────────────────────
        # If any file in this group is a cue, treat the whole group as a cue.
        cue_file = next((f for f in track_files if is_cue(f)), None)
        if cue_file:
            title = clean_title(cue_file)
            entry = {
                "title": title,
                "type": "cue",
                "src": audio_path(cue_file)
            }
            songs.append(entry)
            continue

        # ── Stem song (Instrumental + optional Vocals) ───────────────────────
        parts = {'main': {'instr': None, 'vocal': None},
                 'pt1':  {'instr': None, 'vocal': None},
                 'vamp': {'instr': None, 'vocal': None},
                 'pt3':  {'instr': None, 'vocal': None}}

        for f in track_files:
            part = vamp_part(f)
            bucket = part if part else 'main'
            if is_instrumental(f):
                parts[bucket]['instr'] = audio_path(f)
            elif is_vocal(f):
                parts[bucket]['vocal'] = audio_path(f)

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
    audio_dir = os.path.join(directory, AUDIO_DIR)
    if not os.path.isdir(audio_dir):
        print(f"ERROR: Audio folder not found: {audio_dir}")
        print(f"  Create an '{AUDIO_DIR}/' subfolder and put your MP3s in it.")
        return
    songs = build_songs(directory)
    output = {"showTitle": SHOW_TITLE, "songs": songs}
    out_path = os.path.join(directory, OUTPUT_FILE)
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(output, fh, indent=2)
    cue_count = sum(1 for s in songs if s.get('type') == 'cue')
    song_count = len(songs) - cue_count
    print(f"Written {len(songs)} entries to {out_path}  ({song_count} songs, {cue_count} cues)")
    for s in songs:
        tag = "  [CUE]  " if s.get('type') == 'cue' else "  [SONG] "
        print(f"{tag}{s['title']}")

if __name__ == "__main__":
    main()
