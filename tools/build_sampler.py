"""Build OP-1 (original) synth-sampler patches (max 6 s each) from hand-picked samples.

Usage: python build_sampler.py <library_root> <index.json> <out_dir>
Sources are read-only; patches are written to <out_dir>/synth/<folder>/.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from op1lib import SR, SYNTH_MAX_FRAMES, load_mono, trim, normalize, base_freq_for, write_op1_aif, sampler_meta

ROOT, INDEX, OUT = sys.argv[1:4]
ROWS = json.load(open(INDEX))

# (patch name, folder, kind, octave, unique path suffix)
PICKS = [
    # keys / plucks / mallets
    ('ky_eno_piano',     'mc_keys', 'key', 0, 'one-shots/Eno piano shot 2.wav'),
    ('ky_epiano',        'mc_keys', 'key', 0, 'one-shots/Electric Piano 1.wav'),
    ('ky_al_rhodes',     'mc_keys', 'key', 0, 'oneshot/AL RHODES.wav'),
    ('ky_kolors_rhodes', 'mc_keys', 'key', 0, 'kolors/KOLORS RHODES.wav'),
    ('ky_prophet_pno',   'mc_keys', 'key', 0, 'one-shots/Prophet Piano One Shot.wav'),
    ('ky_vibes',         'mc_keys', 'key', 0, 'one-shots/Vibraphone .wav'),
    ('ky_mallet',        'mc_keys', 'key', 0, 'oneshot/ZM MALLET.wav'),
    ('ky_oak_glass',     'mc_keys', 'key', 0, 'oneshot/OAK GLASS.wav'),
    ('ky_piano_oct',     'mc_keys', 'key', 0, 'tiredlights_note_piano_octave_Ab_70.wav'),
    ('ky_bop_pluck',     'mc_keys', 'key', 0, 'one-shots/Bop Pluck One Shot.wav'),
    ('ky_exotic_pluck',  'mc_keys', 'key', 0, 'one-shots/Exotic Pluck 2.wav'),
    ('ky_vm_pluck',      'mc_keys', 'key', 0, 'oneshot/VM PLUCK.wav'),
    ('ky_sitar',         'mc_keys', 'key', 0, 'one-shots/Sitar One Shot.wav'),
    ('ky_guzheng',       'mc_keys', 'key', 0, 'one-shots/Blown out Guzheng.wav'),
    ('ky_mono_guitar',   'mc_keys', 'key', 0, 'tiredlights_note_mono_guitar_Ab_90.wav'),
    ('ky_bb_guitar',     'mc_keys', 'key', 0, 'oneshot/BB GUITAR 2.wav'),
    # leads / synths / orchestral
    ('ld_op1_saw',       'mc_lead', 'key', 0, 'oneshot/CRTNS OP1 SAW.wav'),
    ('ld_monte_sine',    'mc_lead', 'key', 0, 'oneshot/RGL MONTE SINE.wav'),
    ('ld_crtns_flute',   'mc_lead', 'key', 0, 'oneshot/CRTNS FLUTE.wav'),
    ('ld_dream_flute',   'mc_lead', 'pad', 0, 'SNYTH/DREAM FLUTE.wav'),
    ('ld_juno_synth',    'mc_lead', 'key', 0, 'SNYTH/JUNO SYNTH.wav'),
    ('ld_moog_scream',   'mc_lead', 'key', 0, 'one-shots/Screamin Moog One Shot.wav'),
    ('ld_epic_horn',     'mc_lead', 'key', 0, 'Brass/Horn Epic C.wav'),
    ('ld_pizz',          'mc_lead', 'key', 0, 'pizzicato/pizz C2.wav'),
    ('ld_strings_mid',   'mc_lead', 'pad', 0, 'one-shots/Strings Mid.wav'),
    # pads
    ('pd_saturated',     'mc_pad',  'pad', 0, 'PADS /SATURATED HARMONIC PAD.wav'),
    ('pd_nordic_cold',   'mc_pad',  'pad', 0, 'PADS /NORDIC COLD .wav'),
    ('pd_ocean_cave',    'mc_pad',  'pad', 0, 'PADS /OCEAN CAVE EXPLORATION PAD.wav'),
    # bass
    ('bs_moog',          'mc_bass', 'bass', -1, 'bass/Moog One Shot.wav'),
    ('bs_oberheim',      'mc_bass', 'bass', -1, 'bass/Oberhiem bass.wav'),
    ('bs_p_bass',        'mc_bass', 'bass', -1, 'bass/BJ P BASS.wav'),
    ('bs_808_cave',      'mc_bass', 'bass', -1, '808s/Boogie_-_The_Cave_808.wav'),
]

report = []
for name, folder, kind, octave, suffix in PICKS:
    hits = [r for r in ROWS if r['path'].endswith(suffix)]
    if len(hits) != 1:
        print('!! could not resolve', suffix, len(hits)); continue
    rel = hits[0]['path']
    x = load_mono(os.path.join(ROOT, rel))
    y = normalize(trim(x, SYNTH_MAX_FRAMES - SR // 20, thresh_db=-55, fade_ms=60 if kind != 'bass' else 20), -1)
    bf, how = base_freq_for(y, os.path.basename(rel))
    os.makedirs(os.path.join(OUT, 'synth', folder), exist_ok=True)
    write_op1_aif(os.path.join(OUT, 'synth', folder, name + '.aif'), y,
                  sampler_meta(name, len(y), bf, kind, octave))
    report.append(dict(name=name, folder=folder, kind=kind, src=rel, seconds=round(len(y) / SR, 2),
                       base_freq=round(bf, 2), pitch_from=how))
    print(f'{folder}/{name}: {len(y)/SR:.2f}s base {bf:7.2f} Hz ({how})  <- {rel}')
json.dump(report, open(os.path.join(OUT, 'sampler_report.json'), 'w'), indent=1)
