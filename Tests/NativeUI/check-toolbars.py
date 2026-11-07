#!/usr/bin/env python3
"""Qualify the native toolbar contract against ordinary AppKit toolbars on Wayland."""
import argparse,json,os,resource,select,socket,subprocess,sys,tempfile,time
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Wayland'))
from gnustep import private_defaults
from integration import until
from text_input import Client

p=argparse.ArgumentParser(description=__doc__)
for name in ['build','compositor','capture-probe','backend-bundle','output']:p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--previous-provider',type=Path)
a=p.parse_args();a.output.mkdir(parents=True);rows=[];children=[]
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
with tempfile.TemporaryDirectory(prefix='nxs-toolbar-') as temporary:
 runtime=Path(temporary)
 env=dict(os.environ,XDG_RUNTIME_DIR=temporary,WLR_BACKENDS='headless',WLR_RENDERER='pixman',GNUSTEP_CONFIG_FILE='/Library/Preferences/GNUstep.conf',LD_LIBRARY_PATH=':'.join([str(a.build/'native-ui'),str(a.build),'/Library/Libraries','/usr/NextSpace/lib']))
 for key in ['DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','LD_PRELOAD','NEXTSPACE_NATIVE_UI_PROVIDER']:env.pop(key,None)
 private_defaults(env,runtime);bundles=runtime/'empty-library/Bundles';bundles.mkdir(parents=True)
 (bundles/a.backend_bundle.name).symlink_to(a.backend_bundle.resolve(),target_is_directory=True)
 control,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);control.settimeout(5)
 broker,peer=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
 server=subprocess.Popen([str(a.compositor),'-c',str(child.fileno()),'-S',str(peer.fileno())],pass_fds=[child.fileno(),peer.fileno()],env=env,stdout=subprocess.PIPE,stderr=(a.output/'compositor.stderr').open('w'),text=True);children.append(server);child.close();peer.close();capture=None
 def command(text):
  control.send(text.encode());return json.loads(control.recv(65536))
 try:
  assert select.select([server.stdout],[],[],10)[0]
  line=server.stdout.readline().strip();assert line.startswith('WAYLAND_DISPLAY='),line
  env['WAYLAND_DISPLAY']=line.split('=',1)[1];head=command('outputs')[0]['name']
  capture=Client(str(a.capture_probe),None,env,a.output,'capture',broker,b'V');children.append(capture.process)
  assert capture.events[0]['manager_visible']
  for scale in [120,240]:
   assert command(f'test-scale {head} {scale} 10000')['ok'];assert command('confirm')['ok']
   out=a.output/str(scale);out.mkdir()
   with (out/'probe.stdout').open('wb') as stdout,(out/'probe.stderr').open('w') as stderr:
    actor=subprocess.Popen([str(a.build/'native-ui/native-toolbar-probe'),str(out),str(scale/120),'-GSBackend','wayland','-GSTheme','NextSpace'],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,bufsize=0);children.append(actor)
    os.set_blocking(actor.stdout.fileno(),False);pending=b'';checks=[];deadline=time.monotonic()+60
    while actor.poll() is None or select.select([actor.stdout],[],[],0)[0]:
     assert time.monotonic()<deadline,'Native toolbar probe deadline'
     if not select.select([actor.stdout],[],[],.1)[0]:continue
     data=os.read(actor.stdout.fileno(),65536)
     if not data:break
     stdout.write(data);stdout.flush();pending+=data
     while b'\n' in pending:
      line,pending=pending.split(b'\n',1);event=json.loads(line)
      if event.get('event')=='reference':
       title='Native toolbar reference '+event['name']
       def reference():
        return next((w for w in command('windows') if w['pid']==actor.pid and w['title']==title and w['visible'] and w['buffer_width']==event['pixel_width'] and w['buffer_height']>=event['pixel_height']),None)
       window=until(reference,'native reference backing at requested density')
       assert command(f"move {window['id']} 20 20")['ok'];window=reference()
       assert command('pointer 600 340')['ok']
       raw=out/(event['name']+'-desktop.raw');start=len(capture.events);capture.send('capture '+head+' '+str(raw));frame=capture.wait('frame',start)
       desktop=Image.frombytes('RGBA' if frame['format']==0 else 'RGB',(frame['width'],frame['height']),raw.read_bytes(),'raw','BGRA' if frame['format']==0 else 'BGRX',frame['stride'],-1 if frame['flags']&1 else 1).convert('RGB');raw.unlink()
       desktop.save(out/(event['name']+'-desktop.png'))
       (out/(event['name']+'-geometry.json')).write_text(json.dumps(dict(window=window,frame=frame,reference=event),indent=2)+'\n')
       left,top=round((window['x']+event['reference_x'])*scale/120),round((window['y']+event['reference_y'])*scale/120)
       expected=desktop.crop((left,top,left+event['pixel_width'],top+event['pixel_height']));expected.save(out/(event['name']+'-reference.png'))
       actual=Image.frombytes('RGBA',(event['pixel_width'],event['pixel_height']),(out/(event['name']+'-native.argb')).read_bytes(),'raw','BGRA',event['stride']);actual.save(out/(event['name']+'-native.png'))
       row=dict(case=event['name']+'-whole-desktop-native-pixels',passed=actual.convert('RGB').tobytes()==expected.tobytes() and actual.getchannel('A').getextrema()==(255,255),density=scale)
       rows.append(row);actor.stdin.write(b'captured\n');actor.stdin.flush()
      elif event.get('event')=='overflow-menu':
       def menu_position():
        windows=command('windows')
        (out/'overflow-menu-windows.json').write_text(json.dumps(windows,indent=2)+'\n')
        return next((w for w in windows if w['pid']==event['pid'] and w['visible'] and w['level']==101 and
         w['x']==round(event['x']) and w['y']==round(event['y']) and w['width']==round(event['width']) and w['height']==round(event['height'])),None)
       menu=until(menu_position,'compositor/native overflow menu geometry agreement')
       rows.append(dict(case='overflow-menu-compositor-position',passed=True,density=scale,window=menu))
       raw=out/'overflow-menu.raw';start=len(capture.events);capture.send('capture '+head+' '+str(raw));frame=capture.wait('frame',start)
       desktop=Image.frombytes('RGBA' if frame['format']==0 else 'RGB',(frame['width'],frame['height']),raw.read_bytes(),'raw','BGRA' if frame['format']==0 else 'BGRX',frame['stride'],-1 if frame['flags']&1 else 1).convert('RGB');raw.unlink()
       desktop.save(out/'overflow-menu-desktop.png')
       left,top=round(event['x']*scale/120),round(event['y']*scale/120)
       desktop.crop((left,top,left+round(event['width']*scale/120),top+round(event['height']*scale/120))).save(out/'overflow-menu.png')
       (out/'overflow-menu-geometry.json').write_text(json.dumps(dict(event=event,windows=command('windows')),indent=2)+'\n')
       actor.stdin.write(b'captured\n');actor.stdin.flush()
      else:
       checks.append(event)
       if 'case' in event:rows.append(dict(event,density=scale))
      (a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
    code=actor.wait(timeout=5)
   (a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
   assert code==0,(code,(out/'probe.stdout').read_text()[-1500:],(out/'probe.stderr').read_text()[-2500:])
   assert checks[-1]['images']==4 and checks[-1]['api_bytes']>=480
   assert all(row['passed'] for row in rows),[row for row in rows if not row['passed']]
  if a.previous_provider:
   old=dict(env,NEXTSPACE_NATIVE_UI_PROVIDER=str(a.previous_provider))
   with (a.output/'previous-provider.stdout').open('w') as stdout,(a.output/'previous-provider.stderr').open('w') as stderr:
    actor=subprocess.Popen([str(a.build/'native-ui/native-toolbar-probe'),'--expect-no-toolbar','-GSBackend','wayland'],env=old,stdout=stdout,stderr=stderr);children.append(actor)
    try:code=actor.wait(timeout=15)
    except subprocess.TimeoutExpired:actor.kill();actor.wait();raise
   rows.append(dict(case='previous-provider-without-toolbar',passed=code==0))
   (a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert code==0
 finally:
  if capture:capture.stop()
  for actor in children[2:]:
   if actor.poll() is None:actor.terminate();actor.wait(timeout=5)
  if server.poll() is None:
   try:command('quit')
   except (OSError,ConnectionError):pass
   try:server.wait(timeout=5)
   except subprocess.TimeoutExpired:server.kill();server.wait()
  control.close();broker.close()
  (a.output/'cleanup.json').write_text(json.dumps([dict(pid=c.pid,exit=c.returncode) for c in children],indent=2)+'\n')
print(json.dumps(dict(passed=len(rows),native_images=8)))
