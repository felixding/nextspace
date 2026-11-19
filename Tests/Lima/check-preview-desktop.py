#!/usr/bin/env python3
"""Release gate using the existing preview and ordinary desktop seat input.

Run inside the Linux review VM as its desktop user. Each density gets a fresh
preview session, original browsers, and the exact delivery runtime. A startup,
interaction or manifest failure keeps the aggregate result incomplete.
"""
import argparse
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import time

repo=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--preview',type=Path,default=repo/'.build/native-ui/macbook-preview.py')
parser.add_argument('--output',type=Path,required=True)
scales=(1,1.25,1.5,1.75,2)
parser.add_argument('--scale',type=float,choices=scales,action='append')
args=parser.parse_args()
assert sys.platform.startswith('linux') and os.geteuid()!=0,'Run as the desktop user inside the Linux VM'
args.output.mkdir(parents=True,exist_ok=True)
report=dict(complete=False,runs=[])
def save():
    temporary=args.output/'results.next'
    temporary.write_text(json.dumps(report,indent=2)+'\n')
    temporary.replace(args.output/'results.json')

save()
for index,scale in enumerate(args.scale or scales):
    free=shutil.disk_usage(args.output).free
    assert free>=1024**3,('Guest needs at least1GiB free before a desktop run',free)
    run=dict(scale=scale,complete=False,guest_free_before=free)
    report['runs'].append(run);save()
    # Keep the logical desktop unchanged. Physical pixels and Wayland's
    # fractional-scale units must remain integral at every supported density.
    width,height=round(1464*scale),round(918*scale)
    units=round(120*scale)
    run.update(output_pixels=[width,height],scale_units=units)
    env=dict(os.environ,NEXTSPACE_PREVIEW_HEADLESS='1',
             NEXTSPACE_PREVIEW_OUTPUT_SIZE=f'{width}x{height}',
             NEXTSPACE_PREVIEW_SCALE=str(units))
    # Diagnostics, automation ports and an extended startup deadline cannot
    # silently become part of a successful ordinary-session qualification.
    for name in ('NEXTSPACE_TRACE_ACTIVATION','NEXTSPACE_TRACE_NATIVE_RPC',
                 'NEXTSPACE_PREVIEW_STARTUP_TIMEOUT'):
        env.pop(name,None)
    with (args.output/f'scale-{scale:g}.stderr').open('w') as error:
        child=subprocess.Popen([sys.executable,str(args.preview)],env=env,
            stdout=subprocess.PIPE,stderr=error,text=True,start_new_session=True)
        try:
            deadline=time.monotonic()+450
            while True:
                assert time.monotonic()<deadline,'Preview did not become ready'
                assert child.poll() is None,('Preview exited before readiness',child.returncode)
                if not select.select([child.stdout],[],[],.5)[0]:continue
                line=child.stdout.readline()
                if not line:continue
                event=json.loads(line)
                if event.get('event')=='manual-preview-starting':
                    run['root']=event['root'];save()
                if event.get('event')=='manual-preview-ready':break
            root=Path(event['root']);run['root']=str(root);save()
            # Fail new payload-verification wiring before the long interaction
            # sequence. Recheck afterward against the actual panel owner too.
            subprocess.run([sys.executable,str(repo/'Tests/Lima/check-preview-payload.py'),str(root)],
                env=env,check=True,timeout=120)
            subprocess.run([sys.executable,str(repo/'Tests/Wayland/native_desktop_shortcuts.py'),str(root)],
                env=env,check=True,timeout=120)
            subprocess.run([sys.executable,str(repo/'Tests/Wayland/native_desktop_pickers.py'),str(root),
                '--first-browser','firefox' if index%2==0 else 'chromium'],
                env=env,check=True,timeout=600)
            subprocess.run([sys.executable,str(repo/'Tests/Wayland/native_picker_keyboard.py'),str(root)],
                env=env,check=True,timeout=600)
            subprocess.run([sys.executable,str(repo/'Tests/Wayland/native_desktop_menus.py'),str(root)],
                env=env,check=True,timeout=120)
            endpoint=next(line.split('=',1)[1] for line in (root/'session.stdout').read_text().splitlines()
                          if line.startswith('NEXTSPACE_NATIVE_UI_SOCKET='))
            subprocess.run([sys.executable,str(repo/'Tests/NativeUI/color-owner-transport.py'),
                '--endpoint',endpoint,'--desktop',str(root/'control.sock'),
                '--output',str(root/'color-owner-transport.json')],env=env,check=True,timeout=120)
            subprocess.run([sys.executable,str(repo/'Tests/NativeUI/invalidation-transport.py'),
                '--endpoint',endpoint,'--output',str(root/'invalidation-transport.json')],
                env=env,check=True,timeout=30)
            subprocess.run([sys.executable,str(repo/'Tests/Lima/check-preview-payload.py'),str(root)],
                env=env,check=True,timeout=120)
            checks=json.loads((root/'ordinary-picker-ux.json').read_text())
            assert checks['complete'] and all(row['passed'] for row in checks['checks'])
            run.update(complete=True,checks=len(checks['checks']))
            save()
        except BaseException as failure:
            run['error']=repr(failure);save();raise
        finally:
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=90)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid,signal.SIGTERM)
                    child.wait(timeout=10)
            if 'root' in run:
                cleanup=json.loads((Path(run['root'])/'cleanup.json').read_text())
                detached=cleanup.get('detached_processes',{})
                run['cleanup_passed']=(cleanup['session_exit'] is not None and
                    not cleanup['live'] and not cleanup.get('errors') and
                    'remaining' in detached and detached['remaining']==[])
                save()
                assert run['cleanup_passed'],'Private preview processes survived teardown'
report['complete']=all(run['complete'] for run in report['runs'])
save();print(json.dumps(report))
