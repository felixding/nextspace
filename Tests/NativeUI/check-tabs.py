#!/usr/bin/env python3
"""Qualify native model controls against ordinary AppKit desktop references."""
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
p.add_argument('--probe',type=Path,help='Use a separately built native reference probe')
p.add_argument('--previous-group-provider',type=Path)
p.add_argument('--previous-scroll-provider',type=Path,help='List provider predating shared scroll geometry')
p.add_argument('--previous-item-hit-provider',type=Path,help='Provider predating optional native item hit queries')
p.add_argument('--previous-client',type=Path)
p.add_argument('--previous-loader',type=Path)
p.add_argument('--specialized',action='store_true',help='Qualify original native stepper/color/date controls')
p.add_argument('--date-panel',action='store_true',help='Qualify original native calendar-panel composition')
p.add_argument('--date-input',action='store_true',help='Measure original native date input and empty-state behavior')
p.add_argument('--gui-library-path',type=Path,help='Use a staged GNUstep GUI library for native component qualification')
p.add_argument('--base-library-path',type=Path,help='Use a staged Foundation library for native component qualification')
p.add_argument('--placeholder',action='store_true',help='Qualify original native field placeholders')
p.add_argument('--popup-title',action='store_true',help='Qualify popup display titles with the same desktop capture harness')
p.add_argument('--radio',action='store_true',help='Qualify shared native radio groups against ordinary matrices')
p.add_argument('--list',action='store_true',help='Qualify shared native lists against ordinary NSBrowser controls')
a=p.parse_args();a.output.mkdir(parents=True);rows=[];children=[]
binary='native-specialized-probe' if a.specialized else 'native-placeholder-probe' if a.placeholder else 'native-list-probe' if a.list else 'native-radio-probe' if a.radio else 'native-popup-title-probe' if a.popup_title else 'native-tab-probe'
if a.date_input:binary='native-date-input-probe'
if a.date_panel:binary='native-date-panel-probe'
reference_title='Native specialized reference ' if a.specialized else 'Native placeholder reference ' if a.placeholder else 'Native list reference ' if a.list else 'Native radio group reference ' if a.radio else 'Native popup title reference ' if a.popup_title else 'Native tab reference '
if a.date_input:reference_title='Native date input reference '
if a.date_panel:reference_title='Native date panel reference '
images=12 if a.specialized else 24 if a.placeholder else 13 if a.list else 13 if a.radio else 8 if a.popup_title else 5
if a.date_input:images=6
if a.date_panel:images=1
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
with tempfile.TemporaryDirectory(prefix='nxs-tabs-') as temporary:
 runtime=Path(temporary)
 env=dict(os.environ,XDG_RUNTIME_DIR=temporary,WLR_BACKENDS='headless',WLR_RENDERER='pixman',GNUSTEP_CONFIG_FILE='/Library/Preferences/GNUstep.conf',LD_LIBRARY_PATH=':'.join([str(a.build/'native-ui'),str(a.build),'/Library/Libraries','/usr/NextSpace/lib']))
 if a.base_library_path:env['LD_LIBRARY_PATH']=str(a.base_library_path)+':'+env['LD_LIBRARY_PATH']
 if a.gui_library_path:env['LD_LIBRARY_PATH']=str(a.gui_library_path)+':'+env['LD_LIBRARY_PATH']
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
    actor=subprocess.Popen([str(a.probe or a.build/'native-ui'/binary),str(out),str(scale/120),'-GSBackend','wayland','-GSTheme','NextSpace'],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,bufsize=0);children.append(actor)
    os.set_blocking(actor.stdout.fileno(),False);pending=b'';checks=[];deadline=time.monotonic()+60
    while actor.poll() is None or select.select([actor.stdout],[],[],0)[0]:
     assert time.monotonic()<deadline,'Native control probe deadline'
     if not select.select([actor.stdout],[],[],.1)[0]:continue
     data=os.read(actor.stdout.fileno(),65536)
     if not data:break
     stdout.write(data);stdout.flush();pending+=data
     while b'\n' in pending:
      line,pending=pending.split(b'\n',1);event=json.loads(line)
      if event.get('event')=='reference-ready':
       title=reference_title+event['name']
       window=until(lambda:next((w for w in command('windows') if w['pid']==actor.pid and w['title']==title and w['visible'] and w['focused']),None),'native reference activation')
       assert command(f"move {window['id']} 20 20")['ok']
       if a.list:assert command('pointer 600 340')['ok']
       actor.stdin.write(b'ready\n');actor.stdin.flush()
      elif event.get('event')=='reference-key-ready':
       window=until(lambda:next((w for w in command('windows') if w['pid']==actor.pid and w['title']==event['title'] and w['visible']),None),'native key reference')
       assert command(f"focus {window['id']}")['ok']
       try:
        if event['modifiers']&1:assert command('key 42 1')['ok']
        for down in (1,0):assert command(f"key {event['code']} {down}")['ok']
       finally:
        if event['modifiers']&1:assert command('key 42 0')['ok']
       actor.stdin.write(b'key-done\n');actor.stdin.flush()
      elif event.get('event')=='reference-pointer-ready':
       window=until(lambda:next((w for w in command('windows') if w['pid']==actor.pid and w['title']==event['title'] and w['visible']),None),'native pointer reference')
       assert command(f"focus {window['id']}")['ok']
       assert command(f"pointer {round(window['x']+event['x'])} {round(window['y']+event['y'])}")['ok']
       try:
        if event['modifiers']&1:assert command('key 42 1')['ok']
        assert command('button 272 1')['ok'];assert command('button 272 0')['ok']
       finally:
        if event['modifiers']&1:assert command('key 42 0')['ok']
       actor.stdin.write(b'pointer-done\n');actor.stdin.flush()
      elif event.get('event')=='reference':
       title=reference_title+event['name']
       def reference():
        return next((w for w in command('windows') if w['pid']==actor.pid and w['title']==title and w['visible'] and w['buffer_width']==event.get('window_pixel_width',event['pixel_width']) and w['buffer_height']==event.get('window_pixel_height',event['pixel_height'])),None)
       window=until(reference,'native reference backing at requested density')
       assert command(f"move {window['id']} 20 20")['ok'];window=reference()
       assert command('pointer 600 340')['ok']
       raw=out/(event['name']+'-desktop.raw');start=len(capture.events);capture.send('capture '+head+' '+str(raw));frame=capture.wait('frame',start)
       desktop=Image.frombytes('RGBA' if frame['format']==0 else 'RGB',(frame['width'],frame['height']),raw.read_bytes(),'raw','BGRA' if frame['format']==0 else 'BGRX',frame['stride'],-1 if frame['flags']&1 else 1).convert('RGB');raw.unlink()
       desktop.save(out/(event['name']+'-desktop.png'))
       (out/(event['name']+'-geometry.json')).write_text(json.dumps(dict(window=window,frame=frame,reference=event),indent=2)+'\n')
       left,top=round((window['x']+event.get('crop_x',0))*scale/120),round((window['y']+event.get('crop_y',0))*scale/120)
       expected=desktop.crop((left,top,left+event['pixel_width'],top+event['pixel_height']));expected.save(out/(event['name']+'-reference.png'))
       actual=Image.frombytes('RGBA',(event['pixel_width'],event['pixel_height']),(out/(event['name']+'-native.argb')).read_bytes(),'raw','BGRA',event['stride']);actual.save(out/(event['name']+'-native.png'))
       row=dict(case=event['name']+'-whole-desktop-native-pixels',passed=actual.convert('RGB').tobytes()==expected.tobytes() and actual.getchannel('A').getextrema()==(255,255),density=scale)
       rows.append(row);actor.stdin.write(b'captured\n');actor.stdin.flush()
      else:
       checks.append(event)
       if 'case' in event:rows.append(dict(event,density=scale))
      (a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
    code=actor.wait(timeout=5)
   (a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
   assert code==0,(code,(out/'probe.stdout').read_text()[-1500:],(out/'probe.stderr').read_text()[-2500:])
   assert checks[-1]['images']==images+(4 if a.radio and checks[-1].get('semantic_activation') else 0) and checks[-1]['api_bytes']>=480
   assert all(row['passed'] for row in rows),[row for row in rows if not row['passed']]
  if a.previous_provider:
   old=dict(env,NEXTSPACE_NATIVE_UI_PROVIDER=str(a.previous_provider))
   with (a.output/'previous-provider.stdout').open('w') as stdout,(a.output/'previous-provider.stderr').open('w') as stderr:
    actor=subprocess.Popen([str(a.build/'native-ui'/binary),'--expect-no-specialized' if a.specialized else '--expect-no-placeholder' if a.placeholder else '--expect-no-list' if a.list else '--expect-no-radio' if a.radio else '--expect-no-popup-title' if a.popup_title else '--expect-no-tabs','-GSBackend','wayland'],env=old,stdout=stdout,stderr=stderr);children.append(actor)
    try:code=actor.wait(timeout=15)
    except subprocess.TimeoutExpired:actor.kill();actor.wait();raise
   rows.append(dict(case='previous-provider-without-'+('specialized' if a.specialized else 'placeholders' if a.placeholder else 'lists' if a.list else 'radio-groups' if a.radio else 'popup-title' if a.popup_title else 'tabs'),passed=code==0))
   (a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert code==0
  if a.previous_group_provider:
   assert a.radio
   old=dict(env,NEXTSPACE_NATIVE_UI_PROVIDER=str(a.previous_group_provider))
   with (a.output/'previous-group-provider.stdout').open('w') as stdout,(a.output/'previous-group-provider.stderr').open('w') as stderr:
    actor=subprocess.Popen([str(a.build/'native-ui'/binary),'--expect-no-radio-size','-GSBackend','wayland'],env=old,stdout=stdout,stderr=stderr);children.append(actor)
    try:code=actor.wait(timeout=15)
    except subprocess.TimeoutExpired:actor.kill();actor.wait();raise
   rows.append(dict(case='previous-group-provider-without-cell-size',passed=code==0))
   (a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert code==0
  if a.previous_scroll_provider:
   assert a.list
   old=dict(env,NEXTSPACE_NATIVE_UI_PROVIDER=str(a.previous_scroll_provider))
   with (a.output/'previous-scroll-provider.stdout').open('w') as stdout,(a.output/'previous-scroll-provider.stderr').open('w') as stderr:
    actor=subprocess.Popen([str(a.build/'native-ui'/binary),'--expect-no-scroll','-GSBackend','wayland'],env=old,stdout=stdout,stderr=stderr);children.append(actor)
    try:code=actor.wait(timeout=15)
    except subprocess.TimeoutExpired:actor.kill();actor.wait();raise
   rows.append(dict(case='previous-list-provider-without-scroll-geometry',passed=code==0))
   (a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert code==0
  if a.previous_item_hit_provider:
   assert a.list
   old=dict(env,NEXTSPACE_NATIVE_UI_PROVIDER=str(a.previous_item_hit_provider))
   with (a.output/'previous-item-hit-provider.stdout').open('w') as stdout,(a.output/'previous-item-hit-provider.stderr').open('w') as stderr:
    actor=subprocess.Popen([str(a.build/'native-ui'/binary),'--expect-no-item-hit','-GSBackend','wayland'],env=old,stdout=stdout,stderr=stderr);children.append(actor)
    try:code=actor.wait(timeout=15)
    except subprocess.TimeoutExpired:actor.kill();actor.wait();raise
   rows.append(dict(case='previous-provider-without-item-hits',passed=code==0))
   (a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert code==0
  if a.previous_client:
   for name,library in [('previous-client',a.build/'native-ui')]+([('previous-loader-and-client',a.previous_loader)] if a.previous_loader else []):
    out=a.output/name;out.mkdir()
    old=dict(env,LD_LIBRARY_PATH=str(library)+':/Library/Libraries:/usr/NextSpace/lib',NEXTSPACE_NATIVE_UI_PROVIDER=str((a.build/'native-ui/libnextspace-native-ui-gnustep.so.1').resolve()))
    with (out/'stdout').open('w') as stdout,(out/'stderr').open('w') as stderr:
     actor=subprocess.Popen([str(a.previous_client),str(out),'-GSBackend','wayland','-GSTheme','NextSpace'],env=old,stdout=stdout,stderr=stderr);children.append(actor)
     try:code=actor.wait(timeout=20)
     except subprocess.TimeoutExpired:actor.kill();actor.wait();raise
    rows.append(dict(case=name+'-with-new-provider',passed=code==0 and sum(line.startswith('{') for line in (out/'stdout').read_text().splitlines())==(1 if a.popup_title else 5)))
    (a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert rows[-1]['passed'],(name,code,(out/'stderr').read_text())
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
print(json.dumps(dict(passed=len(rows),native_images=sum("whole-desktop-native-pixels" in row["case"] for row in rows))))
