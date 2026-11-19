#!/usr/bin/env python3
"""A persistent original NSMenu must not swallow the next field click."""
import argparse,json,os,select,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Wayland'))
from gnustep import headless_session

p=argparse.ArgumentParser(description=__doc__)
for name in ('runtime','backend','probe','output'):
    p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--scale',type=int,default=120)
p.add_argument('--expect-swallowed',action='store_true')
a=p.parse_args();rows=[];child=None;destination=None
def check(case,passed,**details):
    rows.append(dict(case=case,passed=bool(passed),**details))
    (a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
    assert passed,rows[-1]
extra=dict(GNUSTEP_CONFIG_FILE='/Library/Preferences/GNUstep.conf',WLR_HEADLESS_OUTPUTS='1',
    LD_LIBRARY_PATH=':'.join(map(str,[a.runtime/'native-ui',a.runtime,Path('/Library/Libraries'),Path('/usr/NextSpace/lib')])))
with headless_session(a.runtime/'nextspace-compositor',a.output,extra_env=extra) as (env,command):
    bundles=Path(env['GNUSTEP_CONFIG_FILE']).parent/'empty-library/Bundles';bundles.mkdir(parents=True)
    (bundles/'libgnustep-wayland-032.bundle').symlink_to(a.backend)
    head=command('outputs')[0]
    assert command('resize-output '+head['name']+' 1464 918')['ok']
    assert command('test-scale '+head['name']+' '+str(a.scale)+' 10000')['ok']
    assert command('confirm')['ok']
    try:
        with (a.output/'probe.stderr').open('w') as log:
            child=subprocess.Popen([str(a.probe),'-GSBackend','wayland','-GSTheme','NextSpace','-NSUseRunningCopy','NO'],
                env=dict(env,WAYLAND_DEBUG='1'),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True)
        def read(process=child):
            assert select.select([process.stdout],[],[],12)[0],'native probe response'
            value=json.loads(process.stdout.readline())
            with (a.output/'probe.jsonl').open('a') as f:f.write(json.dumps(value)+'\n')
            return value
        assert read()['event']=='ready'
        with (a.output/'destination.stderr').open('w') as log:
            destination=subprocess.Popen([str(a.probe),'-GSBackend','wayland','-GSTheme','NextSpace','-NSUseRunningCopy','NO'],
                env=dict(env,NEXTSPACE_MENU_DESTINATION='1'),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True)
        assert read(destination)['event']=='ready'
        def state(process=child):
            process.stdin.write('state\n');process.stdin.flush();return read(process)
        def until(predicate,label):
            end=time.monotonic()+12
            while True:
                value=state()
                if predicate(value):return value
                assert time.monotonic()<end,(label,value)
                time.sleep(.03)
        def point(s,key):
            x,y,w,h=s[key];screen=s['screen']
            return x+w/2,screen[1]+screen[3]-(y+h/2)
        def click(position):
            assert command('pointer %.0f %.0f'%position)['ok']
            for down in (1,0):
                assert command('button 272 '+str(down))['ok'];time.sleep(.08)
        s=until(lambda s:s['first_rect'][2]>0,'native geometry')
        click(point(s,'first_rect'));s=until(lambda s:s['first_focused'],'initial field pointer focus')
        initial_first=s['first'];foreign=state(destination);initial_second=foreign['second']
        initial_foreign_first=foreign['first']
        check('original-native-first-field-focused-by-pointer',True)
        click(point(s,'menu_item'));s=until(lambda s:s['submenu_visible'],'original submenu opens')
        check('original-application-submenu-is-persistent',not s['submenu_transient'],level=s['submenu_level'])
        click(point(s,'command_item'));s=until(lambda s:s['actions']==1,'original menu command')
        check('original-menu-action-runs-once',s['actions']==1)
        check('original-persistent-submenu-remains-after-command',s['submenu_visible'])
        click(point(foreign,'second_rect'))
        end=time.monotonic()+12
        while True:
            foreign=state(destination)
            if a.expect_swallowed or foreign['second_focused']:break
            assert time.monotonic()<end,foreign
            time.sleep(.03)
        check('single-outside-click-reaches-foreign-destination-field',foreign['second_focused']!=a.expect_swallowed,
            focused=foreign['second_focused'],negative=a.expect_swallowed,source_pid=child.pid,destination_pid=destination.pid)
        for down in (1,0):assert command('key 45 '+str(down))['ok']
        end=time.monotonic()+12
        while True:
            s=state();foreign=state(destination)
            if foreign['second']!=initial_second or foreign['first']!=initial_foreign_first or s['first']!=initial_first:break
            assert time.monotonic()<end,(s,foreign)
            time.sleep(.03)
        check('next-key-edits-the-clicked-foreign-native-field',(foreign['second']!=initial_second and s['first']==initial_first)!=a.expect_swallowed,
            source=s['first'],destination=foreign['second'],other_destination_field=foreign['first'],negative=a.expect_swallowed)
        debug=(a.output/'probe.stderr').read_text()
        grabs=[line for line in debug.splitlines() if 'xdg_popup' in line and '.grab(' in line]
        check('persistent-native-submenu-has-no-dismissal-grab',bool(grabs)==a.expect_swallowed,grabs=len(grabs),negative=a.expect_swallowed)
        print(json.dumps(dict(complete=True,checks=len(rows),negative=a.expect_swallowed)),flush=True)
    finally:
        stopped=[]
        for process in (destination,child):
            if not process:continue
            if process.poll() is None:
                process.stdin.write('quit\n');process.stdin.flush()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=5)
            stopped.append(dict(pid=process.pid,exit=process.returncode,live=process.poll() is None))
        (a.output/'cleanup.json').write_text(json.dumps(stopped)+'\n')
