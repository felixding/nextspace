#!/usr/bin/env python3
"""Qualify native model RPC against captured native references."""
import argparse,json,os,resource,select,socket,subprocess,sys,tempfile,time
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Wayland'))
from gnustep import private_defaults

p=argparse.ArgumentParser(description=__doc__)
for name in ['build','compositor','backend-bundle','reference','output']:p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--previous-provider',type=Path)
p.add_argument('--previous-group-provider',type=Path)
p.add_argument('--radio',action='store_true',help='Use the shared group model/input and member pixel transport')
a=p.parse_args();a.output.mkdir(parents=True);rows=[];children=[]
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
def check(case,passed,**data):
 rows.append(dict(case=case,passed=bool(passed),**data));(a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
def stop(child):
 if child.poll() is None:
  child.terminate()
  try:child.wait(timeout=5)
  except subprocess.TimeoutExpired:child.kill();child.wait()
with tempfile.TemporaryDirectory(prefix='nxs-tab-wire-') as temporary:
 runtime=Path(temporary)
 env=dict(os.environ,XDG_RUNTIME_DIR=temporary,WLR_BACKENDS='headless',WLR_RENDERER='pixman',GNUSTEP_CONFIG_FILE='/Library/Preferences/GNUstep.conf',LD_LIBRARY_PATH=':'.join([str(a.build/'native-ui'),str(a.build),'/Library/Libraries','/usr/NextSpace/lib']))
 for key in ['DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','LD_PRELOAD','NEXTSPACE_NATIVE_UI_PROVIDER']:env.pop(key,None)
 private_defaults(env,runtime);bundles=runtime/'empty-library/Bundles';bundles.mkdir(parents=True)
 (bundles/a.backend_bundle.name).symlink_to(a.backend_bundle.resolve(),target_is_directory=True)
 control,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);control.settimeout(5)
 server=subprocess.Popen([str(a.compositor),'-c',str(child.fileno())],pass_fds=[child.fileno()],env=env,stdout=subprocess.PIPE,stderr=(a.output/'compositor.stderr').open('w'),text=True);children.append(server);child.close()
 try:
  assert select.select([server.stdout],[],[],10)[0]
  line=server.stdout.readline().strip();assert line.startswith('WAYLAND_DISPLAY='),line
  env['WAYLAND_DISPLAY']=line.split('=',1)[1]
  variants=([('current-120',None,120),('current-240',None,240)] if a.radio else [('current',None,120)])+([('previous',a.previous_provider,120)] if a.previous_provider else [])+([('previous-group',a.previous_group_provider,120)] if a.previous_group_provider else [])
  for name,provider,density in variants:
   if a.radio:
    control.send(b'outputs');output=json.loads(control.recv(65536))[0]['name']
    control.send(f'test-scale {output} {density} 10000'.encode());assert json.loads(control.recv(65536))['ok']
    control.send(b'confirm');assert json.loads(control.recv(65536))['ok']
   out=a.output/name;out.mkdir();endpoint=runtime/(name+'.sock');local=dict(env)
   if provider:local['NEXTSPACE_NATIVE_UI_PROVIDER']=str(provider)
   helper=subprocess.Popen([sys.executable,str(Path(__file__).resolve().parents[2]/'Experiments/ChromiumScrollers/helper.py'),'--library',str(a.build/'libnextspace-native-scroller.so.1'),'--socket',str(endpoint),'-GSBackend','wayland','-GSTheme','NextSpace'],env=local,stdout=(out/'helper.jsonl').open('w'),stderr=(out/'helper.stderr').open('w'));children.append(helper)
   deadline=time.monotonic()+30
   while not endpoint.exists():
    assert helper.poll() is None,(helper.returncode,(out/'helper.stderr').read_text())
    assert time.monotonic()<deadline,'Native host readiness';time.sleep(.02)
   with (out/'probe.stdout').open('w') as stdout,(out/'probe.stderr').open('w') as stderr:
    arguments=([str(a.build/'native-ui/native-radio-transport-probe'),str(endpoint),str(out),str(density/120),*(['--expect-no-radio'] if provider else [])] if a.radio else [str(a.build/'native-ui/native-tab-transport-probe'),str(endpoint),str(out),*(['--expect-no-tabs'] if provider else [])])
    actor=subprocess.Popen(arguments,env=local,stdout=stdout,stderr=stderr);children.append(actor)
    try:code=actor.wait(timeout=45)
    except subprocess.TimeoutExpired:stop(actor);raise
   events=[json.loads(line) for line in (out/'probe.stdout').read_text().splitlines()]
   for event in events:
    if 'case' in event:check(name+'-'+event['case'],event['passed'])
    if event.get('event')=='image':
     if a.radio:source=a.reference/str(density)/(event['reference']+'-reference.png')
     else:
      case,render_density=event['name'].rsplit('-',1);source=a.reference/str(int(render_density)*120)/(case+'-reference.png')
     expected=Image.open(source).convert('RGB')
     if a.radio and event['member']:
      x,y,width,height=event['crop'];factor=density/120
      left,top=round(x*factor),round(y*factor);expected=expected.crop((left,top,left+event['width'],top+event['height']))
     actual=Image.frombytes('RGBA',(event['width'],event['height']),(out/(event['name']+'.argb')).read_bytes(),'raw','BGRA',event['stride']);actual.save(out/(event['name']+'.png'))
     check(name+'-transport-'+event['name']+'-whole-native-desktop-pixels',actual.size==expected.size and actual.convert('RGB').tobytes()==expected.tobytes() and actual.getchannel('A').getextrema()==(255,255),reference=str(source))
   check(name+'-C-transport-probe-exit',code==0,exit=code,stderr=(out/'probe.stderr').read_text())
   assert events[-1]['images']==(0 if provider else 17 if a.radio else 10)
   check(name+'-helper-survives',helper.poll() is None);stop(helper)
 finally:
  for child in reversed(children[1:]):stop(child)
  if server.poll() is None:
   try:control.send(b'quit');control.recv(65536);server.wait(timeout=5)
   except (OSError,subprocess.TimeoutExpired):stop(server)
  control.close();(a.output/'cleanup.json').write_text(json.dumps([dict(pid=c.pid,exit=c.returncode) for c in children],indent=2)+'\n')
print(json.dumps(dict(passed=len(rows),native_images=34 if a.radio else 10)))
