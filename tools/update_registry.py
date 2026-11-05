"""Record which source samples went into a built set.

Usage: python update_registry.py <out_dir> <set_id>
Reads <out_dir>/drum_report.json and sampler_report.json and writes, in the project root:
  used_samples.csv  - one row per (sample, patch, key); machine readable, appended per set
  SETS.md           - human-readable inventory, one section per set
Re-running with the same set_id replaces that set's rows (no duplicates).
"""
import sys, os, csv, json, datetime
from collections import Counter

OUT, SET_ID = sys.argv[1:3]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, 'used_samples.csv')
MD = os.path.join(ROOT, 'SETS.md')
FIELDS = ['set', 'date', 'engine', 'folder', 'patch', 'key', 'slot', 'source']
today = datetime.date.today().isoformat()

drums = json.load(open(os.path.join(OUT, 'drum_report.json')))
synth = json.load(open(os.path.join(OUT, 'sampler_report.json')))
new = []
for p in drums:
    for k in p['keys']:
        new.append(dict(set=SET_ID, date=today, engine='drum', folder=p['folder'], patch=p['name'],
                        key=k['key'], slot=k['type'], source=k['src']))
for p in synth:
    new.append(dict(set=SET_ID, date=today, engine='sampler', folder=p['folder'], patch=p['name'],
                    key='', slot=f"{p['kind']} base {p['base_freq']}Hz", source=p['src']))

old = []
if os.path.exists(CSV):
    old = [r for r in csv.DictReader(open(CSV, newline='')) if r['set'] != SET_ID]
rows = old + new
with open(CSV, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)

# ---- human-readable inventory, rebuilt from the CSV
lines = ['# OP-1 sets: sample inventory', '',
         'Every source sample (relative to `~/makemusic/_audiofiles`) used in each built set.',
         'Machine-readable version: `used_samples.csv`. The build scripts read it and prefer unused samples.', '']
sets = list(dict.fromkeys(r['set'] for r in rows))
all_used = Counter(r['source'] for r in rows)
lines += [f'Total: {len(sets)} set(s), {len(all_used)} unique samples used.', '']
for s in sets:
    rs = [r for r in rows if r['set'] == s]
    lines += [f'## {s} ({rs[0]["date"]})', '',
              f'{len(set((r["engine"], r["patch"]) for r in rs))} patches, {len(set(r["source"] for r in rs))} unique samples.', '']
    for patch in dict.fromkeys((r['engine'], r['folder'], r['patch']) for r in rs):
        pr = [r for r in rs if (r['engine'], r['folder'], r['patch']) == patch]
        lines.append(f'### {patch[0]}/{patch[1]}/{patch[2]}')
        for r in pr:
            key = f'key {r["key"]:>2} · ' if r['key'] else ''
            lines.append(f'- {key}{r["slot"]}: `{r["source"]}`')
        lines.append('')
open(MD, 'w').write('\n'.join(lines))
print(f'{len(new)} rows for {SET_ID}; registry now {len(rows)} rows, {len(all_used)} unique samples')
