"""Index the sample library (read-only): duration + category guessed from folder/file names."""
import sys, os, re, json, soundfile as sf
from collections import Counter
ROOT = sys.argv[1]; OUT = sys.argv[2]
B, E = r'(?<![a-z])', r'(?![a-z])'          # word-ish boundaries (digits/_/space ok)
def w(*alts): return re.compile(B + '(?:' + '|'.join(alts) + ')' + E)
LOOP = w(r'loops?', r'breaks?', r'fills?', r'rolls?', r'bpm', r'\d{2,3} ?bpm', r'tops?', r'phrases?', r'drum ?loop', r'groove')
DRUM_CATS = [
 ('808', w(r'808s?', r'subs?', r'sub ?bass', r'~ 808 ~')),
 ('kick', w(r'kicks?', r'kik', r'kix', r'kickz', r'bd', r'bass ?drum')),
 ('rim', w(r'rims?', r'rimshot', r'cross ?stick', r'side ?stick')),
 ('clap', w(r'claps?', r'snaps?', r'clp')),
 ('snare', w(r'snares?', r'snr', r'snurs', r'snare_clap', r'snareclap')),
 ('ohat', w(r'open ?hats?', r'open', r'o ?hat', r'oh', r'ohh')),
 ('hat', w(r'hats?', r'hh', r'hi-?hats?', r'hihats?', r'shakers?', r'shaken', r'tamb\w*', r'hihat_shaker')),
 ('cymbal', w(r'crash', r'rides?', r'cymbals?', r'cym', r'splash')),
 ('tom', w(r'toms?')),
 ('perc', w(r'percs?', r'percussion', r'percushin', r'percc', r'conga', r'bongo', r'cowbell', r'clave', r'block', r'bells?', r'foley', r'shells?', r'woodblock')),
]
OTHER_CATS = [
 ('vox', w(r'vox', r'vocals?', r'voice', r'chant', r'adlibs?')),
 ('fx', w(r'fx', r'noise', r'risers?', r'sweeps?', r'textures?', r't e x t u r e', r'ambien\w*', r'atmos', r'vinyl', r'impacts?', r'transition', r'fx_hits', r'noise_fx')),
 ('bass', w(r'bass\w*')),
 ('melodic', w(r'chords?', r'keys?', r'piano', r'synths?', r'snyth', r'pads?', r'brass', r'horns?', r'guitar', r'gtr', r'pluck\w*', r'leads?', r'organ', r'rhodes', r'melodic', r'flute', r'strings?', r'one-?shots?', r'oneshot', r'stabs?')),
]
def classify(rel):
    parts = rel.lower().split('/')
    fn, folders = parts[-1], '/'.join(parts[1:-1])     # drop the pack name
    if LOOP.search(fn) or LOOP.search(folders): return 'loop'
    for text in (fn, folders):
        for c, rx in DRUM_CATS:
            if rx.search(text): return c
        for c, rx in OTHER_CATS:
            if rx.search(text): return c
    return 'other'
rows = []
for dp, dn, fn in os.walk(ROOT):
    if '/RMR OP-1' in dp: continue
    for f in fn:
        if not re.search(r'\.(wav|aiff?)$', f, re.I) or f.startswith('._'): continue
        p = os.path.join(dp, f); rel = os.path.relpath(p, ROOT)
        try: info = sf.info(p)
        except Exception: continue
        rows.append(dict(path=rel, pack=rel.split('/')[0], dur=round(info.duration, 3),
                         sr=info.samplerate, ch=info.channels, cat=classify(rel)))
json.dump(rows, open(OUT, 'w'), indent=0)
print(len(rows), Counter(r['cat'] for r in rows))
