#!/usr/bin/env python3
"""Validate production power API against an owned fake logind bus only."""
import argparse
import errno
import json
import os
from pathlib import Path
import select
import shlex
import subprocess
import tempfile


def run(probe,artifacts,library_dir=None):
    artifacts.mkdir(parents=True)
    service=artifacts/'power-service-probe'
    flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','gio-2.0'],text=True))
    subprocess.run(['cc',str(Path(__file__).with_name('power-service-probe.c')),'-o',str(service),*flags],check=True)
    rows=[]
    with tempfile.TemporaryDirectory(prefix='nextspace-power-') as runtime:
        with (artifacts/'bus.log').open('w') as errors:
            bus=subprocess.Popen(['dbus-daemon','--session','--nofork','--nopidfile',
                '--address=unix:path='+runtime+'/bus','--print-address=1'],stdout=subprocess.PIPE,stderr=errors,text=True)
        try:
            assert select.select([bus.stdout],[],[],5)[0]
            address=bus.stdout.readline().strip();assert address.startswith('unix:path='+runtime+'/bus')
            env=dict(os.environ,DBUS_SYSTEM_BUS_ADDRESS=address,DBUS_SESSION_BUS_ADDRESS=address,NEXTSPACE_POWER_TEST_BUS=address)
            if library_dir:env['LD_LIBRARY_PATH']=str(library_dir)+':'+env.get('LD_LIBRARY_PATH','')
            for behavior in ('accept','deny','timeout'):
                with (artifacts/(behavior+'.stderr')).open('w') as errors:
                    mock=subprocess.Popen([str(service),behavior],env=env,stdout=subprocess.PIPE,stderr=errors,text=True)
                try:
                    assert select.select([mock.stdout],[],[],5)[0]
                    assert json.loads(mock.stdout.readline())['ready']
                    for action in (('off',) if behavior=='timeout' else ('off','reboot','invalid')):
                        result=subprocess.run([str(probe),action],env=env,capture_output=True,text=True,timeout=12)
                        assert result.returncode==0,result.stderr
                        row=json.loads(result.stdout)
                        if action=='invalid':
                            assert not row['accepted'] and row['error']==errno.EINVAL,row
                            assert not select.select([mock.stdout],[],[],0)[0], 'Invalid action reached logind'
                        else:
                            assert select.select([mock.stdout],[],[],1)[0]
                            call=json.loads(mock.stdout.readline())
                            assert call==dict(method='Reboot' if action=='reboot' else 'PowerOff',interactive=True),call
                            row['call']=call
                            assert row['accepted']==(behavior=='accept'),row
                            if behavior=='deny':assert row['message']=='Denied 100% %@ %s',row
                            if behavior=='timeout':assert 4.8<=row['seconds']<8,row
                        rows.append(dict(behavior=behavior,action=action,**row))
                finally:
                    mock.terminate();mock.wait(timeout=5);mock.stdout.close()
            (artifacts/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
            print(f'System power API: {len(rows)} isolated fake-bus acceptance/denial/deadline checks PASS')
        finally:
            bus.terminate();bus.wait(timeout=5);bus.stdout.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--probe',type=Path,required=True);p.add_argument('--artifacts',type=Path,required=True)
    p.add_argument('--library-dir',type=Path)
    args=p.parse_args();run(args.probe.resolve(),args.artifacts.resolve(),args.library_dir)
