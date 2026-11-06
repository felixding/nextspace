#!/usr/bin/env python3
"""Check a native D-Bus File menu and owner loss in an owned Firefox fixture."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'FirefoxNativeUI'))
from marionette import Marionette
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--fixture',type=Path,required=True)
p.add_argument('--port',type=int,required=True)
p.add_argument('--expected-pid',type=int,required=True)
p.add_argument('--menu-host',type=Path,required=True,help='Final menu host launch metadata')
p.add_argument('--output',type=Path,required=True)
p.add_argument('--owner-loss',action='store_true',help='Terminate this verified owned browser while the native menu is held')
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);rows=[]
def check(case,passed,**data):
 rows.append(dict(case=case,passed=bool(passed),**data));(a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
def control(command):
 with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:
  s.settimeout(15);s.connect(str(a.fixture/'control.sock'));s.send(json.dumps(dict(command=command)).encode());return json.loads(s.recv(65536))
def wait(read,predicate):
 deadline=time.monotonic()+8
 while True:
  value=read()
  if predicate(value):return value
  assert time.monotonic()<deadline,value
  time.sleep(.02)
def native_states():
 path=host_output/'native-items.json'
 before=path.stat();stamp=(before.st_ino,before.st_mtime_ns)
 if host.get('shared_helper'):assert control('menu-broker '+json.dumps(dict(operation='snapshot')))['accepted']
 else:os.kill(host['pid'],signal.SIGUSR1)
 def refreshed():
  after=path.stat();return (after.st_ino,after.st_mtime_ns)!=stamp
 wait(refreshed,bool)
 return json.loads(path.read_text())
launch=json.loads((a.fixture/'launch.json').read_text());host=json.loads(a.menu_host.read_text())
assert a.expected_pid==launch['pids'][-1]
if host.get('shared_helper'):
 assert host['owner']==a.expected_pid
 host_output=Path(host['output'])
else:
 assert host['arguments'][host['arguments'].index('--owner')+1]==str(a.expected_pid)
 host_output=Path(host['arguments'][host['arguments'].index('--output')+1])
items=json.loads((host_output/'native-items.json').read_text());file=next(i for i in items if i['title']=='File')
layout=json.loads((host_output/'layout.json').read_text())['root'];file_model=next(c for c in layout[2] if c[1].get('label')=='File')
check('real-exported-first-command',file_model[2][0][1].get('label')=='New Tab')
root=next(w for w in control('windows') if w['pid']==host['pid'] and w['visible'])
check('native-detached-menu',root['level']==20 and not root['accepts_focus'],window=root)
frame=file['frame'];x=round(frame[0]+frame[2]/2);y=round(frame[1]+frame[3]/2)
def open_file():
 assert control(f'pointer {x} {y}')['ok'];assert control('button 272 1')['ok']
 return wait(lambda:control('popups'),bool)[0]
m=Marionette(a.port)
try:
 session=m.command('WebDriver:NewSession',{});check('owned-browser',session['capabilities']['moz:processID']==a.expected_pid)
 m.command('Marionette:SetContext',dict(value='chrome'))
 def state():return m.command('WebDriver:ExecuteScript',dict(script='return {tabs:gBrowser.tabs.length,native:document.getElementById("main-menubar").hasAttribute("native")}',args=[]))['value']
 before=state();check('browser-native-export-active',before['native'])
 # Begin on a fresh host with no held gesture. An outside release can dismiss
 # a native menu; do not inject an unrelated cancellation before this check.
 popup=open_file();check('native-submenu-mapped',popup['width']>0 and popup['height']>0,popup=popup)
 def new_tab_frame():
  values=native_states()
  return next(i['frame'] for i in values if i['title']=='New Tab')
 measured=wait(new_tab_frame,lambda f:f[2]>0 and f[3]>0)
 px=round(measured[0]+measured[2]/2);py=round(measured[1]+measured[3]/2)
 control(f'pointer {px} {py}')
 def highlighted():
  values=native_states()
  return next(i for i in values if i['title']=='New Tab')
 selected=wait(highlighted,lambda i:i['highlighted']==0)
 check('native-leaf-highlight-before-release',selected['highlighted']==0,state=selected)
 control('capture HEADLESS-1');control('button 272 0')
 after=wait(state,lambda s:s['tabs']==before['tabs']+1)
 check('native-command-creates-one-real-tab',after['tabs']==before['tabs']+1,before=before,after=after)
finally:m.close()
if a.owner_loss:
 popup=open_file();check('held-submenu-before-owner-exit',bool(popup))
 prefix=a.menu_host.with_name(a.menu_host.name.removesuffix('-host.json'))
 log=Path(host['log']) if host.get('shared_helper') else Path(str(prefix)+'.stdout')
 start=len(log.read_text());os.kill(a.expected_pid,signal.SIGTERM)
 wait(lambda:log.read_text()[start:],lambda t:'"event": "stopped"' in t and (host.get('shared_helper') or '"event": "owner-lost"' in t))
 wait(lambda:control('windows'),lambda ws:not any(w['pid']==host['pid'] for w in ws))
 control('button 272 0')
 check('owner-exit-removes-native-menu',not control('popups'))
 if host.get('shared_helper'):
  state=Path('/proc',str(host['pid']),'stat').read_text().split(') ',1)[1].split()[0]
  check('shared-host-survives-application-owner-exit',state not in ('Z','X'),pid=host['pid'])
 else:
  cleanup_path=Path(str(prefix)+'-cleanup.json')
  cleanup=wait(lambda:json.loads(cleanup_path.read_text()) if cleanup_path.exists() else None,bool)
  check('native-host-exits-cleanly',cleanup['exit']==0,cleanup=cleanup)
print(json.dumps(dict(passed=len(rows))))
