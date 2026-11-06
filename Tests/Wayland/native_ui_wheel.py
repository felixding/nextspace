#!/usr/bin/env python3
"""Compare real seat wheel input and browser wheel defaults with GNUstep.

agent-browser inspects the owned page and captures images. Its wheel command
targets (0,0), so the existing explicit-coordinate CDP input pattern supplies
only wheel events and modifier flags. Real-seat cases use the fixture's private
inherited compositor capability.
"""
import argparse,json,re,shlex,subprocess,time,urllib.request
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
for name in ['ssh-config','fixture','session','cdp','output']:p.add_argument('--'+name,required=True)
p.add_argument('--node',default='node')
p.add_argument('--supervised',action='store_true',help='Check host replacement using native_ui_session.py instead of the seat fixture')
a=p.parse_args();repo=Path(__file__).resolve().parents[2];out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=True);rows=[]
browser=['agent-browser','--session',a.session,'--cdp',a.cdp]
def ab(*args):return subprocess.check_output(browser+list(args),text=True)
def js(code):return json.loads(ab('eval',code))
def remote(code):return json.loads(subprocess.check_output(['ssh','-F',a.ssh_config,'lima-nextspace-gui',shlex.join(['python3','-c',code])],text=True))
def control(command):
    if a.supervised:
        assert command.startswith('reference '),command
        return supervised('native-reference',**json.loads(command.split(' ',1)[1]))
    return remote('import json,socket\nwith socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:\n s.settimeout(40);s.connect('+repr(a.fixture+'/control.sock')+');s.send('+repr(json.dumps(dict(command=command)).encode())+');print(s.recv(65536).decode())')
def supervised(operation,**values):
    return remote('import json,socket\nwith socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:\n s.settimeout(40);s.connect('+repr(a.fixture+'/control.sock')+');s.send('+repr(json.dumps(dict(operation=operation,**values)).encode())+');print(s.recv(65536).decode())')
def wait(read,predicate):
    end=time.monotonic()+15
    while True:
        value=read()
        if predicate(value):return value
        assert time.monotonic()<end,value;time.sleep(.03)
