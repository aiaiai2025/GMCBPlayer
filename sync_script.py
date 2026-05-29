#!/usr/bin/env python3
"""
sync_script.py
Reads a Word script (.docx), finds paragraphs styled 'Song Title' and 'Cue Title'
in script order, matches them against files in the audio/ folder, and writes songs.json.

Word setup:
  - Songs: paragraph style named exactly  'Song Title'
  - Cues:  paragraph style named exactly  'Cue Title'

Usage:
    python3 sync_script.py path/to/script.docx
    python3 sync_script.py path/to/script.docx --audio audio/ --output songs.json
    python3 sync_script.py path/to/script.docx --dry-run   (report only, no file written)

Dependencies:
    pip install python-docx
"""

import os
import re
import json
import sys
import argparse
from pathlib import Path
from difflib import SequenceMatcher

FUZZY_THRESHOLD = 0.82   # 0–1; raise to require closer matches

try:
    from docx import Document
except ImportError:
    print("ERROR: python-docx not installed.  Run: pip3 install python-docx")
    sys.exit(1)

SONG_STYLE = 'song title'
CUE_STYLE  = 'Cue Title'
SHOW_TITLE = 'Unexpected Stories'

# ── Name normalisation ─────────────────────────────────────────────────────────

def normalize_chars(s):
    """Normalize typographic characters that Word autocorrect introduces."""
    # Smart/curly apostrophes → straight apostrophe
    s = s.replace('’', "'").replace('‘', "'")
    # Em dash / en dash → hyphen
    s = s.replace('—', '-').replace('–', '-')
    # Smart double quotes → straight
    s = s.replace('“', '"').replace('”', '"')
    return s

def clean_name(s):
    """Strip prefixes, suffixes and noise so two names can be compared."""
    s = normalize_chars(s)
    s = os.path.splitext(os.path.basename(s))[0]
    s = re.sub(r'^\d+[a-zA-Z]*\s*[-–]\s*', '', s)          # leading number prefix
    s = re.sub(r'\s*[-–]\s*FINAL', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*\(instrumental\)', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*\(vocals?\)', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*\(cue\)', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*[-–]\s*cue$', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*PT[13]\s*[-–]\s*', ' - ', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*VAMP\s*[-–]\s*', ' - ', s, flags=re.IGNORECASE)
    return s.strip().lower()

def is_instr(f): return bool(re.search(r'\(instrumental\)', f, re.IGNORECASE))
def is_vocal(f): return bool(re.search(r'\(vocal', f, re.IGNORECASE))
def is_cue_file(f):
    name = os.path.splitext(f)[0].strip()
    return bool(re.search(r'\(cue\)$', name, re.IGNORECASE)) or \
           bool(re.search(r'[-–]\s*cue$', name, re.IGNORECASE))
def vamp_part(f):
    if re.search(r'PT1', f, re.IGNORECASE):  return 'pt1'
    if re.search(r'VAMP', f, re.IGNORECASE): return 'vamp'
    if re.search(r'PT3', f, re.IGNORECASE):  return 'pt3'
    return None

def audio_path(filename, audio_dir='audio'):
    return audio_dir.rstrip('/') + '/' + filename

# ── Audio folder scan ──────────────────────────────────────────────────────────

