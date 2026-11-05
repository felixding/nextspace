#!/usr/bin/env python3
"""Check every nested scrollbar pixel across enabled/disabled transitions in the isolated fixture."""
import argparse
import json
import math
from pathlib import Path
import subprocess
from PIL import Image, ImageChops

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--session', required=True)
parser.add_argument('--cdp', required=True)
parser.add_argument('--references', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
command = ['agent-browser', '--session', args.session, '--cdp', args.cdp]

def evaluate(expression):
    return json.loads(subprocess.check_output(command + ['eval', expression], text=True))

assert evaluate('document.title') == 'Native Chromium scrollbar prototype', 'Use the isolated test fixture'
cases = [
    ('fitting', "e.innerHTML='Short text'", 'disabled'),
    ('overflowing', "e.innerHTML='<div style=\"width:600px;height:1200px\">Wide text</div>'", 'enabled'),
    ('empty', 'e.replaceChildren()', 'disabled'),
    ('fitting-again', "e.innerHTML='Short text'", 'disabled'),
]
results = []
for name, mutation, state in cases:
    metrics = evaluate("(()=>{scrollTo(0,0);const e=document.querySelector('#nested');" + mutation + ";return new Promise(r=>setTimeout(()=>r({rect:e.getBoundingClientRect().toJSON(),width:e.clientWidth,height:e.clientHeight,x:e.scrollLeft,y:e.scrollTop}),250))})()")
    image_path = (args.output / (name + '.png')).resolve()
    subprocess.run(command + ['screenshot', str(image_path)], capture_output=True, check=True)
    actual = Image.open(image_path).convert('RGB')
    rect = metrics['rect']
    x, y = math.floor(rect['x'] + 2), math.floor(rect['y'] + 2)
    vertical_width = round(rect['width'] - metrics['width'] - 4)
    horizontal_height = round(rect['height'] - metrics['height'] - 4)
    for orientation, bounds in [
        ('horizontal', (x + vertical_width, y + metrics['height'], x + vertical_width + metrics['width'], y + metrics['height'] + horizontal_height)),
        ('vertical', (x, y, x + vertical_width, y + metrics['height'])),
    ]:
        expected = Image.open(args.references / (state + '-' + orientation + '.png')).convert('RGB')
        crop = actual.crop(bounds)
        difference = ImageChops.difference(crop, expected).getbbox()
        results.append(dict(case=name, orientation=orientation, native_difference=difference))
        assert difference is None, results[-1]
    assert metrics['x'] == metrics['y'] == 0
(args.output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(dict(passed=len(results), results=results)))
