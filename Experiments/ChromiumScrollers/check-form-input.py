#!/usr/bin/env python3
"""Qualify native focus/key handoff in the pinned, isolated standard-control fixture."""
import argparse
import json
from pathlib import Path
import subprocess
from PIL import Image, ImageChops

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--session', required=True)
parser.add_argument('--cdp', required=True)
parser.add_argument('--controls', type=Path, required=True)
parser.add_argument('--normal-references', type=Path, required=True)
parser.add_argument('--focused-references', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
command = ['agent-browser', '--session', args.session, '--cdp', args.cdp]
controls = {item['id']: item for item in json.loads(args.controls.read_text())}
results = []

def browser(*arguments):
    return subprocess.check_output(command + list(arguments), text=True)

def evaluate(expression):
    return json.loads(browser('eval', expression))

def check(name, condition, **values):
    result = dict(case=name, passed=bool(condition), **values)
    results.append(result)
    (args.output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    assert condition, result

def reset():
    evaluate('window.__nxsReloadPending=true; location.reload(); true')
    browser('wait', '--fn', 'document.readyState === "complete" && !!window.events && !window.__nxsReloadPending')
    evaluate('''(()=>{events=[];window.focusEvents=[];
      for(const type of ['keydown','keypress','keyup'])document.addEventListener(type,
        e=>events.push({type,id:e.target.id,key:e.key,trusted:e.isTrusted,checked:e.target.checked}));
      for(const type of ['focus','blur'])document.addEventListener(type,
        e=>focusEvents.push({type,id:e.target.id}),true);return true;})()''')

def focus(identifier):
    browser('focus', '#' + identifier)

def types(identifier):
    return evaluate('events.filter(e=>e.id===' + json.dumps(identifier) + ').map(e=>e.type)')

def compare(identifier, path, references, suffix='', margin=False):
    item = controls[identifier]
    expected = Image.open(references / (identifier + suffix + '.png')).convert('RGBA')
    canvas = Image.new('RGBA', expected.size, 'white')
    canvas.alpha_composite(expected)
    actual = Image.open(path).convert('RGB')
    x, y, width, height = item['x'], item['y'], item['width'], item['height']
    difference = ImageChops.difference(actual.crop((x,y,x+width,y+height)), canvas.convert('RGB')).getbbox()
    check('pixels-' + identifier + suffix + ('-focus' if references == args.focused_references else ''), difference is None, difference=difference)
    if margin:
        outer = actual.crop((x-3,y-3,x+width+3,y+height+3))
        mask = Image.new('RGB', outer.size, 'white')
        mask.paste(actual.crop((x,y,x+width,y+height)), (3,3))
        check('native-focus-outline-' + identifier, ImageChops.difference(outer, mask).getbbox() is None)

assert evaluate('document.title') == 'Native standard-control transport', 'Use the isolated fixture'
reset()
path = (args.output / 'normal.png').resolve()
browser('screenshot', str(path))
for identifier in controls:compare(identifier, path, args.normal_references)

for identifier, item in controls.items():
    if not item['enabled']:continue
    reset();focus(identifier)
    path = (args.output / (identifier + '-focused.png')).resolve()
    browser('screenshot', str(path))
    compare(identifier, path, args.focused_references, margin=True)

for identifier in ('button','check','radio-a'):
    reset()
    item = controls[identifier]
    browser('mouse','move',str(round(item['x']+item['width']/2)),str(round(item['y']+item['height']/2)))
    browser('mouse','down')
    try:
        path = (args.output / (identifier + '-pressed.png')).resolve()
        browser('screenshot', str(path))
        compare(identifier, path, args.focused_references, '-pressed')
    finally:browser('mouse','up')

for identifier in ('button','input-button','large','check','mixed','radio-a','radio-b'):
    reset();focus(identifier);browser('press','Space')
    expected = ['keydown','click','keyup'] if controls[identifier]['kind']==1 else ['keydown','click','input','change','keyup']
    check('native-key-events-' + identifier, types(identifier) == expected, events=types(identifier))
    check('trusted-' + identifier, evaluate('events.every(e=>e.trusted)'))
    if controls[identifier]['kind'] in (2,3):
        check('native-key-state-' + identifier, evaluate('document.getElementById(' + json.dumps(identifier) + ').checked'))

reset();focus('button');browser('press','Tab')
check('native-next-focus', evaluate('document.activeElement.id') == 'input-button')
browser('press','Shift+Tab')
check('native-previous-focus', evaluate('document.activeElement.id') == 'button')
reset();focus('radio-a');browser('press','Space');focus('radio-b');browser('press','Space')
check('native-radio-group-model', evaluate('!document.getElementById("radio-a").checked && document.getElementById("radio-b").checked'))

reset();focus('check')
evaluate('document.getElementById("check").addEventListener("keydown",e=>e.preventDefault());true')
browser('press','Space')
check('keydown-cancelled', types('check') == ['keydown','keyup'] and not evaluate('document.getElementById("check").checked'))

reset();focus('button')
evaluate('document.getElementById("button").addEventListener("keydown",e=>e.preventDefault());true')
browser('press','Tab')
check('navigation-cancelled', evaluate('document.activeElement.id') == 'button')

reset();focus('check')
evaluate('document.getElementById("check").addEventListener("click",e=>e.preventDefault());true')
browser('press','Space')
check('click-cancelled-model-rollback', types('check') == ['keydown','click','keyup'] and not evaluate('document.getElementById("check").checked'))
path = (args.output / 'cancelled-checkbox.png').resolve();browser('screenshot',str(path))
compare('check',path,args.focused_references)

reset();focus('check')
evaluate('''(()=>{let e=document.getElementById('check');for(const type of ['keydown','keypress','keyup'])
  e.dispatchEvent(new KeyboardEvent(type,{key:' ',code:'Space',bubbles:true,cancelable:true}));return true;})()''')
check('script-keys-no-native-action', not evaluate('document.getElementById("check").checked') and 'click' not in types('check'))

reset();focus('button');browser('press','a')
check('unhandled-key-no-activation', 'click' not in types('button'))
reset();focus('button');browser('press','Enter')
check('native-nondefault-enter', 'click' not in types('button'))

reset();focus('button')
evaluate('document.getElementById("button").addEventListener("keydown",e=>e.target.remove(),{once:true});true')
browser('press','Space')
check('remove-on-keydown', 'click' not in types('button'))

reset();focus('button')
evaluate('''document.getElementById('button').addEventListener('keydown',e=>{
  let node=e.target;node.remove();document.body.append(node);node.focus();},{once:true});true''')
browser('press','Space')
check('reinsert-on-keydown-cancels-old-control', 'click' not in types('button'))

reset()
evaluate('''(()=>{const form=document.createElement('form');form.id='model-form';
  form.innerHTML='<button id="native-submit" type="submit">Send</button>';
  window.submissions=[];form.addEventListener('submit',e=>{e.preventDefault();submissions.push({trusted:e.isTrusted,submitter:e.submitter.id});});
  document.body.append(form);form.firstChild.focus();return true;})()''')
browser('press','Space')
check('native-action-real-form-submit', evaluate('submissions.length===1 && submissions[0].trusted && submissions[0].submitter==="native-submit"'))

reset()
evaluate('''(()=>{const e=document.createElement('input');e.type='checkbox';e.id='before-paint';
  document.body.append(e);e.focus();return true;})()''')
browser('press','Space')
check('new-control-focus-before-paint', evaluate('document.getElementById("before-paint").checked') and types('before-paint') == ['keydown','click','input','change','keyup'])
print(json.dumps(dict(passed=len(results),results=results)))
