# OP-1 sets maker

Builds drum and synth-sampler patches for an **original Teenage Engineering OP-1** (not the OP-1 Field)
from the user's sample library at `/Users/marci-work/makemusic/_audiofiles/`.

## Hard rules
- **The sample library is read-only.** Never move, rename, convert in place or delete anything in
  `~/makemusic/_audiofiles`. Read from it and write copies only. After a build, check that no file there changed:
  `find ~/makemusic/_audiofiles -newermt "<build start>" -type f ! -name .DS_Store`. It should return nothing.
- Output goes to `output/` in this repo (or a new folder), never into the library.
- After every new set, update the usage registry (see "Tracking used samples").

## Device limits (original OP-1)
- Drum patch: up to 12 s total (529,200 frames at 44.1 kHz), 24 keys.
- Synth-sampler patch: up to 6 s (264,600 frames).
- About 42 user patches per type (drum / synth), factory patches included. Set 1 uses 32 + 32 to leave room.
- On the OP-1 disk, patches go in `drum/<folder>/` and `synth/<folder>/`. Only one folder level is allowed.

## Setup
```
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
```
Run scripts with `./.venv/bin/python -I tools/<script>.py ...`.

## Pipeline
1. `tools/index_library.py <library> tools/library_index.json`: walks the library (skips `RMR OP-1 Pack`,
   which already contains OP-1 patches) and records duration and a guessed category per file
   (kick, snare, clap, rim, hat, ohat, cymbal, tom, perc, 808, vox, fx, bass, melodic, loop, other).
   It guesses from file and folder names; the pack name is ignored, and the matching uses word boundaries.
2. `tools/build_drums.py <library> tools/library_index.json <out>`: the kit list is defined at the bottom of the
   file (`build_kit`, `build_rack`, `build_break`). Each kit draws from a list of path prefixes ("pools"), with
   per-slot overrides in `extra`. Within a category it picks samples spread across spectral centroid (dark to
   bright). Lengths are trimmed or capped per slot type so the kit fits in 12 s. Writes `<out>/drum_report.json`.
3. `tools/build_sampler.py <library> tools/library_index.json <out>`: a hand-picked `PICKS` list. Each pick is
   trimmed to under 6 s and normalised. The root pitch comes from a note in the filename, otherwise from YIN
   detection snapped to a semitone, otherwise 440 Hz. Writes `<out>/sampler_report.json`.
4. `tools/update_registry.py <out> <set_id>`: records the set in `used_samples.csv` and `SETS.md`.
5. Validate the output. Re-parse each .aif and check the FORM size, frame count, 24 start/end values and the
   12 s / 6 s caps (see the inline check used for set 1: AIFC + sowt + APPL chunk).

Shared code lives in `tools/op1lib.py`: audio loading, trim and normalise, pitch, the AIFF writer, and the
patch metadata builders.

## OP-1 file format (verified against the user's RMR OP-1 pack)
- AIFC, `sowt` (16-bit little-endian PCM), mono, 44.1 kHz. Chunks: FVER, COMM, `APPL` holding `op-1` + JSON + `\n`, SSND.
- Drum JSON: `start`/`end` arrays of 24 values in units of `frame * 4058` (max 2147483646).
  `end[i] = next_start - 4058`. playmode, reverse and volume default to 8192.
- Sampler JSON: `type: "sampler"`, `base_freq` (the pitch of the sample), `knobs[0..3]` = start, loop start,
  loop end and end in units of `frames / 264600 * 32767`. One-shots use `[0, end, end, end]`; pads loop
  the middle of the sample.

## Key layout of the full kits (keys 1-24, left to right)
1-4 kick · 5-8 snare · 9-10 clap · 11 rim · 12-14 closed hat · 15-16 open hat · 17-20 perc · 21 cymbal · 22 808 · 23-24 fx/vox.
`10_acoustic_hiphop` uses its own layout (toms and cymbals). For breaks, key 1 is the whole break and keys 2-24 are onset slices.

## Tracking used samples
- `used_samples.csv` has one row per patch key: set, date, engine, folder, patch, key, slot, source
  (the source path is relative to the library).
- `SETS.md` is the same data, readable by people. It is regenerated from the CSV.
- `build_drums.py` loads the CSV and avoids those samples when enough unused ones exist (`IGNORE_REGISTRY=1`
  disables this). `build_sampler.py` does **not**, so check `SETS.md` before choosing new `PICKS`.
- Name sets `setNN_YYYY-MM-DD`. Build each new set into a new output folder (for example `output_set02/`) so earlier sets stay intact.

## History and known caveats
- set01_2026-11-04: 10 main kits (`mc_kits`), 12 more kits (`mc_more`), 8 racks and 2 breaks (`mc_racks`),
  and 32 sampler patches (`mc_keys`, `mc_lead`, `mc_pad`, `mc_bass`).
- No one has listened to the patches, and they haven't been loaded onto a device yet. Ask the user for
  feedback on how they sound.
- Pitch detection can be an octave off (the pitch class is usually right). `ky_bb_guitar` fell back to 440 Hz.
- Name-based categories have some misses, such as hats in perc folders and snares on the rim slot when no rim exists.
- op1.fun: downloading needs a login, and automated fetching was blocked. The user chose to skip it. If it
  comes back, have the user download patches into a folder, then validate them and merge them in.
