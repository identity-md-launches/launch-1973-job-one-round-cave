#!/usr/bin/env python3
"""Build the static cave gallery from local records, with inline CSS only."""
import argparse
import html
import json
from pathlib import Path
import re

BARE = 'https://api.imd.fun/artifacts/09ee8caaf2f2f23c437db97f072627760da64d33dbd2b3409379a24a4a38d26a'


def build(placeholders=False):
    root = Path(__file__).resolve().parent.parent
    dist = root / 'dist'
    groups = [('line-' + str(n), 'Line ' + str(n)) for n in range(1, 5)] + [('gathering', 'Gathering')]
    goals = [{'line': n, 'goal': (root / f'line-{n}/GOAL.md').read_text().strip()} for n in range(1, 5)]
    (dist / 'goals.json').write_text(json.dumps(goals, indent=2) + '\n')
    if placeholders:
        empty = {'name': 'Not painted yet', 'image': BARE,
                 'attributes': [{'trait_type': 'Cave', 'value': 'Lava'}]}
        for folder, _ in groups:
            target = dist / folder
            target.mkdir(exist_ok=True)
            for n in range(2, 22):
                path = target / f'{n:02}.json'
                if not path.exists():
                    path.write_text(json.dumps(empty, indent=2) + '\n')
    esc = html.escape
    parts = ['''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pepeolithic · Lava</title>
<style>
:root{color-scheme:dark;font-family:Georgia,serif;background:#20170f;color:#f2dfbd}
body{max-width:1200px;margin:auto;padding:24px}a{color:#edb572}h1{font-size:3rem;margin-bottom:8px}
p{line-height:1.6;max-width:75ch}nav{display:flex;gap:20px;flex-wrap:wrap;margin:28px 0}
section{margin:48px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:24px}
figure{margin:0;background:#2b2017;padding:14px;border:1px solid #705032;border-radius:6px}
img{width:100%;height:auto;aspect-ratio:1;object-fit:contain}figcaption{line-height:1.5}
h3{margin:12px 0 8px}small{color:#d4bc96}summary{cursor:pointer;margin:24px 0}
.future{display:flex;flex-wrap:wrap;gap:10px;list-style:none;padding:0}.future li{border:1px solid #705032;padding:10px}
footer{border-top:1px solid #705032;padding:24px 0}a:focus-visible{outline:3px solid #fff}
</style><header><small>PEPEOLITHIC / LAVA</small><h1>Four paths, one gathering</h1>
<p>Each worker leaves a useful tool and a mark. Browse the painted walls, newest first within each line. Future records are listed separately.</p></header><nav>''']
    for folder, title in groups:
        parts.append(f'<a href="#{folder}">{title}</a>')
    parts.append('</nav><main>')
    for folder, title in groups:
        records = []
        for path in sorted((dist / folder).glob('*.json'), reverse=True):
            if not re.fullmatch(r'\d{2}\.json', path.name):
                continue
            record = json.loads(path.read_text())
            records.append((path, record))
        parts.append(f'<section id="{folder}"><h2>{title}</h2>')
        if folder.startswith('line-'):
            parts.append('<p>' + esc(goals[int(folder[-1])-1]['goal']) + '</p>')
        parts.append('<div class="grid">')
        future = []
        for path, record in records:
            relative = folder + '/' + path.name
            if record.get('name') == 'Not painted yet':
                future.append(f'<li><a href="{relative}">{path.stem} · Not painted yet</a></li>')
                continue
            image = record['image']
            if not re.fullmatch(r'https://api\.imd\.fun/artifacts/[0-9a-f]{64}', image):
                raise ValueError('invalid artifact URL in ' + str(path))
            attrs = {item['trait_type']: item['value'] for item in record['attributes']}
            thumb = folder + '/' + path.stem + '.jpg' if path.with_suffix('.jpg').exists() else image
            name = esc(record['name'])
            meaning = esc(str(attrs.get('Meaning', '')))
            tool = esc(str(attrs.get('Left behind', '')))
            parts.append(f'<figure><a href="{image}"><img src="{thumb}" width="512" height="512" loading="lazy" alt="{meaning}"></a><figcaption><small>MARK {path.stem}</small><h3>{name}</h3><p>{meaning}</p><p>Left behind: {tool}</p><a href="{relative}">Record</a> · <a href="{image}">Full wall</a></figcaption></figure>')
        parts.append('</div>')
        if future:
            parts.append(f'<details><summary>{len(future)} future marks · newest slot first</summary><ul class="future">' + ''.join(future) + '</ul></details>')
        parts.append('</section>')
    parts.append('</main><footer><a href="goals.json">All four goals (JSON)</a><p>The page needs no JavaScript or external stylesheet. Previews are local; full walls link to content-addressed artifacts.</p></footer></html>')
    result = '\n'.join(parts) + '\n'
    if len(result.encode()) > 100000:
        raise ValueError('gallery exceeds assignment byte cap')
    (dist / 'index.html').write_text(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--placeholders', action='store_true', help='first gathering: fill missing slots 02–21')
    build(parser.parse_args().placeholders)
