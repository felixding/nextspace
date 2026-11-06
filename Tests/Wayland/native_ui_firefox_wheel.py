#!/usr/bin/env python3
"""Compare Firefox wheel defaults with ordinary native GNUstep scroll views."""
import argparse,json,shlex,subprocess,time
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
for name in ['ssh-config','fixture','output']:p.add_argument('--'+name,required=True)
p.add_argument('--supervised',action='store_true',help='Use native_ui_session.py and check host recovery instead of seat input')
a=p.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True);rows=[]
def remote(code):
    return json.loads(subprocess.check_output(['ssh','-F',a.ssh_config,'lima-nextspace-gui',shlex.join(['python3','-c',code])],text=True))
def control(command):
    if a.supervised:
        if command.startswith('firefox '):
            request=json.loads(command.split(' ',1)[1]);request['operation']='firefox-'+request['operation']
        elif command.startswith('reference '):request=dict(operation='native-reference',**json.loads(command.split(' ',1)[1]))
        else:request=dict(operation=command)
    else:request=dict(command=command)
    return remote('import json,socket\nwith socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:\n s.settimeout(40);s.connect('+repr(a.fixture+'/control.sock')+');s.send('+repr(json.dumps(request).encode())+');print(s.recv(65536).decode())')
def firefox(operation,**values):return control('firefox '+json.dumps(dict(operation=operation,**values)))
def js(code):return firefox('eval',script='return '+code)['value']
def wait(read,predicate):
    end=time.monotonic()+20
    while True:
        value=read()
        if predicate(value):return value
        assert time.monotonic()<end,value;time.sleep(.03)
