#!/usr/bin/env python3
"""Compare an owned Chromium textarea with the live native provider.

DOM transactions use CDP; pointer checks use CDP mouse input. This does not
qualify physical wheel input, IME, CSS zoom or other browser builds.
"""
import argparse,json,re,shlex,subprocess,time
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
for name in ['ssh-config','fixture','session','cdp','output']:p.add_argument('--'+name,required=True)
p.add_argument('--restart',action='store_true')
a=p.parse_args();out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=True);rows=[]
repo=Path(__file__).resolve().parents[2]
ssh=['ssh','-F',a.ssh_config,'lima-nextspace-gui']
browser=['agent-browser','--session',a.session,'--cdp',a.cdp]
def remote(code):return json.loads(subprocess.check_output(ssh+[shlex.join(['python3','-c',code])],text=True))
def control(operation,**values):
    request=dict(operation=operation,**values)
    return remote('import socket,json\nwith socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:\n s.settimeout(40);s.connect('+repr(a.fixture+'/control.sock')+');s.send('+repr(json.dumps(request).encode())+');print(s.recv(65536).decode())')
def ab(*args):return subprocess.check_output(browser+list(args),text=True)
def js(expression):return json.loads(ab('eval',expression))
def check(case,passed,**evidence):
    rows.append(dict(case=case,passed=bool(passed),**evidence))
    (out/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
def wait(read,predicate,timeout=15):
    end=time.monotonic()+timeout
    while True:
        value=read()
        if predicate(value):return value
        assert time.monotonic()<end,value;time.sleep(.03)
def state():
    return js('(()=>{let e=document.getElementById("normal");return {top:e.scrollTop,left:e.scrollLeft,height:e.scrollHeight,width:e.scrollWidth,clientHeight:e.clientHeight,clientWidth:e.clientWidth,clientLeft:e.clientLeft,clientTop:e.clientTop,start:e.selectionStart,end:e.selectionEnd,rect:e.getBoundingClientRect().toJSON(),events:window.__nativeScrollEvents}})()')
def seed(text,width=240,height=120,scroll=0):
    js('(()=>{let e=document.getElementById("normal");e.style.width='+json.dumps(str(width)+'px')+';e.style.height='+json.dumps(str(height)+'px')+';e.value='+json.dumps(text)+';e.setSelectionRange(0,0);document.body.tabIndex=-1;document.body.focus();window.__nativeScrollEvents=[];if(!e.__nativeScrollObserved){e.__nativeScrollObserved=true;e.addEventListener("scroll",v=>window.__nativeScrollEvents.push({top:e.scrollTop,trusted:v.isTrusted}))}e.scrollTop='+str(scroll)+';return true})()')
def compare(label,text,width=240,height=120,scroll=0):
    seed(text,width,height,scroll);current=state();rect=current['rect']
    reference=control('native-reference',name=out.name+'-'+label,controls=[dict(id='textarea',kind=9,
        width=rect['width'],height=rect['height'],title='',state=0,enabled=1,text=text,scroll=[0,scroll])])
    assert reference['ok'];native=reference['reference'][0]
    current=wait(state,lambda s:s['top']==native['viewport']['y'])
    check(label+'-native-geometry',all(current[key]==round(value) for key,value in {
        'clientWidth':native['clip']['width'],'clientHeight':native['clip']['height'],
        'clientLeft':native['clip']['x'],'clientTop':native['clip']['y'],
        'width':native['content']['width'],'height':native['content']['height']}.items()),dom=current,native=native)
    if scroll:
        current=wait(state,lambda s:any(e['top']==s['top'] and e['trusted'] for e in s['events']))
        check(label+'-trusted-scroll-event',True,events=current['events'])
    screenshot=ab('screenshot','--screenshot-dir',str(out/label))
    path=Path(re.search(r'Screenshot saved to (.+)',screenshot).group(1).strip())
    mounted='/workspace/'+str(path.relative_to(repo))
    pixels=remote('from PIL import Image,ImageChops\nimport json\na=Image.open('+repr(mounted)+').convert("RGB").crop('+repr(tuple(round(rect[k]) for k in ['left','top','right','bottom']))+')\nb=Image.open('+repr(reference['path']+'/textarea.png')+').convert("RGB")\nd=ImageChops.difference(a,b);print(json.dumps(dict(equal=d.getbbox() is None,box=d.getbbox(),size=a.size)))')
    check(label+'-native-pixels',pixels['equal'],**pixels)
    return current

text='\n'.join('Line '+str(i) for i in range(30))
try:
    for suffix in ['initial']+(['recovered'] if a.restart else []):
        if suffix=='recovered':
            before=control('status')['host'];control('restart-host')
            wait(lambda:control('status')['host'],lambda pid:pid and pid!=before)
        compare(suffix+'-top',text)
        compare(suffix+'-middle',text,scroll=73)
        compare(suffix+'-end',text,scroll=1000000)
        compare(suffix+'-resized',text,width=150,height=80,scroll=1000000)
        compare(suffix+'-wrapped','An ordinary native text view wraps this sentence. '*12,width=150,height=80)
        compare(suffix+'-short','Alpha\nBeta')
        seed(text);current=state();rect=current['rect']
        js('document.getElementById("normal").focus()')
        # Coordinates observed in this fixture's native screenshot. The
        # arrow belongs to NSScrollView; no engine scrollbar exists here.
        x=rect['left']+10;y=rect['bottom']-13
        ab('mouse','move',str(x),str(y));ab('mouse','down');ab('mouse','up')
        clicked=wait(state,lambda s:s['top']>0)
        check(suffix+'-native-arrow',clicked['start']==0 and clicked['end']==0 and any(e['trusted'] and e['top']>0 for e in clicked['events']),state=clicked)
        start=clicked['top'];ab('mouse','down');time.sleep(.55)
        held=wait(state,lambda s:s['top']>start)
        ab('mouse','up');released=state();time.sleep(.35);stopped=state()
        check(suffix+'-native-arrow-repeat-release',stopped['top']==released['top'] and held['top']>start,held=held['top'],released=released['top'],stopped=stopped['top'])
    print(json.dumps(dict(passed=len(rows),output=str(out))))
finally:
    try:ab('mouse','up')
    except subprocess.CalledProcessError:pass
    finally:ab('close')
