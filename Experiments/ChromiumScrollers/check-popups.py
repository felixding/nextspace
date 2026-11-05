#!/usr/bin/env python3
"""Exercise native select pixels and real browser model/event lifecycle."""
import argparse,json,subprocess,time
from pathlib import Path
from PIL import Image,ImageChops
p=argparse.ArgumentParser(description=__doc__)
for key in ('session','cdp'):p.add_argument('--'+key,required=True)
for key in ('references','focused-references','output'):p.add_argument('--'+key,type=Path,required=True)
p.add_argument('--native-state-command',required=True,help='JSON argv for the owned helper inspect-popup.py command')
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
command=['agent-browser','--session',a.session,'--cdp',a.cdp];results=[]
def browser(*args):return subprocess.check_output(command+list(args),text=True)
def evaluate(script):return json.loads(browser('eval',script))
def check(case,condition,**data):
    results.append(dict(case=case,passed=bool(condition),**data))
    (a.output/'results.json').write_text(json.dumps(results,indent=2)+'\n');assert condition,results[-1]
def reset():
    evaluate('window.__nxsReloadPending=true;location.reload();true')
    browser('wait','--fn','document.readyState==="complete" && !!window.events && !window.__nxsReloadPending')
def state(identifier='select'):
    return evaluate('(()=>{const e=document.getElementById('+json.dumps(identifier)+');return {value:e.value,index:e.selectedIndex,open:e.matches(":open")}})()')
def changes():return evaluate('events.filter(e=>e.type==="input"||e.type==="change")')
def keys(*names):
    for name in names:browser('press',name)
def native_state():return json.loads(subprocess.check_output(json.loads(a.native_state_command),text=True))
def wait_highlight(index):
    deadline=time.monotonic()+3
    while True:
        state=native_state()
        if state['highlighted']==index:return
        assert time.monotonic()<deadline,state
        time.sleep(.01)
