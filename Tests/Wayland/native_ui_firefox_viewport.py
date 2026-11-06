#!/usr/bin/env python3
"""Compare an owned Firefox textarea's viewport and complete native image.

The supervised session fixture owns Marionette, the native host and compositor.
DOM transactions use Marionette; pointer actions use trusted WebDriver input.
"""
import argparse,json,shlex,subprocess,time
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
for name in ['ssh-config','fixture','output']:p.add_argument('--'+name,required=True)
p.add_argument('--restart',action='store_true')
p.add_argument('--pointer',action='store_true')
a=p.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True);rows=[]
def remote(code):
    return json.loads(subprocess.check_output(['ssh','-F',a.ssh_config,'lima-nextspace-gui',shlex.join(['python3','-c',code])],text=True))
def control(operation,**values):
    request=dict(operation=operation,**values)
    return remote('import json,socket\nwith socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:\n s.settimeout(40);s.connect('+repr(a.fixture+'/control.sock')+');s.send('+repr(json.dumps(request).encode())+');print(s.recv(65536).decode())')
def js(code):return control('firefox-eval',script='return '+code)['value']
def content_focus():
    # The independent Alt/menubar issue is also handled by the existing seat
    # editing fixture. Focus the real browser pane before trusting pointer input.
    active=control('firefox-eval',context='chrome',script='return (()=>{let m=document.getElementById("toolbar-menubar");return m?.getAttribute("autohide")==="true"&&!m.hasAttribute("inactive")})()')['value']
    if active:control('keyboard',text='forward-modifiers 0 0 0 0\nforward 1 1\nforward 1 0\nsync')
    control('firefox-eval',context='chrome',script='gBrowser.selectedBrowser.focus();return true')
