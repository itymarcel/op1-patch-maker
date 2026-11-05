"""Build OP-1 (original) drum patches from the sample library.

Usage: python build_drums.py <library_root> <index.json> <out_dir>
Sources are read-only; patches are written to <out_dir>/drum/<folder>/.
"""
import sys, os, re, json, random
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from op1lib import (SR, DRUM_MAX_FRAMES, load_mono, trim, normalize, features,
                    natural_len, write_op1_aif, drum_meta)

ROOT, INDEX, OUT = sys.argv[1:4]
INDEX_ROWS = json.load(open(INDEX))
BUDGET = DRUM_MAX_FRAMES - SR // 10        # keep ~0.1 s headroom

# standard 24-key layout (chromatic, left to right on the OP-1 keyboard, F..E x2)
LAYOUT = (['kick'] * 4 + ['snare'] * 4 + ['clap'] * 2 + ['rim'] + ['hat'] * 3 +
          ['ohat'] * 2 + ['perc'] * 4 + ['cymbal'] + ['808'] + ['fx'] * 2)
CAP = dict(kick=.5, snare=.5, clap=.5, rim=.3, hat=.25, ohat=.8, perc=.4, cymbal=1.5,
           **{'808': 1.8}, fx=.9, tom=.7, vox=.9)
PEAK = dict(hat=-4, ohat=-4, cymbal=-5, perc=-2, fx=-3, vox=-2)
MAXRAW = dict(kick=3, snare=3, clap=3, rim=2, hat=2.5, ohat=4, perc=3, cymbal=8,
              **{'808': 8}, fx=6, tom=4, vox=4)
# what index category feeds each slot type, in order of preference
SOURCE = dict(kick=['kick'], snare=['snare'], clap=['clap', 'snare'], rim=['rim', 'snare', 'perc'],
              hat=['hat'], ohat=['ohat', 'cymbal', 'hat'], perc=['perc', 'tom'],
              cymbal=['cymbal', 'ohat'], **{'808': ['808', 'kick']}, fx=['fx', 'vox', 'perc'],
              tom=['tom', 'perc'], vox=['vox', 'fx'])

USED = set()
# samples used by earlier sets (see used_samples.csv) are avoided when enough fresh ones exist
_REG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'used_samples.csv')
if os.path.exists(_REG) and os.environ.get('IGNORE_REGISTRY') != '1':
    import csv
    USED |= {r['source'] for r in csv.DictReader(open(_REG, newline=''))}
_cache = {}


def rows_for(pools, cat):
    out = []
    for r in INDEX_ROWS:
        if not any(r['path'].startswith(p) for p in pools):
            continue
        if r['cat'] != cat:
            continue
        if r['dur'] > MAXRAW.get(cat, 4) or r['dur'] < 0.03:
            continue
        out.append(r)
    return out


def analysed(r):
    if r['path'] not in _cache:
        x = load_mono(os.path.join(ROOT, r['path']))
        _cache[r['path']] = (x, features(x))
    return _cache[r['path']]


def pick(pools, slot, n, rng):
    """Pick n samples spread across the timbre range (spectral centroid)."""
    cands = []
    for cat in SOURCE[slot]:
        cands = rows_for(pools, cat)
        if len(cands) >= n or cat == SOURCE[slot][-1]:
            break
    if not cands:
        return []
    fresh = [r for r in cands if r['path'] not in USED]
    if len(fresh) >= n:
        cands = fresh
    if len(cands) > 48:
        cands = rng.sample(cands, 48)
    scored = []
    for r in cands:
        x, f = analysed(r)
        if natural_len(x) < SR * 0.02:
            continue
        scored.append((f['centroid'], r))
    scored.sort(key=lambda t: t[0])
    if not scored:
        return []
    if len(scored) <= n:
        chosen = [r for _, r in scored]
    else:
        idx = np.linspace(0, len(scored) - 1, n).round().astype(int)
        chosen = [scored[i][1] for i in dict.fromkeys(idx)]
    for r in chosen:
        USED.add(r['path'])
    return chosen