def check(case,passed,**evidence):
    rows.append(dict(case=case,passed=bool(passed),**evidence));(out/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
text='\n'.join('Line '+str(i) for i in range(60))
def seed(top=200):
    js('(()=>{let e=document.getElementById("native-wheel");e.disabled=false;e.readOnly=false;e.value='+json.dumps(text)+';e.setSelectionRange(0,0);document.body.tabIndex=-1;document.body.focus();e.scrollTop='+str(top)+';window.__wheelEvents=[];window.__scrollEvents=[];return true})()')
def state():return js('(()=>{let e=document.getElementById("native-wheel");return {top:e.scrollTop,start:e.selectionStart,end:e.selectionEnd,value:e.value,events:window.__wheelEvents,scroll:window.__scrollEvents}})()')
def wheel(dy,x=130,y=90,dx=0,key=None):
    try:
        if key:firefox('actions',actions=[dict(type='key',id='native-wheel-keys',actions=[dict(type='keyDown',value=key)])])
        firefox('actions',actions=[dict(type='wheel',id='native-wheel-input',actions=[dict(type='scroll',origin='viewport',x=x,y=y,deltaX=dx,deltaY=dy,duration=0)])])
    finally:
        if key:firefox('actions',actions=[dict(type='key',id='native-wheel-keys',actions=[dict(type='keyUp',value=key)])])
def compare(label,dy,key=None,native_modifiers=0,start=200,x=130,y=90,enabled=True,editable=True):
    seed(start);js('(()=>{let e=document.getElementById("native-wheel");e.disabled='+json.dumps(not enabled)+';e.readOnly='+json.dumps(not editable)+';return true})()')
    rect=js('document.getElementById("native-wheel").getBoundingClientRect().toJSON()')
    reference=control('reference '+json.dumps(dict(name=out.name+'-'+label,controls=[dict(id='textarea',kind=9,width=rect['width'],height=rect['height'],enabled=int(enabled),editable=int(editable),state=0,title='',text=text,scroll=[0,start],wheel=[dict(dy=dy,modifiers=native_modifiers)])])))
    expected=reference['reference'][0]['viewport']['y'];wheel(dy,x,y,key=key)
    wait(state,lambda s:any(e['trusted'] and e['cancelable'] for e in s['events']))
    current=wait(state,lambda s:s['top']==expected)
    check(label+'-native-offset',current['value']==text and current['start']==current['end']==0,expected=expected,state=current)
    if expected!=start and enabled:
        current=wait(state,lambda s:any(e['trusted'] and e['top']==expected for e in s['scroll']))
        check(label+'-trusted-events',any(e['trusted'] and e['cancelable'] for e in current['events']),state=current)
    elif not enabled:
        # Firefox suppresses scroll events on disabled textareas even when its
        # original engine scrolls them. Establish that policy on a separate
        # appearance:none control, rather than manufacturing a DOM event.
        js('(()=>{let old=document.getElementById("wheel-engine-disabled");if(old)old.remove();let e=document.createElement("textarea");e.id="wheel-engine-disabled";e.style="position:absolute;left:400px;top:200px;width:240px;height:120px;appearance:none";e.value='+json.dumps(text)+';e.disabled=true;document.body.append(e);window.__engineDisabledScroll=[];e.addEventListener("scroll",v=>__engineDisabledScroll.push({top:e.scrollTop,trusted:v.isTrusted}));e.scrollTop=200;return true})()')
        wheel(20,x=450,y=250)
        wait(lambda:js('document.getElementById("wheel-engine-disabled").scrollTop'),lambda v:v>200)
        time.sleep(.25);current=state();baseline=js('({events:__engineDisabledScroll,top:document.getElementById("wheel-engine-disabled").scrollTop,left:document.getElementById("wheel-engine-disabled").clientLeft})')
        check(label+'-engine-scroll-event-policy',not baseline['events'] and baseline['left']==2 and not any(e['top']==expected for e in current['scroll']),native=current,engine=baseline)
    screen=firefox('screenshot')['path'];box=tuple(round(rect[k]) for k in ['left','top','right','bottom'])
    diff=remote('from pathlib import Path\nfrom PIL import Image,ImageChops\nimport json\np=Path('+repr(screen)+');saved=p.with_name('+repr(out.name+'-'+label+'.png')+');saved.write_bytes(p.read_bytes());a=Image.open(saved).convert("RGB").crop('+repr(box)+');b=Image.open('+repr(reference['path']+'/textarea.png')+').convert("RGB");d=ImageChops.difference(a,b);print(json.dumps(dict(equal=d.getbbox() is None,box=d.getbbox(),screen=str(saved))))')
    check(label+'-native-pixels',diff['equal'],**diff)

js('(()=>{for(let id of ["native-wheel","wheel-other","wheel-engine-disabled"])document.getElementById(id)?.remove();document.body.style.minHeight="";window.scrollTo(0,0);let e=document.createElement("textarea");e.id="native-wheel";e.style="display:block;width:240px;height:120px";document.body.prepend(e);window.__wheelEvents=[];window.__scrollEvents=[];e.addEventListener("scroll",v=>__scrollEvents.push({top:e.scrollTop,trusted:v.isTrusted}));return true})()')
seed();firefox('screenshot')
if not a.supervised:
    windows=control('windows');native=next(w for w in windows if w['title']=='Native wheel seat reference');browser=next(w for w in windows if w['app_id']=='firefox-esr')
    assert control(f"move {native['id']} 1000 200")['ok']
    x=browser['x']+130;y=browser['y']+browser['height']-js('innerHeight')+90
    for command in ['scroll 1','scroll -1','scroll-v120 60','scroll-v120 -30','scroll-v120 240','scroll-v120 -120']:
        seed();control('native reset 200');control(f"raise {native['id']}");control('pointer 1040 220');control(command)
        expected=wait(lambda:control('native state'),lambda s:s['y']!=200)['y']
        control(f"raise {browser['id']}");control(f'pointer {x} {y}');control(command)
        actual=wait(state,lambda s:s['top']==expected)
        check('seat-'+command.replace(' ','-'),actual['start']==0 and actual['end']==0 and actual['value']==text,native=expected,browser=actual['top'])
observer='''window.__cancelWheel=false;window.__wheelAfter=null;
window.__wheelObserver=e=>{window.__lastWheel=e;if(__cancelWheel)e.preventDefault();
__wheelEvents.push({trusted:e.isTrusted,cancelable:e.cancelable,dy:e.deltaY,mode:e.deltaMode,prevented:e.defaultPrevented});
window.__wheelAfter=null;setTimeout(()=>{window.__wheelAfter=e.defaultPrevented},0)};
document.getElementById("native-wheel").addEventListener("wheel",__wheelObserver,{passive:false});'''
js('(()=>{let s=document.createElement("script");s.textContent='+json.dumps(observer)+';document.body.append(s);s.remove();return true})()')
try:
    seed();js('window.__cancelWheel=true');wheel(2)
    canceled=wait(state,lambda s:len(s['events'])==1)
    check('page-cancellation-keeps-native-offset',canceled['top']==200 and canceled['events'][0]['trusted'] and canceled['events'][0]['cancelable'] and canceled['events'][0]['prevented'],state=canceled)
    js('window.__cancelWheel=false')
    for label,dy,key,native_mod,start,px,py in [
        ('down',2,None,0,200,130,90),('up',-2,None,0,200,130,90),
        ('end',1000,None,0,200,130,90),('top',-1000,None,0,200,130,90),
        ('shift',2,'\ue008',1,200,130,90),('native-alternate',1,'\ue03d',8,200,130,90),
        ('over-native-scroller',2,None,0,200,40,100)]:
        compare(label,dy,key,native_mod,start,px,py)
    compare('read-only',2,editable=False)
    compare('disabled',2,enabled=False)
    check('native-ack-not-exposed-as-page-cancellation',wait(lambda:js('window.__wheelAfter'),lambda v:v is not None) is False)
    js('document.getElementById("native-wheel").removeEventListener("wheel",__wheelObserver);true');seed()
    wheel(2);check('listener-removal-retains-native-wheel-region',wait(state,lambda s:s['top']!=200)['top']==220)
    js('document.body.style.minHeight="2500px";window.scrollTo(0,0);true');seed(1000000);end=state()['top'];wheel(20);time.sleep(.25)
    check('native-end-does-not-scroll-ancestor',state()['top']==end and js('scrollY')==0,top=state()['top'],page=js('scrollY'))
    seed();js('document.getElementById("native-wheel").addEventListener("wheel",e=>e.currentTarget.value="Short",{once:true});true');wheel(2)
    changed=wait(state,lambda s:s['value']=='Short' and s['top']==0)
    check('page-mutation-precedes-native-default',True,state=changed)
    seed();js('document.getElementById("native-wheel").addEventListener("wheel",e=>{window.__removed=e.currentTarget;__removed.remove()},{once:true});true');wheel(2)
    check('removal-during-wheel-releases-binding',wait(lambda:js('!document.getElementById("native-wheel")'),bool))
    js('document.body.prepend(__removed);true');seed();firefox('screenshot');wheel(2)
    check('reinserted-control-rebinds-native-region',wait(state,lambda s:s['top']!=200)['top']==220)
    js('(()=>{let e=document.createElement("div");e.id="wheel-other";e.style="position:absolute;left:400px;top:40px;width:200px;height:150px;overflow:scroll";e.innerHTML="<div style=height:2000px>Other scroll area</div>";document.body.append(e);return true})()');wheel(20,x=450,y=100)
    check('ordinary-scroll-area-retains-engine-default',wait(lambda:js('document.getElementById("wheel-other").scrollTop'),lambda v:v>0)>0)
    if a.supervised:
        seed();js('window.__wheelRecoveryMarker="retained"');wheel(2);wait(state,lambda s:s['top']==220)
        before=control('status');control('restart-host')
        wait(lambda:control('status'),lambda s:s['host'] and s['host']!=before['host'] and any(w['pid']==s['host'] and w['level']==20 and not w['flags']&(2|32) for w in s['windows']))
        firefox('screenshot');retained=state()
        check('host-replacement-retains-page-and-offset',js('window.__wheelRecoveryMarker')=='retained' and retained['value']==text and retained['top']==220 and control('status')['browser']==before['browser'],state=retained)
        seed();wheel(2)
        check('recovered-native-default-without-page-listener',wait(state,lambda s:s['top']!=200)['top']==220)
        js('(()=>{let s=document.createElement("script");s.textContent='+json.dumps(observer)+';document.body.append(s);s.remove();return true})()')
        compare('recovered-wheel',2)
    print(json.dumps(dict(passed=len(rows))))
finally:firefox('release-actions')