def check(case,passed,**evidence):
    rows.append(dict(case=case,passed=bool(passed),**evidence));(out/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
def state():return js('(()=>{let e=document.getElementById("normal");return {top:e.scrollTop,start:e.selectionStart,end:e.selectionEnd,value:e.value,events:window.__wheelEvents||[],scroll:window.__scrollEvents||[]}})()')
text='\n'.join('Line '+str(i) for i in range(60))
def seed(top=200):
    js('(()=>{let e=document.getElementById("normal");e.value='+json.dumps(text)+';e.setSelectionRange(0,0);document.body.tabIndex=-1;document.body.focus();e.scrollTop='+str(top)+';window.__wheelEvents=[];window.__scrollEvents=[];return true})()')
def wheel(dx,dy,modifiers=0,x=130,y=90):
    with urllib.request.urlopen(a.cdp+'/json/list') as stream:pages=json.load(stream)
    pages=[p for p in pages if p.get('type')=='page' and p.get('url')=='file:///workspace/Experiments/ChromiumScrollers/test-multiline.html'];assert len(pages)==1,pages
    code="""const s=new WebSocket(process.argv[1]);await new Promise((r,j)=>{s.addEventListener('open',r,{once:true});s.addEventListener('error',j,{once:true})});const result=await new Promise((r,j)=>{const t=setTimeout(()=>j(new Error('Owned input timed out')),10000);s.addEventListener('message',e=>{const v=JSON.parse(e.data);if(v.id===1){clearTimeout(t);r(v)}});s.send(JSON.stringify({id:1,method:'Input.dispatchMouseEvent',params:JSON.parse(process.argv[2])}))});s.close();if(result.error)throw new Error(JSON.stringify(result));"""
    subprocess.run([a.node,'--input-type=module','-e',code,pages[0]['webSocketDebuggerUrl'],json.dumps(dict(type='mouseWheel',x=x,y=y,deltaX=dx,deltaY=dy,modifiers=modifiers))],check=True,timeout=15)
def compare(label,dy,cdp_modifiers=0,native_modifiers=0,start=200,x=130,y=90):
    seed(start);rect=js('document.getElementById("normal").getBoundingClientRect().toJSON()')
    reference=control('reference '+json.dumps(dict(name=out.name+'-'+label,controls=[dict(id='textarea',kind=9,
        width=rect['width'],height=rect['height'],enabled=1,state=0,title='',text=text,scroll=[0,start],
        wheel=[dict(dx=0,dy=dy,modifiers=native_modifiers)])])))
    expected=reference['reference'][0]['viewport']['y'];wheel(0,dy,cdp_modifiers,x,y)
    actual=wait(state,lambda s:s['top']==expected)
    check(label+'-native-offset',actual['value']==text and actual['start']==0 and actual['end']==0,state=actual,expected=expected)
    if expected!=start:
        actual=wait(state,lambda s:any(v['trusted'] and v['top']==expected for v in s['scroll']))
        check(label+'-trusted-events',any(v['trusted'] and v['cancelable'] for v in actual['events']),state=actual)
    screenshot=ab('screenshot','--screenshot-dir',str(out/label));image=Path(re.search(r'Screenshot saved to (.+)',screenshot).group(1).strip())
    mounted='/workspace/'+str(image.relative_to(repo));box=tuple(round(rect[k]) for k in ['left','top','right','bottom'])
    diff=remote('from PIL import Image,ImageChops\nimport json\na=Image.open('+repr(mounted)+').convert("RGB").crop('+repr(box)+')\nb=Image.open('+repr(reference['path']+'/textarea.png')+').convert("RGB");d=ImageChops.difference(a,b);print(json.dumps(dict(equal=d.getbbox() is None,box=d.getbbox())))')
    check(label+'-native-pixels',diff['equal'],**diff)

try:
    ab('open','file:///workspace/Experiments/ChromiumScrollers/test-multiline.html');seed()
    if a.supervised:
        initial=supervised('status');chrome=next(w for w in initial['windows'] if w['app_id']=='chromium-browser' and w['level']==0)
        supervised('shell',text='activate '+str(chrome['id']))
        js('window.__wheelRecoveryMarker="retained"')
        for label in ['initial','recovered']:
            if label=='recovered':
                host=supervised('status')['host'];supervised('restart-host')
                wait(lambda:supervised('status'),lambda s:s['host'] and s['host']!=host and any(w['pid']==s['host'] and w['level']==20 and not w['flags']&(2|32) for w in s['windows']))
                check('host-replaced-page-retained',js('window.__wheelRecoveryMarker')=='retained' and any(w['id']==chrome['id'] and w['pid']==chrome['pid'] for w in supervised('status')['windows']))
                ab('screenshot','--screenshot-dir',str(out/'retained-viewport'))
                retained=state()
                check('host-replaced-viewport-retained',retained['top']==220 and retained['value']==text,state=retained)
            seed();wheel(0,2)
            check(label+'-no-page-listener-native-default',wait(state,lambda s:s['top']!=200)['top']==220)
            js('(()=>{let e=document.getElementById("normal");window.__recoveryWheel=v=>__wheelEvents.push({trusted:v.isTrusted,cancelable:v.cancelable});window.__recoveryScroll=v=>__scrollEvents.push({trusted:v.isTrusted,top:e.scrollTop});e.addEventListener("wheel",__recoveryWheel,{passive:false});e.addEventListener("scroll",__recoveryScroll);return true})()')
            compare(label+'-host-wheel',2)
            js('(()=>{let e=document.getElementById("normal");e.removeEventListener("wheel",__recoveryWheel);e.removeEventListener("scroll",__recoveryScroll);return true})()')
        print(json.dumps(dict(passed=len(rows),output=str(out))))
        raise SystemExit(0)
    windows=control('windows');native=next(w for w in windows if w['title']=='Native wheel seat reference')
    chrome=next(w for w in windows if w['app_id']=='chromium-browser')
    assert control(f"move {native['id']} 1000 200")['ok']
    y=chrome['y']+chrome['height']-js('innerHeight')+90;x=chrome['x']+130
    # No page wheel listener exists for these cases. Native handler-region
    # registration must defeat the otherwise competing compositor default.
    for command in ['scroll 1','scroll -1','scroll-v120 60','scroll-v120 -30','scroll-v120 240','scroll-v120 -120']:
        seed();control('native reset 200');control('pointer 1040 220');control(command)
        expected=wait(lambda:control('native state'),lambda s:s['y']!=200)['y']
        control(f'pointer {x} {y}');control(command)
        actual=wait(state,lambda s:s['top']==expected)
        check('seat-'+command.replace(' ','-'),actual['start']==0 and actual['end']==0 and actual['value']==text,native=expected,browser=actual['top'])
    js('(()=>{let e=document.getElementById("normal");window.__cancelWheel=false;window.__wheelObserver=v=>{__wheelEvents.push({trusted:v.isTrusted,cancelable:v.cancelable,dy:v.deltaY});if(__cancelWheel)v.preventDefault()};e.addEventListener("wheel",__wheelObserver,{passive:false});e.addEventListener("scroll",v=>__scrollEvents.push({trusted:v.isTrusted,top:e.scrollTop}));return true})()')
    seed();js('window.__cancelWheel=true');wheel(0,2)
    canceled=wait(state,lambda s:len(s['events'])==1)
    check('page-cancels-native-default',canceled['top']==200 and canceled['events'][0]['trusted'] and canceled['events'][0]['cancelable'],state=canceled)
    js('window.__cancelWheel=false')
    for label,dy,cdp_mod,native_mod,start,px,py in [
        ('down',2,0,0,200,130,90),('fractional',.25,0,0,200,130,90),
        ('end',1000,0,0,200,130,90),('top',-1000,0,0,200,130,90),
        ('shift',2,8,1,200,130,90),('native-alternate',1,4,8,200,130,90),
        ('over-native-scroller',2,0,0,200,34,100)]:
        compare(label,dy,cdp_mod,native_mod,start,px,py)
    js('document.getElementById("normal").removeEventListener("wheel",__wheelObserver);true');seed()
    control(f'pointer {x} {y}');control('scroll 1')
    check('removing-page-listener-retains-native-region',wait(state,lambda s:s['top']!=200)['top']==300)
    ab('open','file:///workspace/Experiments/ChromiumScrollers/test-multiline.html');seed()
    control(f'pointer {x} {y}');control('scroll 1')
    check('reload-rebinds-native-region',wait(state,lambda s:s['top']!=200)['top']==300)
    js('(()=>{let d=document.createElement("div");d.id="wheel-other";d.style="position:absolute;left:400px;top:40px;width:200px;height:150px;overflow:scroll";d.innerHTML="<div style=height:2000px>Other scroll area</div>";document.body.append(d);return true})()')
    wheel(0,20,x=450,y=100)
    ordinary=wait(lambda:js('document.getElementById("wheel-other").scrollTop'),lambda v:v>0)
    check('other-scroll-area-retains-engine-default',True,top=ordinary)
    seed();js('document.getElementById("normal").addEventListener("wheel",v=>v.currentTarget.value="Short",{once:true});true')
    wheel(0,2)
    canonical=wait(state,lambda s:s['value']=='Short' and s['top']==0)
    check('page-mutation-precedes-native-default',canonical['top']==0,state=canonical)
    seed();js('document.getElementById("normal").addEventListener("wheel",v=>{window.__removed=v.currentTarget;__removed.remove()},{once:true});true')
    wheel(0,2)
    check('removal-during-wheel-releases-binding',wait(lambda:js('!document.getElementById("normal")'),bool))
    js('document.querySelector("label").append(__removed);true');seed()
    ab('screenshot','--screenshot-dir',str(out/'reinserted'))
    control(f'pointer {x} {y}');control('scroll 1')
    check('reinserted-control-rebinds-native-region',wait(state,lambda s:s['top']!=200)['top']==300)
    print(json.dumps(dict(passed=len(rows),output=str(out))))
finally:ab('close')
