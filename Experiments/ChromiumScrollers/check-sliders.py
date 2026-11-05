#!/usr/bin/env python3
"""Check native slider pixels, data/keys, live tracking and application events."""
import argparse,json,subprocess
from pathlib import Path
from PIL import Image,ImageChops
p=argparse.ArgumentParser(description=__doc__)
for name in ['session','cdp']:p.add_argument('--'+name,required=True)
for name in ['controls','references','focused-references','output']:p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
cmd=['agent-browser','--session',a.session,'--cdp',a.cdp];results=[]
controls={i['id']:i for i in json.loads(a.controls.read_text())}
key_results={i['id']:i.get('keys',[]) for i in json.loads((a.references/'results.json').read_text())}
def browser(*args):return subprocess.check_output(cmd+list(args),text=True)
def evaluate(js):return json.loads(browser('eval',js))
def check(case,value,**data):
 results.append(dict(case=case,passed=bool(value),**data));(a.output/'results.json').write_text(json.dumps(results,indent=2)+'\n');assert value,results[-1]
def reset():
 evaluate('window.__nxsReloadPending=true;location.reload();true')
 browser('wait','--fn','document.readyState==="complete" && !!window.events && !window.__nxsReloadPending')
def value(identifier):return evaluate('document.getElementById('+json.dumps(identifier)+').valueAsNumber')
def compare(identifier,focused=False):
 item=controls[identifier];path=(a.output/(identifier+('-focused' if focused else '-normal')+'.png')).resolve()
 browser('screenshot',str(path));expected=Image.open((a.focused_references if focused else a.references)/(identifier+'.png')).convert('RGB')
 x,y,w,h=[item[k] for k in ['x','y','width','height']]
 delta=ImageChops.difference(Image.open(path).convert('RGB').crop((x,y,x+w,y+h)),expected).getbbox()
 check('pixels-'+identifier+('-focused' if focused else ''),delta is None,difference=delta)
assert evaluate('document.title')=='Native slider model transport'
reset()
for identifier in controls:compare(identifier)
for identifier,item in controls.items():
 if not item['enabled']:continue
 reset();browser('focus','#'+identifier);compare(identifier,True)
 for expected in key_results[identifier]:
  evaluate('events=[];true');browser('press',expected['key'])
  check('native-key-'+identifier+'-'+expected['key'],abs(value(identifier)-expected['value'])<1e-10,actual=value(identifier),native=expected['value'])
  check('trusted-key-'+identifier+'-'+expected['key'],evaluate('events.every(e=>e.trusted) && !events.some(e=>e.type==="click")'))
reset();browser('focus','#range');evaluate('document.getElementById("range").addEventListener("keydown",e=>e.preventDefault());true');browser('press','ArrowRight')
check('keydown-cancelled',value('range')==50 and evaluate('!events.some(e=>e.type==="input")'))
reset();evaluate('document.getElementById("range").addEventListener("mousedown",e=>e.preventDefault());true')
browser('mouse','move','410','106');browser('mouse','down');browser('mouse','up')
check('mousedown-cancelled',value('range')==50 and evaluate('!events.some(e=>e.type==="input")'))
reset();browser('mouse','move','410','154');browser('mouse','down')
try:
 browser('wait','--fn','document.getElementById("custom").valueAsNumber>0')
 check('native-live-value',value('custom')>0)
 browser('mouse','move','600','180')
finally:browser('mouse','up')
check('drag-outside-native-range',value('custom')==10)
check('single-change-on-release',evaluate('events.filter(e=>e.id==="custom"&&e.type==="change").length===1 && events.every(e=>e.trusted)'))
reset();item=controls['disabled']
browser('mouse','move',str(item['x']+item['width']//2),str(item['y']+item['height']//2));browser('mouse','down');browser('mouse','up')
check('disabled',value('disabled')==35 and evaluate('!events.some(e=>e.type==="input"||e.type==="change")'))
reset();browser('focus','#range');evaluate('''for(const type of ['keydown','keyup'])document.getElementById('range').dispatchEvent(new KeyboardEvent(type,{key:'ArrowRight',bubbles:true,cancelable:true}));true''')
check('untrusted-key-no-native-change',value('range')==50)
reset();evaluate('document.getElementById("custom").addEventListener("input",e=>e.target.remove(),{once:true});true')
browser('mouse','move','410','154');browser('mouse','down')
browser('wait','--fn','!document.getElementById("custom")');browser('mouse','up')
check('remove-during-native-action',evaluate('!document.getElementById("custom")'))
reset();browser('focus','#range');evaluate('''document.getElementById('range').addEventListener('keydown',e=>{const n=e.target;n.remove();document.body.append(n);n.focus();},{once:true});true''');browser('press','ArrowRight')
check('reinsert-cancels-old-key',value('range')==50)
print(json.dumps(dict(passed=len(results),results=results)))