def check(case,passed,**evidence):
    rows.append(dict(case=case,passed=bool(passed),**evidence));(out/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
def wait(read,predicate):
    end=time.monotonic()+20
    while True:
        value=read()
        if predicate(value):return value
        assert time.monotonic()<end,value;time.sleep(.03)
def state():
    return js('(()=>{let e=document.getElementById("native-viewport");return {top:e.scrollTop,left:e.scrollLeft,height:e.scrollHeight,width:e.scrollWidth,clientWidth:e.clientWidth,clientHeight:e.clientHeight,clientLeft:e.clientLeft,clientTop:e.clientTop,start:e.selectionStart,end:e.selectionEnd,value:e.value,events:window.__viewportEvents,rect:e.getBoundingClientRect().toJSON()}})()')
def seed(text,width=240,height=120,scroll=0):
    js('(()=>{let e=document.getElementById("native-viewport");e.style.width='+json.dumps(str(width)+'px')+';e.style.height='+json.dumps(str(height)+'px')+';e.value='+json.dumps(text)+';e.setSelectionRange(0,0);document.body.tabIndex=-1;document.body.focus();window.__viewportEvents=[];e.scrollTop='+str(scroll)+';return true})()')
def compare(label,text,width=240,height=120,scroll=0):
    seed(text,width,height,scroll);current=state();rect=current['rect']
    reference=control('native-reference',name=out.name+'-'+label,controls=[dict(id='textarea',kind=9,width=rect['width'],height=rect['height'],enabled=1,state=0,title='',text=text,scroll=[0,scroll])])
    native=reference['reference'][0];current=wait(state,lambda s:s['top']==native['viewport']['y'])
    expected=dict(clientWidth=native['clip']['width'],clientHeight=native['clip']['height'],clientLeft=native['clip']['x'],clientTop=native['clip']['y'],width=native['content']['width'],height=native['content']['height'])
    check(label+'-native-geometry',all(current[k]==round(v) for k,v in expected.items()),dom=current,native=native)
    if scroll:
        current=wait(state,lambda s:any(e['trusted'] and e['top']==s['top'] for e in s['events']))
        check(label+'-trusted-scroll-event',True,events=current['events'])
    screen=control('firefox-screenshot')['path'];box=tuple(round(rect[k]) for k in ['left','top','right','bottom'])
    diff=remote('from pathlib import Path\nfrom PIL import Image,ImageChops\nimport json\np=Path('+repr(screen)+');saved=p.with_name('+repr(out.name+'-'+label+'.png')+');saved.write_bytes(p.read_bytes());a=Image.open(saved).convert("RGB").crop('+repr(box)+');b=Image.open('+repr(reference['path']+'/textarea.png')+').convert("RGB");d=ImageChops.difference(a,b);print(json.dumps(dict(equal=d.getbbox() is None,box=d.getbbox(),screen=str(saved))))')
    check(label+'-native-pixels',diff['equal'],**diff)
def pointer(action,x=None,y=None):
    step=dict(type=action)
    if action=='pointerMove':step.update(x=round(x),y=round(y),duration=0,origin='viewport')
    else:step['button']=0
    assert control('firefox-actions',actions=[dict(type='pointer',id='native-pointer',parameters=dict(pointerType='mouse'),actions=[step])])['ok']

text='\n'.join('Line '+str(i) for i in range(30))
initial=control('status');window=next(w for w in initial['windows'] if w['pid']==initial['browser'] and w['level']==0)
control('shell',text='activate '+str(window['id']))
js('(()=>{let previous=document.getElementById("native-viewport");if(previous)previous.remove();let e=document.createElement("textarea");e.id="native-viewport";e.style="display:block;width:240px;height:120px";document.body.prepend(e);e.addEventListener("scroll",v=>__viewportEvents.push({top:e.scrollTop,trusted:v.isTrusted}));window.__viewportMarker="retained";window.__viewportEvents=[];return true})()')
try:
    for label in ['initial']+(['recovered'] if a.restart else []):
        if label=='recovered':
            retained=state();host=control('status')['host'];control('restart-host')
            wait(lambda:control('status'),lambda s:s['host'] and s['host']!=host and any(w['pid']==s['host'] and w['level']==20 and not w['flags']&(2|32) for w in s['windows']))
            control('firefox-screenshot');after=state()
            check('host-replacement-retains-page-and-viewport',js('window.__viewportMarker')=='retained' and after['top']==retained['top'] and after['value']==retained['value'],before=retained,after=after)
        compare(label+'-top',text)
        compare(label+'-middle',text,scroll=73)
        compare(label+'-end',text,scroll=1000000)
        compare(label+'-resized',text,width=150,height=80,scroll=1000000)
        compare(label+'-wrapped','An ordinary native text view wraps this sentence. '*12,width=150,height=80)
        compare(label+'-short','Alpha\nBeta')
        if a.pointer:
            content_focus();seed(text);current=state();rect=current['rect'];js('document.getElementById("native-viewport").focus()')
            control('firefox-screenshot');pointer('pointerMove',rect['left']+10,rect['bottom']-13);pointer('pointerDown');pointer('pointerUp')
            clicked=wait(state,lambda s:s['top']>0)
            check(label+'-native-arrow',clicked['start']==0 and clicked['end']==0 and any(e['trusted'] for e in clicked['events']),state=clicked)
            before=clicked['top'];pointer('pointerDown');time.sleep(.55);held=wait(state,lambda s:s['top']>before);pointer('pointerUp');released=state();time.sleep(.35);stopped=state()
            check(label+'-native-arrow-repeat-release',stopped['top']==released['top'] and held['top']>before,held=held['top'],released=released['top'],stopped=stopped['top'])
    seed(text)
    js('(()=>{let e=document.getElementById("native-viewport");e.addEventListener("scroll",()=>{window.__removedViewport=e;e.remove()},{once:true});e.scrollTop=73;return true})()')
    check('scroll-event-removes-control',wait(lambda:js('!document.getElementById("native-viewport")'),bool))
    js('document.body.prepend(__removedViewport);true')
    compare('reinserted-middle',text,scroll=73)
    ordinary=js('(()=>{let e=document.createElement("div");e.style="width:200px;height:150px;overflow:scroll";e.innerHTML="<div style=height:2000px>Ordinary scroll area</div>";document.body.append(e);e.scrollTop=100;return {top:e.scrollTop,height:e.scrollHeight}})()')
    check('ordinary-scroll-container-retains-engine-model',ordinary['top']==100 and ordinary['height']==2000,state=ordinary)
    js('document.getElementById("native-viewport").style.zoom="1.25";true')
    control('firefox-screenshot');zoomed=state()
    check('unsupported-zoom-retains-engine-viewport',zoomed['clientLeft']==2,state=zoomed)
    js('document.getElementById("native-viewport").style.zoom="1";true')
    compare('restored-scale-middle',text,scroll=73)
    print(json.dumps(dict(passed=len(rows))))
finally:
    if a.pointer:control('firefox-release-actions')
