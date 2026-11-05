"""Shared helpers: read audio (read-only on the source), process, write OP-1 AIFF patches.

Source files are only ever opened for reading; all output goes to new files.
"""
import json, re, struct
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

SR = 44100
DRUM_MAX_FRAMES = 529200          # 12.0 s (original OP-1 drum sampler)
DRUM_UNIT = 4058                  # OP-1 drum start/end = frame * 4058
SYNTH_MAX_FRAMES = 264600         # 6.0 s (original OP-1 synth sampler)
SYNTH_KNOB_FULL = 32767


# ---------------------------------------------------------------- audio io
def load_mono(path):
    """Read a file (read-only) -> float32 mono at 44.1 kHz."""
    data, sr = sf.read(path, dtype='float32', always_2d=True)
    x = data.mean(axis=1)
    if sr != SR:
        from math import gcd
        g = gcd(SR, sr)
        x = resample_poly(x, SR // g, sr // g).astype(np.float32)
    return np.nan_to_num(x)


def trim(x, max_len, thresh_db=-50.0, fade_ms=8.0):
    """Remove leading silence, cut trailing silence, cap length, fade the tail."""
    if len(x) == 0:
        return x
    peak = np.max(np.abs(x)) or 1.0
    thr = peak * 10 ** (thresh_db / 20)
    idx = np.nonzero(np.abs(x) > thr)[0]
    if len(idx) == 0:
        return x[:0]
    start = max(0, idx[0] - 32)           # keep a few samples of pre-attack
    end = idx[-1] + 1
    x = x[start:end][:max_len].copy()
    n = min(len(x), int(SR * fade_ms / 1000))
    if n > 1:
        x[-n:] *= np.linspace(1.0, 0.0, n, dtype=np.float32) ** 2
    # tiny fade-in to avoid clicks
    m = min(len(x), 16)
    x[:m] *= np.linspace(0.0, 1.0, m, dtype=np.float32)
    return x


def normalize(x, peak_db=-1.0):
    p = np.max(np.abs(x)) if len(x) else 0
    if p <= 0:
        return x
    return x * (10 ** (peak_db / 20) / p)


def natural_len(x, thresh_db=-50.0):
    if len(x) == 0:
        return 0
    peak = np.max(np.abs(x)) or 1.0
    idx = np.nonzero(np.abs(x) > peak * 10 ** (thresh_db / 20))[0]
    return 0 if len(idx) == 0 else idx[-1] - idx[0] + 1


def features(x):
    """Rough timbre features on the first 300 ms: spectral centroid, low ratio."""
    seg = x[: int(SR * 0.3)]
    if len(seg) < 256:
        seg = np.pad(seg, (0, 256 - len(seg)))
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    freqs = np.fft.rfftfreq(len(seg), 1 / SR)
    tot = spec.sum() or 1.0
    return dict(centroid=float((spec * freqs).sum() / tot),
                low=float(spec[freqs < 150].sum() / tot))


# ---------------------------------------------------------------- pitch
NOTE_IDX = {'C': 0, 'C#': 1, 'DB': 1, 'D': 2, 'D#': 3, 'EB': 3, 'E': 4, 'F': 5, 'F#': 6,
            'GB': 6, 'G': 7, 'G#': 8, 'AB': 8, 'A': 9, 'A#': 10, 'BB': 10, 'B': 11}


def detect_pitch(x, fmin=30.0, fmax=1500.0):
    """YIN-style f0 estimate over the sustain part of the sound. Returns Hz or None."""
    a = int(SR * 0.05)
    seg = x[a: a + 8192]
    if len(seg) < 4096:
        seg = x[:8192]
    if len(seg) < 2048 or np.max(np.abs(seg)) < 1e-4:
        return None
    seg = seg - seg.mean()
    W = len(seg) // 2
    tmax = min(int(SR / fmin), W)
    tmin = int(SR / fmax)
    d = np.zeros(tmax)
    for t in range(1, tmax):
        diff = seg[:W] - seg[t:t + W]
        d[t] = np.dot(diff, diff)
    cmnd = np.ones(tmax)
    cs = np.cumsum(d[1:])
    cmnd[1:] = d[1:] * np.arange(1, tmax) / np.where(cs == 0, 1, cs)
    cand = np.nonzero(cmnd[tmin:] < 0.15)[0]
    if len(cand):
        t = cand[0] + tmin
        while t + 1 < tmax and cmnd[t + 1] < cmnd[t]:
            t += 1
    else:
        t = int(np.argmin(cmnd[tmin:]) + tmin)
        if cmnd[t] > 0.4:
            return None
    if 1 <= t < tmax - 1:   # parabolic interpolation
        a_, b_, c_ = cmnd[t - 1], cmnd[t], cmnd[t + 1]
        den = a_ - 2 * b_ + c_
        t = t + (0.5 * (a_ - c_) / den if den else 0)
    return SR / t


def note_from_name(name):
    """Find a note name like 'C', 'Ab', 'F#', 'Dmaj', 'Amin11' in a filename."""
    stem = re.sub(r'\.(wav|aiff?)$', '', name, flags=re.I)
    toks = re.findall(r'(?:(?<=[\s_\-(])|^)([A-G](?:#|b)?)(?=(?:maj|min|m\d|m\b|dim|dom|half|\d|\s|_|\)|$|-))', stem)
    if not toks:
        return None
    t = toks[-1]
    return NOTE_IDX.get(t[0] + t[1:].upper())


def base_freq_for(x, filename):
    f0 = detect_pitch(x)
    pc = note_from_name(filename)
    if pc is not None:
        ref = f0 or 130.81
        # pick the octave of that pitch class closest to the detected f0
        midi_ref = 69 + 12 * np.log2(ref / 440.0)
        best = min((m for m in range(24, 109) if m % 12 == pc), key=lambda m: abs(m - midi_ref))
        return 440.0 * 2 ** ((best - 69) / 12), 'filename'
    if f0:
        # snap to nearest semitone (OP-1 then plays in tune with other engines)
        midi = round(69 + 12 * np.log2(f0 / 440.0))
        return 440.0 * 2 ** ((midi - 69) / 12), 'detected'
    return 440.0, 'default'


# ---------------------------------------------------------------- aiff writer
def _ieee_ext(v):
    """80-bit IEEE extended for AIFF sample rate."""
    import math
    if v == 0:
        return b'\x00' * 10
    m, e = math.frexp(v)
    e += 16382
    m = int(m * (1 << 64))
    return struct.pack('>HQ', e, m)


def write_op1_aif(path, x, meta):
    """Write AIFC (sowt, 16-bit mono 44.1k) with the OP-1 'APPL op-1' JSON chunk."""
    pcm = np.clip(np.round(x * 32767), -32768, 32767).astype('<i2').tobytes()
    nframes = len(x)
    comp_name = b'Signed integer (little-endian) linear PCM'
    pstr = bytes([len(comp_name)]) + comp_name
    if len(pstr) % 2:
        pstr += b'\x00'
    comm = struct.pack('>hIh', 1, nframes, 16) + _ieee_ext(SR) + b'sowt' + pstr
    js = b'op-1' + json.dumps(meta, separators=(',', ':')).encode() + b'\n'
    if len(js) % 2:
        js += b' '
    ssnd = struct.pack('>II', 0, 0) + pcm

    def chunk(cid, body):
        return cid + struct.pack('>I', len(body)) + body + (b'\x00' if len(body) % 2 else b'')

    body = b'AIFC' + chunk(b'FVER', struct.pack('>I', 0xA2805140)) + chunk(b'COMM', comm) \
        + chunk(b'APPL', js) + chunk(b'SSND', ssnd)
    with open(path, 'wb') as f:
        f.write(b'FORM' + struct.pack('>I', len(body)) + body)


def drum_meta(name, segments):
    """segments: list of 24 (start_frame, end_frame) tuples."""
    start = [min(s * DRUM_UNIT, 2147483646) for s, e in segments]
    end = [min(max(e * DRUM_UNIT - DRUM_UNIT, s * DRUM_UNIT), 2147483646) for s, e in segments]
    return {
        "drum_version": 1, "type": "drum", "name": name, "octave": 0,
        "pitch": [0] * 24, "start": start, "end": end,
        "playmode": [8192] * 24, "reverse": [8192] * 24, "volume": [8192] * 24,
        "dyna_env": [0, 8192, 0, 8192, 0, 0, 0, 0],
        "fx_active": False, "fx_type": "delay", "fx_params": [8000] * 8,
        "lfo_active": False, "lfo_type": "tremolo", "lfo_params": [16000, 16000, 16000, 16000, 0, 0, 0, 0],
    }


def sampler_meta(name, nframes, base_freq, kind='oneshot', octave=0):
    endk = max(1, round(nframes / SYNTH_MAX_FRAMES * SYNTH_KNOB_FULL))
    if kind == 'pad':        # loop the body of the sound while held
        knobs = [0, round(endk * 0.25), round(endk * 0.9), endk, 12000, 0, 0, 8192]
        adsr = [1500, 10746, 32767, 12000, 4000, 64, 4000, 4000]
    elif kind == 'bass':
        knobs = [0, endk, endk, endk, 12000, 0, 0, 8192]
        adsr = [64, 10746, 32767, 3000, 4000, 64, 4000, 4000]
    else:
        knobs = [0, endk, endk, endk, 12000, 0, 0, 8192]
        adsr = [64, 10746, 32767, 6000, 4000, 64, 4000, 4000]
    return {
        "synth_version": 2, "type": "sampler", "name": name, "octave": octave,
        "base_freq": float(base_freq), "adsr": adsr, "knobs": knobs,
        "fx_active": False, "fx_type": "delay", "fx_params": [8000] * 8,
        "lfo_active": False, "lfo_type": "tremolo", "lfo_params": [16000, 0, 0, 16000, 0, 0, 0, 0],
    }