def build_audio_library(audio_dir):
    """
    Returns two dicts:
      song_lib  { clean_name: entry }   — stem song entries (instr±vocal±vamp)
      cue_lib   { clean_name: filename } — standalone cue files
    """
    raw = sorted(f for f in os.listdir(audio_dir) if f.lower().endswith('.mp3'))

    # Separate cues from stem songs
    cue_files  = [f for f in raw if is_cue_file(f)]
    song_files = [f for f in raw if not is_cue_file(f)]

    # ── Cue library ────────────────────────────────────────────────────────────
    cue_lib = {}
    for f in cue_files:
        key = clean_name(f)
        cue_lib[key] = f          # last file wins if duplicates (shouldn't happen)

    # ── Song library (group by clean base name, handle vamp) ──────────────────
    # First pass: group files by their numeric track prefix
    by_prefix = {}
    for f in song_files:
        m = re.match(r'^(\d+[a-zA-Z]*)', f)
        prefix = m.group(1) if m else '__noprefix__'
        by_prefix.setdefault(prefix, []).append(f)

    # For files with no prefix, group by clean name instead
    no_prefix = by_prefix.pop('__noprefix__', [])
    by_clean = {}
    for f in no_prefix:
        key = clean_name(f)
        by_clean.setdefault(key, []).append(f)

    song_lib = {}

    def process_group(files):
        parts = {k: {'instr': None, 'vocal': None}
                 for k in ('main', 'pt1', 'vamp', 'pt3')}
        for f in files:
            vp = vamp_part(f)
            bucket = vp if vp else 'main'
            if is_instr(f):   parts[bucket]['instr'] = f
            elif is_vocal(f): parts[bucket]['vocal'] = f

        has_vamp = any(parts[k]['instr'] for k in ('pt1', 'vamp', 'pt3'))
        instr_main = parts['main']['instr'] or parts['pt1']['instr']
        key = clean_name(instr_main or files[0])

        if has_vamp:
            entry = {
                'instr': audio_path(parts['pt1']['instr']) if parts['pt1']['instr'] else None,
                'vocal': audio_path(parts['pt1']['vocal']) if parts['pt1']['vocal'] else None,
                'vamp': {
                    'instr': audio_path(parts['vamp']['instr']) if parts['vamp']['instr'] else None,
                    'vocal': audio_path(parts['vamp']['vocal']) if parts['vamp']['vocal'] else None,
                },
                'postVamp': {
                    'instr': audio_path(parts['pt3']['instr']) if parts['pt3']['instr'] else None,
                    'vocal': audio_path(parts['pt3']['vocal']) if parts['pt3']['vocal'] else None,
                }
            }
        else:
            entry = {
                'instr': audio_path(parts['main']['instr']) if parts['main']['instr'] else None,
                'vocal': audio_path(parts['main']['vocal']) if parts['main']['vocal'] else None,
            }
        return key, entry

    for prefix, files in sorted(by_prefix.items()):
        key, entry = process_group(files)
        song_lib[key] = entry

    for key_group, files in by_clean.items():
        key, entry = process_group(files)
        song_lib[key] = entry

    return song_lib, cue_lib

# ── Word script parse ──────────────────────────────────────────────────────────

def parse_script(docx_path):
    """
    Returns list of (style_type, display_name) in script order.
    style_type is 'song' or 'cue'.

    Song Title = paragraph style  → whole paragraph is a song entry.
    Cue Title  = character style  → a run within a stage direction is a cue.
                                    Multiple Cue Title runs in one paragraph
                                    each become separate cue entries, in order.
    """
    doc = Document(docx_path)
    entries = []
    for para in doc.paragraphs:
        para_style = para.style.name if para.style else ''

        if para_style == SONG_STYLE:
            text = para.text.strip()
            if text:
                entries.append(('song', text))
            continue   # don't also scan runs inside a song-title paragraph

        # Scan runs for Cue Title character style.
        # Consecutive Cue Title runs are merged into a single cue entry —
        # Word often splits a styled phrase into multiple runs internally.
        cue_buffer = []
        for run in para.runs:
            run_style = run.style.name if run.style else ''
            if run_style == CUE_STYLE:
                cue_buffer.append(run.text)
            else:
                if cue_buffer:
                    text = ''.join(cue_buffer).strip()
                    if text:
                        entries.append(('cue', text))
                    cue_buffer = []
        if cue_buffer:
            text = ''.join(cue_buffer).strip()
            if text:
                entries.append(('cue', text))

    return entries

# ── Match & build ──────────────────────────────────────────────────────────────

def fuzzy_lookup(key, library):
    """
    Fall back to fuzzy match when exact key lookup fails.
    Returns (best_key, score) or (None, 0) if nothing clears the threshold.
    """
    best_key, best_score = None, 0.0
    for k in library:
        score = SequenceMatcher(None, key, k).ratio()
        if score > best_score:
            best_key, best_score = k, score
    if best_score >= FUZZY_THRESHOLD:
        return best_key, best_score
    return None, 0.0

