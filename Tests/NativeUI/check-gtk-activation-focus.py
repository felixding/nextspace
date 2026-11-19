#!/usr/bin/env python3
from pathlib import Path
import os,subprocess,sys,time,json,select
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Wayland'))
from gnustep import headless_session
parser=__import__('argparse').ArgumentParser(description='Replay queued GTK focus before opening an original GNUstep color panel.')
for name in ['gtk-probe','native-probe','compositor','backend-bundle','output']:parser.add_argument('--'+name,type=Path,required=True)
parser.add_argument('--library-path',type=Path,action='append',required=True)
parser.add_argument('--first-map',action='store_true')
parser.add_argument('--cancel-before-map',action='store_true')
args=parser.parse_args();out=args.output;out.mkdir(parents=True)
assert not args.cancel_before_map or args.first_map
extra=dict(GNUSTEP_CONFIG_FILE='/Library/Preferences/GNUstep.conf',GTK_CSD='0',GDK_BACKEND='wayland',NO_AT_BRIDGE='1',LD_LIBRARY_PATH=':'.join(map(str,args.library_path)))
if args.first_map:extra['NEXTSPACE_TRACE_ACTIVATION']='1'
with headless_session(args.compositor,out,extra_env=extra) as (env,command):
 bundles=Path(env['GNUSTEP_CONFIG_FILE']).parent/'empty-library/Bundles';bundles.mkdir(parents=True)
 (bundles/'libgnustep-wayland-032.bundle').symlink_to(args.backend_bundle,target_is_directory=True)
 children=[]
 def start(name,args):
  child=subprocess.Popen(args,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(out/(name+'.stderr')).open('w'),text=True);children.append(child);return child
 def event(child,phase):
  assert select.select([child.stdout],[],[],12)[0],('phase timeout',phase,child.poll())
  line=child.stdout.readline();assert line,('actor exited',phase,child.poll());value=json.loads(line);assert value['phase']==phase,value;return value
 def send(child,text):child.stdin.write(text+'\n');child.stdin.flush()
 def until(predicate,label):
  end=time.monotonic()+12
  while True:
   value=command('windows')
   if predicate(value):return value
   assert time.monotonic()<end,(label,value);time.sleep(.02)
 try:
  source=start('gtk-source',[str(args.gtk_probe)]);event(source,'ready')
  w=next(w for w in until(lambda a:any(w['pid']==source.pid and w['visible'] for w in a),'GTK mapped') if w['pid']==source.pid)
  assert command('move %d 30 30'%w['id'])['ok'];assert command('pointer 100 100')['ok'];assert command('button 272')['ok'];event(source,'input')
  mode=['--cancel-before-map'] if args.cancel_before_map else ['--first-map'] if args.first_map else []
  target=start('native-target',[str(args.native_probe)]+mode+['-GSBackend','wayland']);event(target,'warm')
  until(lambda a:any(w['pid']==target.pid and w['focused'] for w in a),'native target warm focus');time.sleep(.1)
  send(source,'pause');event(source,'paused-after-focus-out')
  send(target,'reopen');event(target,'reopened')
  until(lambda a:any(w['pid']==source.pid and w['focused'] for w in a),'source actual seat focus')
  assert command('pointer 100 100')['ok'];assert command('button 272')['ok']
  send(source,'token');token=event(source,'token')['token'];send(target,token)
  result=event(target,'result');windows=command('windows')
  result.update(windows=windows)
  result['complete']=bool(result['well_active'] and result['panel_visible'] and any(
    w['pid']==target.pid and w['focused'] for w in windows))
  if args.first_map:
   import re
   activation_rows=[line for line in (out/'compositor.log').read_text().splitlines() if 'Activation received token=' in line]
   result['activation_targets_mapped']=bool(activation_rows) and all(
       re.search(r'target=[1-9][0-9]* mapped=1',line) for line in activation_rows)
   result['activation_trace']=activation_rows
   result['complete']=result['complete'] and result['activation_targets_mapped']
   if args.cancel_before_map:
    result.pop('activation_targets_mapped')
    result['cancelled_activation_not_replayed']=not activation_rows
    result['complete']=bool(result['cancelled_activation_not_replayed'] and not result['well_active'] and
        not result['panel_visible'] and not result['application_active'] and
        any(w['pid']==source.pid and w['focused'] for w in windows))
  (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
  send(target,'finish');send(source,'finish');assert target.wait(timeout=5)==0;assert source.wait(timeout=5)==0
 finally:
  for c in reversed(children):
   if c.poll() is None:c.terminate();c.wait(timeout=5)
  (out/'cleanup.json').write_text(json.dumps(dict(exits=[c.returncode for c in children],
    live=[c.pid for c in children if c.poll() is None]))+'\n')
assert result['complete'],result
case=('cancelled-native-first-map-does-not-replay-activation' if args.cancel_before_map else
      'new-native-panel-activation-target-is-mapped' if args.first_map else
      'queued-gtk-focus-keeps-original-native-color-panel-visible')
print(json.dumps(dict(complete=True,case=case)))