def compare(identifier,focused=False):
    path=(a.output/(identifier+('-focused' if focused else '-normal')+'.png')).resolve()
    browser('screenshot',str(path));reference=(a.focused_references if focused else a.references)/(identifier+'.png')
    expected=Image.open(reference).convert('RGBA');canvas=Image.new('RGBA',expected.size,'white');canvas.alpha_composite(expected)
    rect=evaluate('document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
    x,y=round(rect['x']),round(rect['y'])
    actual=Image.open(path).convert('RGB').crop((x,y,x+expected.width,y+expected.height))
    delta=ImageChops.difference(actual,canvas.convert('RGB')).getbbox()
    check('native-pixels-'+identifier+('-focused' if focused else ''),delta is None,difference=delta)
assert evaluate('document.title')=='Native select model transport'
reset()
for identifier in ('select','grouped','empty'):compare(identifier)
# Preserve the default screenshot as an unresolved integration difference.
# Chromium's UA stylesheet applies opacity .7 to disabled selects in addition
# to native disabled drawing. The explicit-opacity case checks the underlying
# native image; it does not qualify the default disabled presentation.
browser('screenshot',str((a.output/'disabled-default-opacity.png').resolve()))
(a.output/'limitations.json').write_text(json.dumps(dict(disabled_default_opacity=
    evaluate('getComputedStyle(document.querySelector("#disabled")).opacity'),
    default_disabled_presentation_qualified=False),indent=2)+'\n')
evaluate('document.querySelector("#disabled").style.opacity=1;true');compare('disabled')
for identifier in ('select','grouped','empty'):
    browser('focus','#'+identifier);compare(identifier,True)
reset();browser('focus','#select');keys('Space')
check('native-open-lifecycle',state()['open'])
keys('ArrowDown','Enter');current=state()
check('native-key-selection',current==dict(value='b',index=1,open=False),actual=current)
check('trusted-application-events',[e['type'] for e in changes()]==['input','change'] and all(e['trusted'] for e in changes()))
evaluate('events=[];true');keys('Space','ArrowDown','Escape')
check('native-cancel-lifecycle',state()==dict(value='b',index=1,open=False) and not changes())
reset();browser('focus','#select')
evaluate('document.querySelector("#select").addEventListener("keydown",e=>e.preventDefault());true');keys('Space')
check('page-cancels-key-before-native',not state()['open'] and not changes())
reset();browser('focus','#select');evaluate('document.querySelector("#select").dispatchEvent(new KeyboardEvent("keydown",{key:" ",bubbles:true,cancelable:true}));true')
check('untrusted-key-no-menu',not state()['open'] and not changes())
reset();browser('focus','#select');keys('Tab')
check('native-focus-navigation',evaluate('document.activeElement.id')=='grouped')
reset();browser('click','#show-picker')
check('application-show-picker-native',state()['open'] and native_state()['visible'])
keys('ArrowDown','Enter')
check('application-show-picker-selection',state()==dict(value='b',index=1,open=False) and len(changes())==2)
keys('Space');evaluate('document.querySelector("#select").blur();true')
check('application-blur-closes-native-menu',not state()['open'] and not native_state()['visible'])
reset();browser('focus','#grouped');keys('Space','ArrowDown','Enter')
check('disabled-item-no-application-action',state('grouped')['index']==0 and not changes());keys('Escape')
keys('Space','ArrowDown','ArrowDown','Enter')
check('duplicate-label-identity',state('grouped')['index']==2 and len(changes())==2 and all(e['trusted'] for e in changes()))
reset();browser('focus','#select');keys('Space')
evaluate('document.querySelector("#select").options[1].replaceWith(new Option("Replacement","replacement"));true')
keys('ArrowDown','Enter')
check('stale-option-cannot-select-replacement',state()['value']=='a' and not changes() and not state()['open'])
reset();browser('focus','#select');keys('Space')
evaluate('document.querySelector("#select").remove();true')
check('remove-open-control',evaluate('!document.querySelector("#select")'))
reset();browser('focus','#select');keys('Space')
evaluate('const e=document.querySelector("#select");e.remove();document.body.append(e);e.focus();true')
check('reinsert-cancels-old-menu',state()['value']=='a' and not changes() and not state()['open'])
reset();browser('focus','#select')
evaluate('document.querySelector("#select").addEventListener("input",e=>e.target.remove(),{once:true});true')
keys('Space','ArrowDown','Enter')
check('remove-in-native-action-callback',evaluate('!document.querySelector("#select")'))
reset();browser('focus','#empty');keys('Space')
browser('wait','--fn','!document.querySelector("#empty").matches(":open")')
check('empty-menu-stays-closed',not state('empty')['open'] and not changes())
reset();browser('mouse','move','300','104');browser('mouse','down')
try:check('native-mouse-tracking-opens',state()['open'])
finally:browser('mouse','up')
check('native-release-on-selected-item',not state()['open'] and not changes())
reset();browser('mouse','move','300','104');browser('mouse','down')
try:
    native=next(item for item in json.loads((a.references/'results.json').read_text()) if item['id']=='select')['native_item_rects'][1]
    rect=evaluate('document.querySelector("#select").getBoundingClientRect().toJSON()')
    browser('mouse','move',str(round(rect['x']+native['x']+native['width']/2)),str(round(rect['y']+native['y']+native['height']/2)))
    wait_highlight(1)
finally:browser('mouse','up')
check('native-mouse-selection',state()==dict(value='b',index=1,open=False) and len(changes())==2 and all(e['trusted'] for e in changes()))
reset();browser('mouse','move','300','104');browser('mouse','down')
try:
    browser('mouse','move','600','400');wait_highlight(-1)
finally:browser('mouse','up')
check('native-mouse-cancel-outside',not state()['open'] and state()['value']=='a' and not changes())
reset();evaluate('document.querySelector("#select").addEventListener("mousedown",e=>e.preventDefault());true')
browser('mouse','move','300','104');browser('mouse','down');browser('mouse','up')
check('page-cancels-mouse-before-native',not state()['open'] and not changes())
print(json.dumps(dict(passed=len(results),results=results)))
