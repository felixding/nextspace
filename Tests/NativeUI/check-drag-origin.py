#!/usr/bin/env python3
"""Unmapped native drag cancellation and ordinary mapped drag regression."""
import argparse,contextlib,json,os,select,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Wayland'))
from gnustep import headless_session,pasteboard_storage
p=argparse.ArgumentParser(description=__doc__)
for name in ['build','compositor','backend','previous-backend','gui','base','output']:p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);runs=[]
extra=dict(GNUSTEP_CONFIG_FILE='/Library/Preferences/GNUstep.conf',LD_LIBRARY_PATH=':'.join(map(str,[a.gui,a.base,Path('/Library/Libraries'),Path('/usr/NextSpace/lib')])))
@contextlib.contextmanager
def session(compositor,root,backend=None):
 with headless_session(compositor,root,extra_env=extra) as (env,command):
  bundles=Path(env['GNUSTEP_CONFIG_FILE']).parent/'empty-library/Bundles';bundles.mkdir(parents=True)
  (bundles/'libgnustep-wayland-032.bundle').symlink_to(backend or a.backend,target_is_directory=True)
  yield env,command
for phase,backend in [('before',a.previous_backend),('after',a.backend)]:
 root=a.output/phase
 with session(a.compositor,root,backend) as (env,command),pasteboard_storage(Path('/Library/bin/gpbs-wayland'),a.build/'native-ui/native-pasteboard-probe',env,root):
  with (root/'probe.stdout').open('w') as out,(root/'probe.stderr').open('w') as err:
   child=subprocess.Popen([str(a.build/'native-ui/native-drag-origin-probe'),'-GSBackend','wayland'],env=env,stdin=subprocess.PIPE,stdout=out,stderr=err,text=True)
   try:
    end=time.monotonic()+12
    while True:
     text=(root/'probe.stdout').read_text()
     if phase=='before' and child.poll() is not None:break
     if phase=='after' and 'native-window-ready' in text:break
     assert time.monotonic()<end,(phase,text,(root/'probe.stderr').read_text())
     time.sleep(.02)
    events=[json.loads(x) for x in text.splitlines() if x.startswith('{')]
    receipt=next((x for x in events if x['event']=='unmapped-native-drag'),None)
    if receipt is None:
     (root/'unexpected-exit.json').write_text(json.dumps(dict(code=child.poll(),events=events),indent=2)+'\n')
     with (root/'unexpected-backtrace.txt').open('w') as trace:
      subprocess.run(['gdb','-q','-batch','-ex','run','-ex','bt','--args',str(a.build/'native-ui/native-drag-origin-probe'),'-GSBackend','wayland'],env=env,stdout=trace,stderr=trace,timeout=10)
     raise AssertionError((phase,'missing native drag receipt',child.poll(),events))
    if phase=='before':
     assert receipt['began'] and child.returncode!=0,receipt
     runs.append(dict(phase=phase,old_backend_fails_unmapped_origin=True,receipt=receipt))
    else:
     assert not receipt['began'] and receipt['ended'] and receipt['operation']==0,receipt
     while True:
      windows=command('windows');shown=[w for w in windows if w['title']=='Native drag origin guard' and w['visible']]
      if shown:break
      assert child.poll() is None and time.monotonic()<end,windows
      time.sleep(.02)
     (root/'native-window-after-cancel.json').write_text(json.dumps(shown,indent=2)+'\n')
     child.stdin.write('\n');child.stdin.flush();child.wait(timeout=5);assert child.returncode==0
     runs.append(dict(phase=phase,cancelled_without_begin=True,display_still_maps_native_windows=True,receipt=receipt))
   finally:
    if child.poll() is None:child.terminate()
    child.wait(timeout=5)
import drag_start
# Reuse the original real-pointer AppKit drag cases, with the selected backend.
drag_start.headless_session=session
drag_start.run(a.compositor,a.build/'native-ui/native-drag-window-probe',Path('/Library/bin/gpbs-wayland'),a.build/'native-ui/native-pasteboard-probe',a.output/'mapped-drags')
report=dict(complete=True,runs=runs,mapped_drag_cases=10)
(a.output/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
