#!/usr/bin/env python3
"""Check an owned Chromium in native_ui_session.py --hold using real seat keys."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import time

p=argparse.ArgumentParser(description=__doc__)
for name in ['ssh-config','fixture','output','session']:p.add_argument('--'+name,required=True)
p.add_argument('--cdp',required=True);p.add_argument('--guest-cdp',type=int,required=True)
p.add_argument('--browser-pid',type=int,required=True);p.add_argument('--hook-log',required=True)
a=p.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True);rows=[]
ssh=['ssh','-F',a.ssh_config,'lima-nextspace-gui'];browser=['agent-browser','--session',a.session,'--cdp',a.cdp]
def remote(code):return json.loads(subprocess.check_output(ssh+[shlex.join(['python3','-c',code])],text=True))
def control(operation,**values):
    request=dict(operation=operation,**values)
    return remote('import socket,json\nwith socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:\n s.settimeout(10);s.connect('+repr(a.fixture+'/control.sock')+');s.send('+repr(json.dumps(request).encode())+');print(s.recv(65536).decode())')
def ab(*command):return subprocess.check_output(browser+list(command),text=True)
def js(code):return json.loads(ab('eval',code))
def wait(read,predicate,timeout=15):
    end=time.monotonic()+timeout
    while True:
        value=read()
        if predicate(value):return value
        assert time.monotonic()<end,value
        time.sleep(.02)
def check(case,passed,**data):
    rows.append(dict(case=case,passed=bool(passed),**data));(out/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
def read_file(name):return remote('import json;from pathlib import Path;print(json.dumps(Path('+repr(a.fixture+'/'+name)+').read_text()))')
def pages():return remote('import json,urllib.request;print(json.dumps([v for v in json.load(urllib.request.urlopen('+repr('http://127.0.0.1:'+str(a.guest_cdp)+'/json/list')+")) if v['type']=='page']))")
# Use the fixture's actual XKB map. These are input event modifiers, not a
# substitute for GNUstep's interpretation or an application shortcut table.
masks=remote('''import ctypes as C,json
from pathlib import Path
x=C.CDLL('libxkbcommon.so.0')
x.xkb_context_new.argtypes=[C.c_int];x.xkb_context_new.restype=C.c_void_p
x.xkb_keymap_new_from_string.argtypes=[C.c_void_p,C.c_char_p,C.c_int,C.c_int];x.xkb_keymap_new_from_string.restype=C.c_void_p
x.xkb_keymap_mod_get_index.argtypes=[C.c_void_p,C.c_char_p];x.xkb_keymap_mod_get_index.restype=C.c_uint
context=x.xkb_context_new(0);keymap=x.xkb_keymap_new_from_string(context,Path('''+repr(a.fixture+'/keymap.xkb')+''').read_bytes(),1,0);assert keymap
print(json.dumps({name:1<<x.xkb_keymap_mod_get_index(keymap,label) for name,label in [('control',b'Control'),('alt',b'Mod1'),('shift',b'Shift')]}))''')
def key(code,modifier=None):
    mask=masks[modifier] if modifier else 0
    assert control('keyboard',text=f'forward-modifiers {mask} 0 0 0\nforward {code} 1\nforward {code} 0\nforward-modifiers 0 0 0 0\nsync')['ok']
def field_state(identifier):return js('(()=>{let e=document.getElementById('+json.dumps(identifier)+');return {value:e.value,start:e.selectionStart,end:e.selectionEnd}})()')
def fields(label):
    for identifier in ['normal','password']:
        js('(()=>{let e=document.getElementById('+json.dumps(identifier)+");e.focus();e.value='Alpha beta';e.setSelectionRange(3,3);return true})()")
        # Complete the native paint/model synchronization before the key;
        # do not introduce a concurrent native pointer-tracking transaction.
        ab('screenshot',str(out/(label+'-'+identifier+'.png')))
        key(30,'control');state=wait(lambda:field_state(identifier),lambda s:s['start']==s['end']==0)
        check(label+'-'+identifier+'-native-emacs',state==dict(value='Alpha beta',start=0,end=0),state=state)
        key(44,'shift');state=wait(lambda:field_state(identifier),lambda s:s['value']=='ZAlpha beta')
        check(label+'-'+identifier+'-native-transaction',state==dict(value='ZAlpha beta',start=1,end=1),state=state)
        js('document.getElementById('+json.dumps(identifier)+").addEventListener('beforeinput',e=>e.preventDefault(),{once:true});true")
        key(16,'shift');state=field_state(identifier)
        check(label+'-'+identifier+'-cancellation-retained',state==dict(value='ZAlpha beta',start=1,end=1),state=state)
    js('document.body.tabIndex=0;document.body.focus();true')
def menu(label):
    before=pages();start=len(read_file(a.hook_log));key(20,'alt')
    after=wait(pages,lambda v:len(v)==len(before)+1)
    trace=wait(lambda:read_file(a.hook_log)[start:],lambda s:'app-menu-execute ' in s)
    check(label+'-one-native-menu-action',trace.count('app-menu-execute ')==1,trace=trace)
    original=next(v['id'] for v in before if '/test-text.html' in v['url'])
    # The new-tab page can replace its initial target during startup. Keep
    # these owned test tabs for the fixture's complete session teardown and
    # return to the observed, stable original page.
    ab('tab','list','--json');ab('tab',original)
    js('document.body.tabIndex=0;document.body.focus();true')
def views():
    lines=[line for line in read_file(a.hook_log).splitlines() if line.startswith('views-state ')]
    if not lines:return None
    row=dict(v.split('=',1) for v in lines[-1].split()[1:])
    return dict(value=bytes.fromhex(row['value_hex']).decode(),start=int(row['start']),end=int(row['end']),focused=int(row['focused']))
def address(label):
    key(38,'control');wait(views,lambda v:v and v['focused'])
    key(102);key(107,'shift');key(14);wait(views,lambda v:v and v['value']=='')
    prefix=''
    codes={'a':30,'l':38,'p':25,'h':35,' ':57,'b':48,'e':18,'t':20}
    for character in 'Alpha beta':
        key(codes[character.lower()],'shift' if character.isupper() else None);prefix+=character
        wait(views,lambda v:v and v['value']==prefix)
    key(102)
    for _ in range(3):key(106)
    wait(views,lambda v:v and v['start']==v['end']==3)
    key(30,'control');state=wait(views,lambda v:v and v['start']==v['end']==0)
    check(label+'-native-address-emacs',state==dict(value='Alpha beta',start=0,end=0,focused=1),state=state)
    key(44,'shift');state=wait(views,lambda v:v and v['value']=='ZAlpha beta')
    check(label+'-native-address-edit',state==dict(value='ZAlpha beta',start=1,end=1,focused=1),state=state)
    key(1) # Close any address suggestions through Chromium's own Escape path.
try:
    status=control('status');host=status['host'];shell=status['shell'];session=status['session']
    command=remote("import json;from pathlib import Path;print(json.dumps(Path('/proc/"+str(a.browser_pid)+"/cmdline').read_bytes().replace(b'\\0',b' ').decode()))")
    check('owned-unchanged-browser',('--remote-debugging-port='+str(a.guest_cdp)) in command and 'chromium-recovery-normalized' in command)
    sandbox=remote('''import json
from pathlib import Path
root='''+str(a.browser_pid)+'''
pending=[root];seen=set();rows=[]
while pending:
 pid=pending.pop()
 if pid in seen:continue
 seen.add(pid)
 try:
  proc=Path('/proc',str(pid))
  pending.extend(map(int,(proc/'task'/str(pid)/'children').read_text().split()))
  command=(proc/'cmdline').read_bytes().replace(b'\\0',b' ').decode()
  if '--type=renderer' in command:
   state=dict(line.split(':',1) for line in (proc/'status').read_text().splitlines() if ':' in line)
   rows.append(dict(pid=pid,seccomp=state['Seccomp'].strip(),no_new_privs=state['NoNewPrivs'].strip()))
 except FileNotFoundError:pass
print(json.dumps(rows))''')
    check('chromium-renderer-sandbox-retained',bool(sandbox) and all(v['seccomp']=='2' and v['no_new_privs']=='1' for v in sandbox),processes=sandbox)
    window=next(w for w in status['windows'] if w['pid']==a.browser_pid and w['level']==0)
    control('shell',text='activate '+str(window['id']))
    wait(lambda:control('status'),lambda s:any(w['pid']==a.browser_pid and w['flags']&1 for w in s['windows']))
    original=next(v['id'] for v in pages() if '/test-text.html' in v['url'])
    ab('tab','list','--json');ab('tab',original)
    js('window.__recoveryFrame=normal;true');fields('before-host-loss');menu('before-host-loss');address('before-host-loss')
    status=control('status');check('cold-browser-does-not-restart-host',status['host']==host)
    control('restart-host')
    replacement=wait(lambda:control('status'),lambda s:s['host'] and s['host']!=host and any(w['pid']==s['host'] and w['level']==20 and not w['flags']&(2|32) for w in s['windows']),30)
    check('host-replacement-keeps-browser-and-workspace',replacement['shell']==shell and replacement['session']==session and any(w['pid']==a.browser_pid for w in replacement['windows']))
    check('same-live-page-after-host-loss',js("window.__recoveryFrame===normal && normal.value==='ZAlpha beta' && password.value==='ZAlpha beta'"))
    # Restore browser WebView focus through its existing tab activation, then
    # use actual seat keys for the native editor and application menu checks.
    original=next(v['id'] for v in pages() if '/test-text.html' in v['url']);ab('tab',original)
    fields('after-host-loss');menu('after-host-loss');address('after-host-loss')
    verified=control('verify-firefox')
    check('firefox-menu-and-fields-survive-chromium-host-loss',verified.get('ok') and verified.get('passed')==10)
    control('shell',text='activate '+str(window['id']))
    wait(lambda:control('status'),lambda s:any(w['pid']==a.browser_pid and w['flags']&1 for w in s['windows']))
    menu('after-firefox-switch')
    check('no-extra-host-restart',control('status')['host']==replacement['host'])
    snapshot=control('status');visible=[w for w in snapshot['windows'] if w['pid']==snapshot['host'] and w['level']==20 and not w['flags']&(2|32)]
    check('one-visible-native-menu',len(visible)==1,windows=visible)
    (out/'status.json').write_text(json.dumps(snapshot,indent=2)+'\n')
finally:
    ab('close')
print(json.dumps(dict(passed=len(rows))))
