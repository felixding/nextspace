#!/usr/bin/env python3
"""Qualify only the pinned prototype's standard-control fixture via agent-browser."""
import argparse
import json
from pathlib import Path
import subprocess
from PIL import Image, ImageChops

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--session', required=True)
parser.add_argument('--cdp', required=True)
parser.add_argument('--controls', type=Path, required=True)
parser.add_argument('--references', type=Path, required=True)
parser.add_argument('--pressed-references', type=Path, help='Optional focused native press images')
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
command = ['agent-browser', '--session', args.session, '--cdp', args.cdp]
results = []

def browser(*arguments):
    return subprocess.check_output(command + list(arguments), text=True)

def evaluate(expression):
    return json.loads(browser('eval', expression))

def reset():
    evaluate('window.__nxsReloadPending=true; location.reload(); true')
    browser('wait', '--fn', 'document.readyState === "complete" && !!window.events && !window.__nxsReloadPending')
    evaluate('events = []; true')

def check(name, condition, **data):
    result = dict(case=name, passed=bool(condition), **data)
    results.append(result)
    (args.output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    assert condition, result

def center(identifier):
    rect = evaluate('document.getElementById(' + json.dumps(identifier) + ').getBoundingClientRect().toJSON()')
    return rect['x'] + rect['width'] / 2, rect['y'] + rect['height'] / 2

def move(x, y):
    browser('mouse', 'move', str(round(x)), str(round(y)))

def click(identifier):
    browser('click', '#' + identifier)

def types(identifier):
    return evaluate('events.filter(e=>e.id===' + json.dumps(identifier) + ').map(e=>e.type)')

def compare(identifier, suffix, screenshot):
    item = controls[identifier]
    directory = args.pressed_references if suffix and args.pressed_references else args.references
    reference = Image.open(directory / (identifier + suffix + '.png')).convert('RGBA')
    expected = Image.new('RGBA', reference.size, 'white')
    expected.alpha_composite(reference)
    bounds = item['x'], item['y'], item['x'] + item['width'], item['y'] + item['height']
    actual = Image.open(screenshot).convert('RGB').crop(bounds)
    difference = ImageChops.difference(actual, expected.convert('RGB')).getbbox()
    check('pixels-' + identifier + suffix, difference is None, difference=difference)

assert evaluate('document.title') == 'Native standard-control transport', 'Use the isolated test fixture'
controls = {item['id']: item for item in json.loads(args.controls.read_text())}
reset()
image = (args.output / 'normal.png').resolve()
browser('screenshot', str(image))
for identifier in controls:
    compare(identifier, '', image)

for identifier in ('button', 'check', 'radio-a'):
    reset()
    move(*center(identifier))
    browser('mouse', 'down')
    try:
        image = (args.output / (identifier + '-pressed.png')).resolve()
        browser('screenshot', str(image))
        compare(identifier, '-pressed', image)
    finally:
        browser('mouse', 'up')

for identifier in ('button', 'input-button', 'large'):
    reset()
    click(identifier)
    check('click-' + identifier, types(identifier) == ['mousedown', 'mouseup', 'click'])
    check('trusted-' + identifier, evaluate('events.every(e=>e.trusted)'))

for identifier in ('check', 'mixed'):
    reset()
    click(identifier)
    state = evaluate('({checked:document.getElementById(' + json.dumps(identifier) + ').checked,mixed:document.getElementById(' + json.dumps(identifier) + ').indeterminate})')
    check('activate-' + identifier, state == dict(checked=True, mixed=False), state=state)
    check('events-' + identifier, types(identifier) == ['mousedown', 'mouseup', 'click', 'input', 'change'])
    click(identifier)
    check('toggle-' + identifier, not evaluate('document.getElementById(' + json.dumps(identifier) + ').checked'))

reset()
click('radio-a')
click('radio-b')
check('radio-group', evaluate('!document.getElementById("radio-a").checked && document.getElementById("radio-b").checked'))
evaluate('events=[]; true')
click('radio-b')
check('radio-selected', evaluate('document.getElementById("radio-b").checked') and types('radio-b') == ['mousedown', 'mouseup', 'click'])

reset()
for identifier in ('disabled', 'disabled-check', 'disabled-radio'):
    move(*center(identifier))
    browser('mouse', 'down')
    browser('mouse', 'up')
check('disabled-events', evaluate('events.length') == 0)

reset()
evaluate('document.getElementById("check").addEventListener("click", e=>e.preventDefault()); true')
click('check')
check('prevent-default-rollback', not evaluate('document.getElementById("check").checked') and types('check') == ['mousedown', 'mouseup', 'click'])

reset()
evaluate('document.getElementById("button").addEventListener("pointerdown", e=>e.target.setPointerCapture(e.pointerId)); true')
x, y = center('button')
move(x, y)
browser('mouse', 'down')
move(x + 180, y)
browser('mouse', 'up')
check('capture-cancel', types('button') == ['mousedown', 'mouseup'])

reset()
move(*center('button'))
browser('mouse', 'down')
evaluate('document.getElementById("button").remove(); true')
browser('mouse', 'up')
click('input-button')
check('remove-during-tracking', types('input-button') == ['mousedown', 'mouseup', 'click'])

reset()
move(*center('button'))
browser('mouse', 'down')
reset()
browser('mouse', 'up')
evaluate('events=[]; true')
click('input-button')
check('reload-during-tracking', types('input-button') == ['mousedown', 'mouseup', 'click'])
print(json.dumps(dict(passed=len(results), results=results)))
