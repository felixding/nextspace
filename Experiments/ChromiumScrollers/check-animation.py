#!/usr/bin/env python3
"""Check native animation pixels and lifecycle in the isolated browser fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from PIL import Image

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--session', required=True)
parser.add_argument('--cdp', required=True)
parser.add_argument('--references', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
command = ['agent-browser','--session',args.session,'--cdp',args.cdp]
references = {Image.open(p).convert('RGB').tobytes() for p in args.references.glob('animation-*.png')}
assert len(references)>1
results = []

def browser(*arguments):
    return subprocess.check_output(command+list(arguments),text=True)

def evaluate(expression):
    return json.loads(browser('eval',expression))

def check(case, condition, **values):
    results.append(dict(case=case,passed=bool(condition),**values))
    (args.output/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    assert condition,results[-1]

def capture(identifier,label):
    rect=evaluate('document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
    path=(args.output/(label+'.png')).resolve()
    browser('screenshot',str(path))
    x,y,w,h=[round(rect[k]) for k in ('x','y','width','height')]
    assert (w,h)==(128,24)
    return Image.open(path).convert('RGB').crop((x,y,x+w,y+h)).tobytes()

def animated(identifier,label):
    hashes=set()
    for index in range(8):
        pixels=capture(identifier,label+'-'+str(index))
        check(label+'-native-frame-'+str(index),pixels in references)
        hashes.add(hashlib.sha256(pixels).hexdigest())
        time.sleep(.035)
    check(label+'-moving',len(hashes)>1,unique_images=len(hashes))

assert evaluate('document.title')=='Native animation invalidation transport','Use the private fixture'
animated('animated','first')
animated('second','second')
before=capture('static','static-before');time.sleep(.3)
check('determinate-stable',capture('static','static-after')==before)
browser('click','#animated')
check('read-only-click',evaluate('events.length===1 && events[0].type==="click" && events[0].trusted'))

evaluate('document.getElementById("animated").value=.5;true')
before=capture('animated','stopped-before');time.sleep(.3)
check('stopped-stable',capture('animated','stopped-after')==before)
evaluate('document.getElementById("animated").removeAttribute("value");true')
animated('animated','restarted')

evaluate('''(()=>{let e=document.getElementById('animated'),parent=e.parentNode;
 e.remove();parent.append(e);return true;})()''')
animated('animated','reinserted')
evaluate('document.getElementById("animated").remove();document.getElementById("second").remove();true')
before=capture('static','only-static-before');time.sleep(.3)
check('remove-all-animated',capture('static','only-static-after')==before)
evaluate('''(()=>{const e=document.createElement('progress');e.id='new-animation';
 document.getElementById('static').parentNode.append(e);return true;})()''')
animated('new-animation','new-control')
check('no-animation-edit-events',evaluate('events.every(e=>e.type==="click")'))

evaluate('window.__nxsReloadPending=true;location.reload();true')
browser('wait','--fn','document.readyState==="complete" && !!window.events && !window.__nxsReloadPending')
animated('animated','reloaded')
print(json.dumps(dict(passed=len(results),results=results)))
