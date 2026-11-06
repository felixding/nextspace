#!/usr/bin/env python3
"""Compare legacy GTK decoration negotiation with the existing xdg frame."""
import argparse,json,os,select,socket,subprocess,tempfile
from pathlib import Path
from PIL import Image,ImageChops
from integration import until
from text_input import Client

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--build',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True);captures=a.output/'frames';captures.mkdir()
rows=[];clients=[];server=None
def check(case,passed,**evidence):
 rows.append(dict(case=case,passed=bool(passed),**evidence))
 (a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
with tempfile.TemporaryDirectory(prefix='nxs-legacy-frame-') as runtime:
 env=dict(os.environ,XDG_RUNTIME_DIR=runtime,WLR_BACKENDS='headless',WLR_RENDERER='pixman',NEXTSPACE_COMPOSITOR_CAPTURE_DIR=str(captures.resolve()))
 for k in ['DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','LD_PRELOAD']:env.pop(k,None)
 control,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);control.settimeout(5)
 server=subprocess.Popen([str(a.build/'nextspace-compositor'),'-c',str(child.fileno())],pass_fds=[child.fileno()],env=env,stdout=subprocess.PIPE,stderr=(a.output/'compositor.stderr').open('w'),text=True);child.close()
 def command(text):
  control.send(text.encode());return json.loads(control.recv(65536))
 def window(client):
  return next((w for w in command('windows') if w['pid']==client.process.pid),None)
 def state(client,enabled,request='initial'):
  value=until(lambda: window(client) if window(client) and window(client)['server_decorated']==enabled else None,'decoration mode follows committed surface')
  check(client.label+'-'+request,value['server_decorated']==enabled,window=value)
  return value
 def title(client):
  w=window(client);path=captures/f"frame-{w['id']}-120.png"
  def ready():
   try:
    with Image.open(path) as image:
     return image.convert('RGB') if image.size==(w['frame_width'],w['frame_top']) else None
   except (OSError,SyntaxError):return None
  return until(ready,'complete title rendering')
 try:
  assert select.select([server.stdout],[],[],10)[0]
  line=server.stdout.readline().strip();assert line.startswith('WAYLAND_DISPLAY='),line
  env['WAYLAND_DISPLAY']=line.split('=',1)[1]
  reference=Client(str(a.build/'decoration-probe'),'',env,a.output,'xdg',ready_event=None);reference.label='xdg';clients.append(reference);reference.wait('configure')
  state(reference,True);expected=title(reference);expected.save(a.output/'xdg-reference.png')
  for mode in ['--legacy','--legacy-early']:
   client=Client(str(a.build/'decoration-probe'),mode,env,a.output,mode[2:],ready_event=None);client.label=mode[2:];clients.append(client);client.wait('configure')
   state(client,True)
   actual=title(client);actual.save(a.output/(client.label+'-title.png'))
   check(client.label+'-whole-title-equals-xdg',actual.size==expected.size and ImageChops.difference(actual,expected).getbbox() is None)
   for request,enabled in [('legacy-mode 1',False),('legacy-mode 0',False),('legacy-mode 2',True),('legacy-destroy',False),('legacy-create',True),('legacy-destroy',False)]:
    client.send(request);client.sync();state(client,enabled,request)
   client.stop()
  client=Client(str(a.build/'decoration-probe'),'--legacy-dual',env,a.output,'dual',ready_event=None);client.label='dual';clients.append(client);client.wait('configure')
  state(client,True)
  for request,enabled in [('legacy-mode 0',True),('legacy-mode 2',True),('mode 1',False),('mode 2',True),('legacy-mode 1',True),('destroy',False),('legacy-mode 2',True)]:
   client.send(request);client.sync();state(client,enabled,request)
  print(json.dumps(dict(passed=len(rows))),flush=True)
 except BaseException:
  if server.poll() is None:(a.output/'failure-windows.json').write_text(json.dumps(command('windows'),indent=2)+'\n')
  raise
 finally:
  for client in reversed(clients):
   if client.process.poll() is None:client.stop()
  if server.poll() is None:
   try:command('quit')
   except (OSError,ConnectionError):pass
   try:server.wait(timeout=5)
   except subprocess.TimeoutExpired:server.kill();server.wait()
  control.close()
  (a.output/'cleanup.json').write_text(json.dumps([dict(pid=server.pid,exit=server.returncode)]+[dict(pid=c.process.pid,exit=c.process.returncode) for c in clients],indent=2)+'\n')
