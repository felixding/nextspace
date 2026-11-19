#!/usr/bin/env python3
"""Exercise legacy focus and opt-in activation fallback on a private compositor."""
import argparse,json,os,select,socket,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True);rows=[];children=[]
with tempfile.TemporaryDirectory(prefix='nxs-activation-') as runtime:
 env=dict(os.environ,XDG_RUNTIME_DIR=runtime,WLR_BACKENDS='headless',WLR_RENDERER='pixman')
 for key in ['DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','LD_PRELOAD']:env.pop(key,None)
 parent,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);parent.settimeout(5)
 comp=subprocess.Popen([str(a.build/'nextspace-compositor'),'-c',str(child.fileno())],pass_fds=[child.fileno()],env=env,stdout=subprocess.PIPE,stderr=(a.output/'compositor.stderr').open('w'),text=True);children.append(comp);child.close()
 try:
  assert select.select([comp.stdout],[],[],10)[0]
  line=comp.stdout.readline();assert line.startswith('WAYLAND_DISPLAY='),line
  env['WAYLAND_DISPLAY']=line.strip().split('=',1)[1]
  for mode in ['--no-focus','--activation','--activation-fallback','--activation-order','--activation-closed-popup']:
   actor=subprocess.Popen([str(a.build/'registry-probe'),mode],env=env,stdin=subprocess.PIPE if mode in ('--activation-order','--activation-closed-popup') else None,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);children.append(actor)
   initial=''
   if mode=='--activation-order':
    for expected in ['activation-order-map-input-ready','activation-order-input-ready']:
     assert select.select([actor.stdout],[],[],15)[0], 'Activation ordering probe startup'
     line=actor.stdout.readline();initial+=line
     if line.strip()!=expected:break
     for state in (1,0):
      parent.send(('key 30 '+str(state)).encode());assert json.loads(parent.recv(65536))['ok']
     actor.stdin.write('\n');actor.stdin.flush()
   if mode=='--activation-closed-popup':
    assert select.select([actor.stdout],[],[],15)[0], 'Closed popup activation startup'
    line=actor.stdout.readline();initial+=line
    assert line.strip()=='activation-popup-input-ready',line
    parent.send(b'popups');popups=json.loads(parent.recv(65536));assert len(popups)==1,popups
    popup=popups[0]
    parent.send(('pointer %d %d'%(popup['x']+8,popup['y']+8)).encode());assert json.loads(parent.recv(65536))['ok']
    for state in (1,0):
     parent.send(('key 30 '+str(state)).encode());assert json.loads(parent.recv(65536))['ok']
    actor.stdin.write('\n');actor.stdin.flush()
   try:stdout,stderr=actor.communicate(timeout=20)
   except subprocess.TimeoutExpired:actor.kill();stdout,stderr=actor.communicate();raise
   stdout=initial+stdout
   (a.output/(mode[2:]+'.stdout')).write_text(stdout);(a.output/(mode[2:]+'.stderr')).write_text(stderr)
   row=dict(case=mode[2:],passed=actor.returncode==0,pid=actor.pid,exit=actor.returncode,stdout=stdout)
   rows.append(row);(a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert row['passed'],row
 finally:
  if comp.poll() is None:
   try:parent.send(b'quit');parent.recv(65536)
   except (OSError,ConnectionError):pass
   try:comp.wait(timeout=5)
   except subprocess.TimeoutExpired:comp.kill();comp.wait()
  parent.close()
  (a.output/'cleanup.json').write_text(json.dumps([dict(pid=child.pid,exit=child.returncode) for child in children],indent=2)+'\n')
print(json.dumps(dict(passed=len(rows))))