def assemble(name, slots, folder):
    """slots: list of 24 (slot_type, row) -> writes the patch; returns report."""
    caps = [CAP.get(t, .5) for t, _ in slots]
    raw = [analysed(r)[0] for _, r in slots]
    nat = [natural_len(x) / SR for x in raw]
    scale = 1.0
    while True:
        lens = [min(n, c * scale) for n, c in zip(nat, caps)]
        if sum(lens) * SR <= BUDGET or scale < 0.2:
            break
        scale *= 0.95
    audio, segs, pos = [], [], 0
    for (t, r), x, L in zip(slots, raw, lens):
        y = normalize(trim(x, int(L * SR)), PEAK.get(t, -1))
        segs.append((pos, pos + len(y)))
        audio.append(y)
        pos += len(y)
    buf = np.concatenate(audio)
    os.makedirs(os.path.join(OUT, 'drum', folder), exist_ok=True)
    write_op1_aif(os.path.join(OUT, 'drum', folder, name + '.aif'), buf, drum_meta(name, segs))
    return dict(name=name, folder=folder, seconds=round(len(buf) / SR, 2),
                keys=[dict(key=i + 1, type=t, src=r['path']) for i, (t, r) in enumerate(slots)])


def build_kit(name, folder, pools, extra=None, layout=LAYOUT, seed=0):
    rng = random.Random(name + str(seed))
    pools_for = lambda t: (extra or {}).get(t, pools)
    need = {}
    for t in layout:
        need[t] = need.get(t, 0) + 1
    chosen = {t: pick(pools_for(t), t, k, rng) for t, k in need.items()}
    # fallback: fill missing slots from a broad pool
    broad = ['artist drumkits', 'A collection of the kounts free sample packs/drums']
    for t, k in need.items():
        if len(chosen[t]) < k:
            chosen[t] += pick(broad, t, k - len(chosen[t]), rng)
    slots = []
    counters = {t: 0 for t in need}
    for t in layout:
        lst = chosen[t]
        r = lst[counters[t] % len(lst)]
        counters[t] += 1
        slots.append((t, r))
    return assemble(name, slots, folder)


def build_rack(name, folder, pools, slot, n=24, seed=0):
    rng = random.Random(name + str(seed))
    chosen = pick(pools, slot, n, rng)
    if len(chosen) < n:
        chosen += pick(['artist drumkits'], slot, n - len(chosen), rng)
    return assemble(name, [(slot, r) for r in chosen[:24]], folder)