def build_songs_list(script_entries, song_lib, cue_lib, audio_dir):
    """
    Walk script_entries in order.
    Match each against the audio library.
    Handle duplicate names by auto-suffixing titles.
    Returns (songs_list, report_lines).
    """
    songs   = []
    report  = []
    seen_titles = {}   # title → count, to deduplicate display names

    for kind, name in script_entries:
        key = clean_name(name)

        if kind == 'song':
            # Exact match first, fuzzy fallback second
            matched_key = key if key in song_lib else None
            fuzzy_note  = ''
            if matched_key is None:
                fk, score = fuzzy_lookup(key, song_lib)
                if fk:
                    matched_key = fk
                    fuzzy_note  = f'  (fuzzy {score:.0%})'

            if matched_key:
                entry = dict(song_lib[matched_key])
                title = name
                count = seen_titles.get(title, 0) + 1
                seen_titles[title] = count
                if count > 1:
                    title = f'{name} ({count})'
                entry['title'] = title
                songs.append(entry)
                instr = entry.get('instr') or entry.get('vamp', {}).get('instr', '')
                report.append(f'  ✅  [SONG]  {name!r}  →  {instr}{fuzzy_note}')
            else:
                report.append(f'  ❌  [SONG]  {name!r}  →  NO MATCHING FILE FOUND')

        elif kind == 'cue':
            matched_key = key if key in cue_lib else None
            fuzzy_note  = ''
            if matched_key is None:
                fk, score = fuzzy_lookup(key, cue_lib)
                if fk:
                    matched_key = fk
                    fuzzy_note  = f'  (fuzzy {score:.0%})'

            if matched_key:
                filename = cue_lib[matched_key]
                title = name
                count = seen_titles.get(title, 0) + 1
                seen_titles[title] = count
                if count > 1:
                    title = f'{name} ({count})'
                songs.append({
                    'title': title,
                    'type':  'cue',
                    'src':   audio_path(filename, audio_dir),
                })
                report.append(f'  ✅  [CUE]   {name!r}  →  {filename}' +
                               (f'  (occurrence {count})' if count > 1 else '') +
                               fuzzy_note)
            else:
                report.append(f'  ❌  [CUE]   {name!r}  →  NO MATCHING FILE FOUND')

    return songs, report

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Sync Word script to songs.json')
    parser.add_argument('docx',              help='Path to the Word script (.docx)')
    parser.add_argument('--audio',    default='audio',      help='Audio folder (default: audio/)')
    parser.add_argument('--output',   default='songs.json', help='Output path (default: songs.json)')
    parser.add_argument('--dry-run',  action='store_true',  help='Report only — do not write songs.json')
    args = parser.parse_args()

    here       = Path(__file__).parent
    docx_path  = Path(args.docx) if Path(args.docx).is_absolute() else here / args.docx
    audio_dir  = str(here / args.audio) if not Path(args.audio).is_absolute() else args.audio
    output     = here / args.output

    # Validate inputs
    if not docx_path.exists():
        print(f'ERROR: Script not found: {docx_path}')
        sys.exit(1)
    if not os.path.isdir(audio_dir):
        print(f'ERROR: Audio folder not found: {audio_dir}')
        sys.exit(1)

    print(f'\nScript:  {docx_path.name}')
    print(f'Audio:   {audio_dir}')
    print()

    # Parse
    script_entries = parse_script(docx_path)
    song_lib, cue_lib = build_audio_library(audio_dir)

    print(f'Found in script:  {sum(1 for k,_ in script_entries if k=="song")} songs  '
          f'(paragraph style "{SONG_STYLE}"),  '
          f'{sum(1 for k,_ in script_entries if k=="cue")} cues  '
          f'(character style "{CUE_STYLE}")')
    print(f'Found in audio/:  {len(song_lib)} song entries, {len(cue_lib)} cue files')
    print()

    # Match & report
    songs, report = build_songs_list(script_entries, song_lib, cue_lib, args.audio)
    for line in report:
        print(line)
    print()

    missing = sum(1 for l in report if '❌' in l)
    matched = sum(1 for l in report if '✅' in l)
    print(f'Matched: {matched}   Missing: {missing}')

    if args.dry_run:
        print('\n(dry-run — songs.json not written)')
        return

    if missing > 0:
        print(f'\n⚠️  {missing} unmatched entries. songs.json will be written but missing')
        print('   entries will be skipped. Fix the names and re-run to include them.')

    # Write songs.json
    output_data = {'showTitle': SHOW_TITLE, 'songs': songs}
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2)
    print(f'\nWritten {len(songs)} entries to {output}')


if __name__ == '__main__':
    main()
