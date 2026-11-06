#!/usr/bin/env python3
"""Compare detached application menus with direct GNUstep menus on private Wayland."""
import argparse,json,os,select,socket,subprocess,sys,tempfile,time,uuid
from pathlib import Path
from contextlib import ExitStack
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Wayland'))
from text_input import Client
from gnustep import pasteboard_storage
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
p.add_argument('--capture-probe',type=Path,required=True);p.add_argument('--backend',required=True)
p.add_argument('--compositor',default='/usr/NextSpace/bin/nextspace-compositor');a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=True);rows=[];processes=[]
def check(case,passed,**data):
 rows.append(dict(case=case,passed=bool(passed),**data));(a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
def stop(process):
 if process.poll() is None:
  process.terminate()
  try:process.wait(timeout=5)
  except subprocess.TimeoutExpired:process.kill();process.wait()
def until(read,predicate):
 deadline=time.monotonic()+5
 while True:
  value=read()
  if predicate(value):return value
  assert time.monotonic()<deadline,value
  time.sleep(.01)
with tempfile.TemporaryDirectory(prefix='nxs-menu-') as runtime:
 env=dict(os.environ,XDG_RUNTIME_DIR=runtime,WLR_BACKENDS='headless',WLR_RENDERER='pixman',NEXTSPACE_SESSION_ID='native-menu-'+uuid.uuid4().hex)
 for key in ['DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','LD_PRELOAD','NEXTSPACE_NATIVE_UI_PROVIDER']:env.pop(key,None)
 parent,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);parent.settimeout(10)
 broker,peer=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
 compositor=subprocess.Popen([a.compositor,'-c',str(child.fileno()),'-S',str(peer.fileno())],pass_fds=[child.fileno(),peer.fileno()],env=env,stdout=subprocess.PIPE,stderr=(a.output/'compositor.log').open('w'),text=True);processes.append(compositor);child.close();peer.close();capture=None;probe=None;services=ExitStack()
 def command(text):parent.sendall(text.encode());return json.loads(parent.recv(65536))
 try:
  assert select.select([compositor.stdout],[],[],10)[0]
  env['WAYLAND_DISPLAY']=compositor.stdout.readline().strip().split('=',1)[1]
  services.enter_context(pasteboard_storage(Path('/Library/bin/gpbs-wayland'),a.build/'native-ui/native-pasteboard-probe',env,a.output))
  capture=Client(str(a.capture_probe),None,env,a.output,'capture',broker,b'V');processes.append(capture.process)
  assert capture.events[0]['manager_visible']
  snapshots={};item_offset=None
  for mode in ['provider','reference']:
   out=a.output/mode;out.mkdir(exist_ok=True)
   probe=subprocess.Popen([str(a.build/'native-ui/native-menu-probe'),'--hold' if mode=='provider' else '--reference','-GSBackend',a.backend],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(out/'stderr').open('w'),text=True,bufsize=1);processes.append(probe)
   def read():
    assert select.select([probe.stdout],[],[],10)[0],'native probe output timed out'
    line=probe.stdout.readline();assert line,(mode,probe.poll(),(out/'stderr').read_text());return json.loads(line)
   def request(text):probe.stdin.write(text+'\n');probe.stdin.flush();return read()
   ready=read();check(mode+'-startup',ready['event']==('menu-live' if mode=='provider' else 'reference-live'))
   def windows():return [w for w in command('windows') if w['pid']==probe.pid and w['visible'] and w['presented'] and w['buffer_width']>0]
   live=until(windows,lambda w:len(w)==1);root=live[0];(out/'root-window.json').write_text(json.dumps(root,indent=2)+'\n')
   assert command(f"raise {root['id']}")['ok'] and command(f"focus {root['id']}")['ok']
   def image(label):
    assert command('pointer 1200 500')['ok']
    head=command('outputs')[0];path=out/(label+'.raw');start=len(capture.events);capture.send('capture '+head['name']+' '+str(path));frame=capture.wait('frame',start)
    im=Image.frombytes('RGB',(frame['width'],frame['height']),path.read_bytes(),'raw','BGRX',frame['stride'])
    if frame['flags']&1:im=im.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    im.save(out/(label+'.png'));return im
   snapshots[(mode,'root')]=image('root')
   if mode=='provider':
    state=request('state 0');check('detached-native-root',state['visible'] and not state['tracking'] and state['frame'][2]>0,source=state)
    item_offset=[state['item'][0]-state['frame'][0]+state['item'][2]/2,state['item'][1]-state['frame'][1]+state['item'][3]/2]
   assert command(f"pointer {round(root['x']+item_offset[0])} {round(root['y']+item_offset[1])}")['ok'];assert command('button 272 1')['ok']
   if mode=='provider':
    held=until(lambda:request('state -1'),lambda s:s['tracking']);check('native-tracking-pumps-owner',held['pumps']>0,source=held)
    check('held-model-change-rejected',not request('mutate')['ok']);check('held-hide-rejected',not request('hide')['ok'])
    (out/'held-submenu-state.json').write_text(json.dumps(request('state 1'),indent=2)+'\n')
    (out/'held-all-windows.json').write_text(json.dumps(command('windows'),indent=2)+'\n')
   branch=until(lambda:command('popups'),lambda w:len(w)==1);(out/'submenu-windows.json').write_text(json.dumps(branch,indent=2)+'\n')
   # Keep the native tracking pointer on Edit while taking an unaltered image;
   # capture includes that cursor in both the provider and reference images.
   head=command('outputs')[0];path=out/'submenu.raw';start=len(capture.events);capture.send('capture '+head['name']+' '+str(path));frame=capture.wait('frame',start)
   im=Image.frombytes('RGB',(frame['width'],frame['height']),path.read_bytes(),'raw','BGRX',frame['stride'])
   if frame['flags']&1:im=im.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
   im.save(out/'submenu.png');snapshots[(mode,'submenu')]=im
   if mode=='provider':
    state=request('state 1');sub=branch[0]
    point=[sub['x']+state['item'][0]-state['frame'][0]+state['item'][2]/2,sub['y']+state['item'][1]-state['frame'][1]+state['item'][3]/2]
    assert command(f'pointer {round(point[0])} {round(point[1])}')['ok']
    highlighted=until(lambda:request('state 1'),lambda s:s['highlighted']==0)
    (out/'native-leaf-highlight.json').write_text(json.dumps(highlighted,indent=2)+'\n')
    assert command('button 272 0')['ok']
    action=until(lambda:request('state -1'),lambda s:s['actions']>0)
    check('actual-native-submenu-action',action['actions']==1 and action['last']==64 and not action['tracking'],source=action)
    check('idle-model-update-accepted',request('mutate')['ok'])
    updated=until(windows,lambda w:len(w)==1)[0]
    check('model-update-retains-native-root-surface',updated['id']==root['id'],before=root,after=updated)
    request('disable');check('live-application-availability',not request('state 1')['enabled']);request('enable')
    check('hide-native-window',request('hide')['ok']);until(windows,lambda w:not w)
    check('reshow-native-window',request('show')['ok']);until(windows,lambda w:len(w)==1)
    root=windows()[0];direct=request('state 6')
    point_direct=[direct['item'][0]-direct['frame'][0]+direct['item'][2]/2,direct['item'][1]-direct['frame'][1]+direct['item'][3]/2]
    point=[root['x']+point_direct[0],root['y']+point_direct[1]]
    assert command(f"pointer {round(point[0])} {round(point[1])}")['ok'];assert command('button 272 1')['ok']
    until(lambda:request('state -1'),lambda s:s['tracking'])
    assert command(f"pointer {round(root['x']+item_offset[0])} {round(root['y']+item_offset[1])}")['ok']
    try:until(lambda:command('popups'),lambda w:len(w)==1)
    except AssertionError:
     (out/'cancel-reentry.json').write_text(json.dumps(dict(root=request('state -1'),branch=request('state 1'),windows=command('windows'),popups=command('popups')),indent=2)+'\n')
     raise
    check('cancel-held-menu',request('cancel')['ok'])
    cancelled=until(lambda:request('state -1'),lambda s:not s['tracking'])
    check('cancel-suppresses-command',cancelled['actions']==1 and not cancelled['visible'],source=cancelled)
    assert command('button 272 0')['ok'];until(windows,lambda w:not w)
    check('cancel-removes-native-popup',not command('popups'))
   else:
    assert command('button 272 0')['ok'];assert command('key 1 1')['ok'];assert command('key 1 0')['ok']
    request('hide');until(windows,lambda w:not w);request('show');root=until(windows,lambda w:len(w)==1)[0]
    # Repeat the same native submenu lifecycle without the provider binding.
    assert command(f"pointer {round(root['x']+point_direct[0])} {round(root['y']+point_direct[1])}")['ok']
    assert command('button 272 1')['ok']
    assert command(f"pointer {round(root['x']+item_offset[0])} {round(root['y']+item_offset[1])}")['ok']
    until(lambda:command('popups'),lambda w:len(w)==1);check('reference-submenu-remaps',True)
    assert command('button 272 0')['ok'];assert command('key 1 1')['ok'];assert command('key 1 0')['ok']
   probe.stdin.write('quit\n');probe.stdin.flush();probe.wait(timeout=10)
   remainder=probe.stdout.read();(out/'final.stdout').write_text(remainder)
   check(mode+'-clean-exit',probe.returncode==0,code=probe.returncode);probe=None
  for label in ['root','submenu']:
   first=snapshots[('provider',label)];second=snapshots[('reference',label)]
   check('complete-native-pixels-'+label,first.size==second.size and first.tobytes()==second.tobytes())
 finally:
  if probe:stop(probe)
  if capture:capture.stop()
  services.close()
  stop(compositor);parent.close();broker.close()
  (a.output/'cleanup.json').write_text(json.dumps([dict(pid=p.pid,exit=p.returncode) for p in processes],indent=2)+'\n')
print(json.dumps(dict(passed=len(rows))))