def build_break(name, folder, relpath):
    """Key 1 = whole break (up to 11.9 s); keys 2-24 = transient-cut slices."""
    x = normalize(load_mono(os.path.join(ROOT, relpath)), -1)
    full = trim(x, BUDGET, thresh_db=-60, fade_ms=20)
    # onset detection: positive energy flux on 512-sample hops
    hop = 512
    e = np.array([np.sum(full[i:i + hop] ** 2) for i in range(0, len(full) - hop, hop)])
    flux = np.maximum(0, np.diff(np.log(e + 1e-9)))
    peaks = [i for i in range(1, len(flux) - 1) if flux[i] > flux[i - 1] and flux[i] >= flux[i + 1] and flux[i] > 1.0]
    peaks.sort(key=lambda i: -flux[i])
    onsets = []
    for p in peaks:
        f = (p + 1) * hop
        if all(abs(f - o) > SR * 0.08 for o in onsets):
            onsets.append(f)
        if len(onsets) >= 23:
            break
    onsets = sorted(set([0] + onsets))[:23]
    bounds = onsets + [len(full)]
    # slices reference the same audio as the full break (no extra memory needed)
    segs = [(0, len(full))] + [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
    while len(segs) < 24:
        segs.append(segs[len(segs) % max(1, len(segs) - 1) + 1] if len(segs) > 1 else segs[0])
    os.makedirs(os.path.join(OUT, 'drum', folder), exist_ok=True)
    write_op1_aif(os.path.join(OUT, 'drum', folder, name + '.aif'), full, drum_meta(name, segs[:24]))
    return dict(name=name, folder=folder, seconds=round(len(full) / SR, 2),
                keys=[dict(key=1, type='full break', src=relpath)] +
                     [dict(key=i + 2, type='slice', src=relpath) for i in range(len(segs[:24]) - 1)])


# ------------------------------------------------------------------ the set
MB3 = 'Monte Booker Sounds 3'
MBS = 'monte booker sounds'
KF = 'A collection of the kounts free sample packs'
GED1 = 'G.E.D. Soul Sound Library Reel to Reel Drums Vol.1'
GED2 = 'G.E.D. Soul Sound Library Reel to Reel Drums Vol.2'
KNOCK = 'Knock_Audio_-_SWUNG_-_The_Pocket/One_Shots'
ART = 'artist drumkits'
PR = ['Prrrrrrr Samplebank Vol.1', 'Prrrrrrr_Samplebank_Vol.2', 'Prrrrrrr_Samplebank_Vol.3/KICK',
      'Prrrrrrr_Samplebank_Vol.3/SNARE_CLAP', 'Prrrrrrr_Samplebank_Vol.3/HIHAT_SHAKER',
      'Prrrrrrr_Samplebank_Vol.3/PERC', 'Prrrrrrr_Samplebank_Vol.3/808_SUB', 'Prrrrrrr_Samplebank_Vol.3/NOISE_FX']
HH1 = 'DRUM KIT ONE SHOT HIPHOP1'
MD = 'MONTE DISCORD '

report = []
K = 'mc_kits'      # the 10 main kits
M = 'mc_more'      # more full kits
R = 'mc_racks'     # single-category racks + breaks

# 1-10: the curated kits
report.append(build_kit('01_monte_bounce', K, [MB3]))
report.append(build_kit('02_blkswn', K, [MBS + '/blkswn']))
report.append(build_kit('03_sounds_tape', K, [MBS + '/sounds tape', MBS + '/monte favorites']))
report.append(build_kit('04_reel_soul', K, [GED1], extra=dict(clap=[KF + '/drums'], perc=[KF + '/drums', KF + '/percussion loops'], fx=[KF + '/fx', KF + '/texture and ambience'], **{'808': [GED1]})))
report.append(build_kit('05_reel_soul_2', K, [GED2], extra=dict(clap=[KF + '/drums'], perc=['The Kount Kount Drums Vol. 6'], fx=[KF + '/texture and ambience'], **{'808': [GED2]})))
report.append(build_kit('06_kount_dusty', K, ['Kount Drums Vol. 5', 'The Kount Kount Drums Vol. 6'], extra=dict(fx=['Kount Drums Vol. 5/Textures', KF + '/fx'])))
report.append(build_kit('07_swung_pocket', K, [KNOCK]))
report.append(build_kit('08_trap_808', K, [ART]))
report.append(build_kit('09_prrr_club', K, PR))
ACOUSTIC = (['kick'] * 3 + ['snare'] * 3 + ['rim'] + ['clap'] + ['hat'] * 3 + ['ohat'] +
            ['tom'] * 6 + ['cymbal'] * 4 + ['perc'] * 2)
report.append(build_kit('10_acoustic_hiphop', K, [HH1], layout=ACOUSTIC,
                        extra=dict(ohat=[HH1 + '/WAV/HI HAT', GED1], perc=[HH1 + '/WAV/TAMBOURINE', HH1 + '/WAV/SHAKEN'])))

# 11-22: more full kits
report.append(build_kit('11_mai', M, ['mai Drum Kit']))
report.append(build_kit('12_cc_soundpack', M, [MD + '/CC SOUNDPACK VOL1!']))
report.append(build_kit('13_mango_tired', M, [MD + '/! mango juice kit', MD + '/tiredlights_soundkit_vol1']))
report.append(build_kit('14_kount_free', M, [KF + '/drums'], extra=dict(fx=[KF + '/fx', KF + '/vox'], perc=[KF + '/drums', KF + '/percussion loops'])))
report.append(build_kit('15_soulection', M, [MBS + '/soulection white label']))
report.append(build_kit('16_kount_extras', M, ['The Kount and Kiefer Present Big Cop', 'L.A. LOVE KIT', 'Vignette Kit', "Kount's Care Package 5", 'Kount from Splice', 'downloads']))
report.append(build_kit('17_trap_808_2', M, [ART], seed=2))
report.append(build_kit('18_swung_pocket_2', M, [KNOCK], seed=2))
report.append(build_kit('19_monte_bounce_2', M, [MB3], seed=2))
report.append(build_kit('20_battery_home', M, ['Prrrrrrr_Samplebank_Vol.3/battery Samples', 'Prrrrrrr_Samplebank_Vol.3/home battery kit Samples', 'Prrrrrrr_Samplebank_Vol.3/paul house', 'Prrrrrrr_Samplebank_Vol.3/5 YEARS'], extra=dict(clap=PR, perc=PR, fx=PR, ohat=PR, cymbal=PR, **{'808': PR})))
report.append(build_kit('21_reel_mix', M, [GED1, GED2], extra=dict(clap=[MB3], perc=[MB3], fx=[MBS + '/sounds tape'], **{'808': [MB3]}), seed=3))
report.append(build_kit('22_lofi_mix', M, [MBS, MD], seed=4))

# 23-30: racks (24 of one sound type)
report.append(build_rack('23_kicks', R, [ART, KNOCK, MB3, GED1, GED2, 'Kount Drums Vol. 5', 'The Kount Kount Drums Vol. 6'], 'kick'))
report.append(build_rack('24_snares', R, [ART, KNOCK, MB3, GED1, GED2, 'Kount Drums Vol. 5', 'The Kount Kount Drums Vol. 6'], 'snare'))
report.append(build_rack('25_claps_snaps', R, [ART, KNOCK, MB3, 'Prrrrrrr Samplebank Vol.1', MBS], 'clap'))
report.append(build_rack('26_hats', R, [ART, KNOCK, MB3, GED1, GED2, 'Prrrrrrr_Samplebank_Vol.3/HIHAT_SHAKER'], 'hat'))
report.append(build_rack('27_percs', R, [KNOCK + '/Percussion', MB3 + '/perc', 'Prrrrrrr_Samplebank_Vol.3/PERC', 'mai Drum Kit/PERC'], 'perc'))
report.append(build_rack('28_808s', R, [ART + '/808-A', MD + '/808s', 'mai Drum Kit/808', 'Prrrrrrr_Samplebank_Vol.3/808_SUB', MB3], '808'))
report.append(build_rack('29_vox_chops', R, [MB3 + '/vox', MBS, MD + '/CC SOUNDPACK VOL1!/VOX', 'mai Drum Kit/VOX', KF + '/vox', KNOCK + '/Vox'], 'vox'))
report.append(build_rack('30_fx_texture', R, [ART + '/FX-A', MBS + '/sounds tape', KF + '/fx', 'Prrrrrrr Samplebank Vol.1/FX_Noise', 'Prrrrrrr_Samplebank_Vol.3/NOISE_FX', MD + '/! mango juice kit'], 'fx'))

# 31-32: chopped breaks
report.append(build_break('31_brk_dusty_shuffle', R, KF + '/breaks/Dusty Shuffle Break.wav'))
report.append(build_break('32_brk_trulove', R, "Kount's Reel Break Library 2 Teaser/Trulove Break.wav"))

json.dump(report, open(os.path.join(OUT, 'drum_report.json'), 'w'), indent=1)
for r in report:
    print(f"{r['folder']}/{r['name']}: {r['seconds']} s, {len(set(k['src'] for k in r['keys']))} unique samples")
