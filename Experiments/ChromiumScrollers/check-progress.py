#!/usr/bin/env python3
"""Compare native progress pixels and application model/lifecycle behavior."""
import argparse
import json
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
results = []

def browser(*arguments):
    return subprocess.check_output(command + list(arguments), text=True)

def evaluate(expression):
    return json.loads(browser('eval', expression))

def check(case, condition, **values):
    results.append(dict(case=case, passed=bool(condition), **values))
    (args.output/'results.json').write_text(json.dumps(results, indent=2)+'\n')
    assert condition, results[-1]

def compare(identifier, reference, label):
    rect = evaluate('document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
    path = (args.output/(label+'.png')).resolve()
    browser('screenshot',str(path))
    x,y,w,h = [round(rect[key]) for key in ('x','y','width','height')]
    actual = Image.open(path).convert('RGB').crop((x,y,x+w,y+h))
    expected = Image.open(args.references/(reference+'.png')).convert('RGB')
    difference = ImageChops.difference(actual,expected).getbbox()
    check(label,difference is None,difference=difference)

assert evaluate('document.title') == 'Native progress model transport', 'Use the isolated fixture'
# Test the actual initial frame, before a reload or model update could hide it.
for identifier in ('zero','partial','full','clamped','negative','default-max','invalid-max','invalid-value'):
    compare(identifier,identifier,'initial-'+identifier)

browser('click','#partial')
check('read-only-click-preserved',evaluate('events.length===1 && events[0].type==="click" && events[0].id==="partial" && events[0].trusted'))
evaluate('document.getElementById("partial").value=61;true')
compare('partial','partial-61','value-update')
evaluate('document.getElementById("partial").max=76.25;true')
check('browser-normalized-model',evaluate('document.getElementById("partial").position') == .8)
compare('partial','partial-80','maximum-update')

evaluate('document.getElementById("partial").removeAttribute("value");true')
check('indeterminate-model-retained',evaluate('document.getElementById("partial").position') == -1)
evaluate('let e=document.getElementById("partial");e.max=100;e.value=30;true')
compare('partial','partial','determinate-restored')
evaluate('document.getElementById("partial").style.cssText="width:320px;height:17px";true')
compare('partial','resized','native-resize')
evaluate('''(()=>{let e=document.getElementById('partial'),parent=e.parentNode;
  e.remove();parent.append(e);return true;})()''')
compare('partial','resized','native-reinsert')
evaluate('''(()=>{let previous=document.getElementById('invalid-value'),e=document.createElement('progress');
  e.id='new';e.max=3;e.value=1.5;previous.replaceWith(e);return true;})()''')
compare('new','new','native-new-element')
check('model-updates-no-edit-events',evaluate('events.every(e=>e.type==="click")'))
evaluate('window.__nxsReloadPending=true;location.reload();true')
browser('wait','--fn','document.readyState==="complete" && !!window.events && !window.__nxsReloadPending')
compare('zero','zero','reload-first-control')
compare('partial','partial','reload-value')
print(json.dumps(dict(passed=len(results),results=results)))
