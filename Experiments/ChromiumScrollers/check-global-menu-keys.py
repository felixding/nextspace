#!/usr/bin/env python3
"""Check cold-start native menus and physical keys in an owned Chromium fixture."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import time

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--ssh-config',type=Path,required=True)
p.add_argument('--session',required=True)
p.add_argument('--cdp',default='9941')
p.add_argument('--guest-cdp',type=int,default=9241)
p.add_argument('--fixture',required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
ssh=['ssh','-F',str(a.ssh_config),'lima-nextspace-gui']
ab=['agent-browser','--session',a.session,'--cdp',a.cdp]
rows=[]
def remote(code):
    return json.loads(subprocess.check_output(ssh+[shlex.join(['python3','-c',code])],text=True))
def control(command):
    return remote("import socket,json\nwith socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:\n s.settimeout(15);s.connect("+repr(a.fixture+'/control.sock')+");s.send(json.dumps(dict(command="+repr(command)+")).encode());print(s.recv(65536).decode())")
def key(code,*modifiers):
    for command in [*(f'key {c} 1' for c in modifiers),f'key {code} 1',f'key {code} 0',*(f'key {c} 0' for c in reversed(modifiers))]:
        assert control(command)['ok']
def js(code):return json.loads(subprocess.check_output(ab+['eval',code],text=True))
def pages():
    return remote("import json,urllib.request\nprint(json.dumps([p for p in json.load(urllib.request.urlopen('http://127.0.0.1:"+str(a.guest_cdp)+"/json/list')) if p['type']=='page']))")
def logs():
    return remote('import json;from pathlib import Path\nprint(json.dumps((Path('+repr(a.fixture)+")/'hook.log').read_text()))")
def host_logs():
    return remote('import json;from pathlib import Path\nprint(json.dumps([json.loads(l) for l in (Path('+repr(a.fixture)+")/'helper.jsonl').read_text().splitlines()]))")
def wait(read,predicate):
    end=time.monotonic()+10
    while True:
        value=read()
        if predicate(value):return value
        assert time.monotonic()<end,value
        time.sleep(.025)
def check(case,passed,**data):
    rows.append(dict(case=case,passed=bool(passed),**data))
    (a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
    assert passed,rows[-1]
def browser_windows():return [w for w in control('windows') if w['pid']==launch['pids'][-1] and w['visible']]
def native_windows():return [w for w in control('windows') if w['pid']==launch['pids'][-2] and w['visible']]
def original():
    assert control('focus '+str(browser['id']))['ok']
    # Observed tab-strip position in this owned 900x700, scale-1 fixture.
    assert control('pointer 495 100')['ok'];assert control('button 272')['ok']
    js("document.body.tabIndex=0;document.body.focus();window.__menuKeys=[];for(let type of ['keydown','keyup'])document.addEventListener(type,e=>__menuKeys.push({type,key:e.key,trusted:e.isTrusted,prevented:e.defaultPrevented}));true")
    check('body-focus-outside-native-editors',js('document.activeElement===document.body'))
def new_tab(label,field=False):
    before=pages();start=len(logs());host_start=len(host_logs());key(20,56)
    after=wait(pages,lambda ps:len(ps)==len(before)+1)
    trace=wait(logs,lambda s:'app-menu-execute ' in s[start:])[start:]
    check(label+'-creates-one-tab',len(after)==len(before)+1)
    check(label+'-native-query-before-one-execution','execute=0 handled=1' in trace and trace.count('app-menu-execute ')==1 and trace.count('phase=1 enabled=1')==1,trace=trace)
    if field:
        events=host_logs()[host_start:]
        check(label+'-native-control-dispatches-menu',any(e['event']=='native-form-key' and e['kind']==1 and e['type']==0 and e['result']==1 for e in events),events=[e for e in events if e['event']=='native-form-key'])
    else:check(label+'-browser-unhandled-path-executes-menu',trace.count('execute=1 handled=1')==1)
    # Close the second tab with its actual tab-strip button. The address field
    # owns editing shortcuts, and the CDP client retains the original target.
    assert control('pointer 844 100')['ok']
    # Chromium animates insertion of a new tab. Retry its observed close
    # location until that target disappears; the empty strip at this location
    # contains no close button after the extra tab has gone.
    end=time.monotonic()+10
    while len(pages())!=len(before):
        assert time.monotonic()<end,pages()
        assert control('button 272 1')['ok']
        assert control('capture HEADLESS-1')['event']['event']=='frame'
        assert control('button 272 0')['ok']

launch=remote('from pathlib import Path\nprint((Path('+repr(a.fixture)+")/'launch.json').read_text())")
trace=wait(logs,lambda s:'app-menu-native ' in s)
check('global-key-adapter-installed','experimental native global menu keys enabled' in trace)
check('cold-start-model-without-menu-button','app-menu-browser-added ' in trace and trace.count('app-menu-native ')==1)
browser=next(w for w in control('windows') if w['pid']==launch['pids'][-1] and w['visible'])
menus=[w for w in control('windows') if w['pid']==launch['pids'][-2] and w['visible']]
check('cold-start-detached-gnustep-menu',len(menus)==1 and menus[0]['level']==20 and not menus[0]['accepts_focus'],windows=menus)
assert control(f"move {browser['id']} 350 80")['ok']
check('owned-browser-page',js('location.href')==launch['command'][-1])
try:
    original();new_tab('body')
    original();js("document.querySelector('#ordinary').focus();true")
    check('ordinary-button-focused',js("document.activeElement.id==='ordinary'"))
    new_tab('button',True)
    for label,focus in [('body','document.body'),('button',"document.querySelector('#ordinary')")]:
        original();js(focus+'.focus();true');before=pages();start=len(logs())
        js("window.__menuCancelled=false;document.addEventListener('keydown',function cancel(e){if(e.key==='t'&&e.altKey){e.preventDefault();__menuCancelled=e.defaultPrevented;document.removeEventListener('keydown',cancel,true)}},true);true")
        key(20,56)
        wait(lambda:js("__menuCancelled&&__menuKeys.some(e=>e.type==='keyup'&&e.key==='t')"),bool)
        trace=logs()[start:]
        check(label+'-web-prevent-default-preserves-tabs',{p['id'] for p in pages()}=={p['id'] for p in before})
        check(label+'-cancelled-key-performs-query-only','execute=0 handled=1' in trace and 'execute=1 handled=1' not in trace and 'app-menu-execute ' not in trace,trace=trace)
    original();before=pages();start=len(logs())
    js("document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'t',code:'KeyT',altKey:true,bubbles:true,cancelable:true}));true")
    check('synthetic-key-never-invokes-native-menu',{p['id'] for p in pages()}=={p['id'] for p in before} and 'app-menu-execute ' not in logs()[start:])
    original();start=len(logs());key(36)
    events=wait(lambda:js("__menuKeys.filter(e=>e.key==='j')"),lambda es:any(e['type']=='keyup' for e in es))
    check('unmatched-key-keeps-trusted-web-delivery',any(e['type']=='keydown' and e['trusted'] and not e['prevented'] for e in events),events=events)
    check('unmatched-key-never-invokes-native-menu','app-menu-execute ' not in logs()[start:])
    # Possessing a visible menu ID grants no authority on another connection.
    model=next(e for e in host_logs() if e['event']=='native-menu-model')
    forged=remote("import sys,json,socket\nfrom pathlib import Path\nsys.path.insert(0,'/workspace/Experiments/ChromiumScrollers')\nfrom native_controls import ControlInputRequest,MAGIC\nfrom helper import Response\nruntime=json.loads((Path("+repr(a.fixture)+")/'runtime.json').read_text())\nresults=[]\nwith socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:\n s.settimeout(8);s.connect(runtime['XDG_RUNTIME_DIR']+'/native.sock')\n for mode in [-1,1]:\n  req=ControlInputRequest(magic=MAGIC,operation=27,process="+str(model['process'])+",control="+str(model['control'])+",type=0,modifiers=2,text_size=1,unmodified_size=1,focused=mode)\n  s.send(bytes(req)+b'tt');reply=Response.from_buffer_copy(s.recv(128*1024));results.append(reply.parts[3].x)\nprint(json.dumps(results))")
    check('foreign-connection-cannot-query-or-execute-model',forged==[0,0],responses=forged)
    original();start=len(logs());key(49,56)
    windows=wait(browser_windows,lambda ws:len(ws)==2)
    second=next(w for w in windows if w['id']!=browser['id'])
    wait(logs,lambda s:s.count('app-menu-native ')==2)
    check('second-window-constructs-own-real-model',logs().count('app-menu-browser-added ')==2)
    check('second-window-selects-one-native-root',len(wait(native_windows,lambda ws:len(ws)==1))==1)
    assert control(f"move {second['id']} 900 80")['ok']
    original();wait(logs,lambda s:'app-menu-browser-selected id=1 active=1' in s[start:])
    check('first-window-focus-restores-native-root',len(native_windows())==1)
    new_tab('first-window-after-focus')
    start=len(logs());assert control('focus '+str(second['id']))['ok']
    wait(logs,lambda s:'app-menu-browser-selected id=2 active=1' in s[start:])
    check('second-window-focus-restores-native-root',len(native_windows())==1)
    assert control('close '+str(second['id']))['ok']
    wait(browser_windows,lambda ws:len(ws)==1)
    wait(logs,lambda s:'app-menu-browser-removed id=2' in s)
    check('closed-window-retires-menu-owner',len(browser_windows())==1)
    original();wait(native_windows,lambda ws:len(ws)==1)
    check('browser-still-live',len(pages())==1)
    print(json.dumps(dict(passed=len(rows))))
finally:
    control('key 56 0');control('key 29 0')
