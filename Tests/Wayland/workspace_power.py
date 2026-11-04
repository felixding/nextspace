#!/usr/bin/env python3
"""Native Workspace power flow; all power methods go to an owned fake bus."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import select
import shlex
import subprocess
import tempfile
import time

from integration import until
from alerts import assert_on_output


def check(service,env,command,current,start,probe,artifacts):
    address=env.get('DBUS_SYSTEM_BUS_ADDRESS','')
    assert address==env.get('NEXTSPACE_POWER_TEST_BUS') and address.startswith('unix:path=/tmp/nextspace-power-'), 'Requires the owned power-test bus'
    artifacts.mkdir()
    records=[]
    def key(code):
        assert command(f'key {code} 1')['ok'];time.sleep(.02);assert command(f'key {code} 0')['ok']
    def windows():return [w for w in command('windows') if w['pid']==current().pid and w['visible']]
    def click(window,button):
        assert command(f"pointer {round(window['x']+button['x'])} {round(window['y']+window['height']-button['y'])}")['ok']
        assert command('button 272 1')['ok'];time.sleep(.02);assert command('button 272 0')['ok']
    def application(action=None,window=None):
        arguments=['--application-action','Workspace',action] if action else ['--application-state','Workspace']
        if window is not None:arguments+=['--window-number',str(window)]
        result=subprocess.run([probe,*arguments],env=env,capture_output=True,text=True,timeout=8)
        with (artifacts/'application-api.jsonl').open('a') as log:
            log.write(json.dumps(dict(arguments=arguments,returncode=result.returncode,
                stdout=result.stdout,stderr=result.stderr))+'\n')
        assert result.returncode==0,result.stderr
        return json.loads(result.stdout)
    for index,scale in enumerate((120,180,240)):
        if index:start()
        for index_head,head in enumerate(command('outputs')):
            positions=(0,1800) if index==0 else (-1700,200) if index==1 else (-900,100)
            assert command(f"output-position {head['name']} {positions[index_head]} 0")['ok']
            assert command(f"test-scale {head['name']} {scale} 10000")['ok'];assert command('confirm')['ok']
        for behavior in ('deny','timeout','accept'):
            path=artifacts/f'{scale}-{behavior}.jsonl'
            with path.open('w') as log,(artifacts/f'{scale}-{behavior}.stderr').open('w') as errors:
                mock=subprocess.Popen([str(service),behavior],env=dict(env,DBUS_SESSION_BUS_ADDRESS=address),
                    stdout=log,stderr=errors)
            def events():return [json.loads(row) for row in path.read_text().splitlines()]
            try:
                until(lambda:events() and events()[0].get('ready'),'owned fake power service')
                try:
                    layout=subprocess.run([str(Path(probe).with_name('AlertProbe')),'--power-layout',
                        '-GSBackend','libgnustep-wayland','-GSTheme','NextSpace','-NSUseRunningCopy','NO',
                        '-GSSuppressAppIcon','YES'],env=env,capture_output=True,text=True,timeout=15)
                except subprocess.TimeoutExpired as error:
                    decode=lambda value:value.decode(errors='replace') if isinstance(value,bytes) else value
                    (artifacts/f'{scale}-{behavior}-layout-timeout.json').write_text(json.dumps(dict(
                        stdout=decode(error.stdout),stderr=decode(error.stderr)),indent=2)+'\n')
                    raise
                (artifacts/f'{scale}-{behavior}-layout.json').write_text(json.dumps(dict(returncode=layout.returncode,
                    stdout=layout.stdout,stderr=layout.stderr),indent=2)+'\n')
                assert layout.returncode==0,layout.stderr
                measured=json.loads(layout.stdout);buttons=measured['buttons']
                viewer=until(lambda:next((w for w in windows() if w['style']&1 and w['width']>200),None),'Workspace main window')
                heads=command('outputs');owner=heads[index%len(heads)]
                assert command(f"move {viewer['id']} {owner['x']+20} {owner['y']+40}")['ok']
                until(lambda:f"x = {owner['x']};" in application(window=viewer['client_id'])['screen_frame'],
                    'owning window reaches the target logical output')
                before={w['id'] for w in windows()}
                (artifacts/f'{scale}-{behavior}-activation.json').write_text(json.dumps(application(),indent=2)+'\n')
                application('activate')
                assert command(f"focus {viewer['id']}")['ok']
                until(lambda:application()['active'],'Workspace active before its quit shortcut')
                assert command('key 56 1')['ok'];key(16);assert command('key 56 0')['ok']
                def new_dialog(excluded):
                    return next((w for w in windows() if w['focused'] and w['style']&1 and w['id'] not in excluded),None)
                dialog=until(lambda:new_dialog(before),'Workspace logout confirmation')
                assert (dialog['width'],dialog['height'])==(measured['width'],measured['height']),(dialog,measured)
                power_button=next(button for button in buttons if button['title'].lower().replace(' ','')=='poweroff')
                (artifacts/f'{scale}-{behavior}-panel.json').write_text(json.dumps(dict(window=dialog,buttons=buttons),indent=2)+'\n')
                assert_on_output(dialog,[owner])
                click(dialog,power_button)
                until(lambda:len(events())==2,'Workspace power request reached owned service')
                assert events()[1]==dict(method='PowerOff',interactive=True),events()
                started=time.monotonic()
                responsive=False
                if behavior=='timeout':
                    head=owner;changed=150 if scale==120 else scale-30
                    assert command(f"test-scale {head['name']} {changed} 10000")['ok'];assert command('confirm')['ok']
                    until(lambda:any(w['id']==viewer['id'] and w['preferred_scale']==changed and
                        w['buffer_width']==(w['width']*changed+60)//120 for w in windows()),
                        'Workspace redraw while power reply is pending',timeout=2)
                    responsive=True
                if behavior=='accept':
                    assert current().wait(timeout=10)==129,'Power acceptance did not complete normal Workspace exit'
                else:
                    error=until(lambda:new_dialog(before|{dialog['id']}),'Power failure alert',timeout=8)
                    assert current().poll() is None
                    if behavior=='timeout':assert time.monotonic()-started>=4
                    (artifacts/f'{scale}-{behavior}-alert.json').write_text(json.dumps(error,indent=2)+'\n')
                    key(28)
                    until(lambda:not any(w['id']==error['id'] for w in windows()),'Power error dismissed with Return')
                    assert any(w['id']==viewer['id'] for w in windows()),'Power denial destroyed the desktop'
                    for head in command('outputs'):
                        assert command(f"test-scale {head['name']} {scale} 10000")['ok'];assert command('confirm')['ok']
                assert len(events())==2,'Duplicate power request'
                records.append(dict(scale=scale,behavior=behavior,accepted=behavior=='accept',
                    desktop_preserved=behavior!='accept',pending_redraw=responsive,
                    response_seconds=time.monotonic()-started,pid=current().pid,
                    exitcode=current().returncode))
                (artifacts/'results.json').write_text(json.dumps(dict(cases=records,complete=False,actual_power_calls=False),indent=2)+'\n')
            except BaseException:
                try:(artifacts/f'{scale}-{behavior}-failure.json').write_text(json.dumps(dict(windows=windows(),events=events()),indent=2)+'\n')
                except (OSError,AssertionError,ValueError):pass
                raise
            finally:
                if mock.poll() is None:mock.terminate();mock.wait(timeout=5)
    (artifacts/'results.json').write_text(json.dumps(dict(cases=records,complete=True,actual_power_calls=False),indent=2)+'\n')
    print('Native Workspace power acceptance, denial, timeout and pending redraw: PASS')


@contextmanager
def owned_bus(artifacts):
    service=artifacts/'power-service-probe'
    flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','gio-2.0'],text=True))
    subprocess.run(['cc',str(Path(__file__).with_name('power-service-probe.c')),'-o',str(service),*flags],check=True)
    with tempfile.TemporaryDirectory(prefix='nextspace-power-') as runtime:
        with (artifacts/'bus.log').open('w') as errors:
            bus=subprocess.Popen(['dbus-daemon','--session','--nofork','--nopidfile',
                '--address=unix:path='+runtime+'/bus','--print-address=1'],stdout=subprocess.PIPE,stderr=errors,text=True)
        try:
            assert select.select([bus.stdout],[],[],5)[0]
            address=bus.stdout.readline().strip();assert address.startswith('unix:path='+runtime+'/bus')
            yield service,address
        finally:
            bus.terminate();bus.wait(timeout=5);bus.stdout.close()


def run(compositor,workspace,probe,artifacts):
    artifacts.mkdir(parents=True)
    with owned_bus(artifacts) as (service,address):
        env=dict(os.environ,DBUS_SYSTEM_BUS_ADDRESS=address,NEXTSPACE_POWER_TEST_BUS=address)
        subprocess.run(['python3',str(Path(__file__).with_name('workspace.py')),'--compositor',compositor,
            '--workspace',workspace,'--probe',probe,'--power-probe',str(service),
            '--alert-probe',str(Path(probe).with_name('AlertProbe')),'--artifacts',str(artifacts/'workspace')],env=env,check=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('compositor','workspace','probe'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--artifacts',type=Path,required=True)
    args=parser.parse_args();run(args.compositor,args.workspace,args.probe,args.artifacts)
