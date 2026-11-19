#!/usr/bin/env python3
"""A stalled external selection must not stall native paint RPC."""
import argparse,ctypes as C,importlib.util,json,os,socket,subprocess,sys,time
from pathlib import Path
from contextlib import ExitStack
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Wayland'))
from gnustep import headless_session,pasteboard_storage
spec=importlib.util.spec_from_file_location('wire',Path(__file__).with_name('color-owner-transport.py'))
wire=importlib.util.module_from_spec(spec);spec.loader.exec_module(wire)
from native_controls import ControlInputRequest
from helper import Request as ScrollerRequest

p=argparse.ArgumentParser(description=__doc__)
for name in ['runtime','build','registry','output']:p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--readiness-only',action='store_true',help='Negative control with the previous readiness-only registration')
p.add_argument('--queued-key',action='store_true',help='Queue an unrelated native key during the selection transfer')
p.add_argument('--queued-pointer',action='store_true',help='Queue an original native button press/release during the transfer')
p.add_argument('--queued-scroller',action='store_true',help='Queue an original native scroller drag/release during the transfer')
p.add_argument('--expect-paint-stall',action='store_true',help='Record the queued-key failure against the previous helper')
a=p.parse_args();a.output.mkdir(parents=True);rows=[];children=[]
assert sum((a.queued_key,a.queued_pointer,a.queued_scroller))<=1
assert not a.expect_paint_stall or a.queued_key or a.queued_pointer or a.queued_scroller
def stop(child):
    if child.poll() is None:
        child.terminate()
        try:child.wait(timeout=5)
        except subprocess.TimeoutExpired:child.kill();child.wait()
def until(read,predicate,label):
    deadline=time.monotonic()+12
    while True:
        value=read()
        if predicate(value):return value
        assert time.monotonic()<deadline,(label,value)
        time.sleep(.02)
def check(case,passed,**info):
    rows.append(dict(case=case,passed=bool(passed),**info))
    (a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
    assert passed,rows[-1]
extra=dict(GNUSTEP_CONFIG_FILE='/Library/Preferences/GNUstep.conf',WLR_HEADLESS_OUTPUTS='1',
    LD_LIBRARY_PATH=':'.join(map(str,[a.runtime/'native-ui',a.runtime,a.build/'native-ui',a.build,Path('/Library/Libraries'),Path('/usr/NextSpace/lib')])) )
with headless_session(a.runtime/'nextspace-compositor',a.output,extra_env=extra) as (env,command),ExitStack() as services:
    bundles=Path(env['GNUSTEP_CONFIG_FILE']).parent/'empty-library/Bundles';bundles.mkdir(parents=True)
    (bundles/'libgnustep-wayland-032.bundle').symlink_to(a.runtime/'native-ui/libgnustep-wayland-032.bundle')
    services.enter_context(pasteboard_storage('/Library/bin/gpbs-wayland',a.build/'native-ui/native-pasteboard-probe',env,a.output))
    scripts=Path(__file__).resolve().parents[2]/'Experiments/ChromiumScrollers'
    helper=scripts/'helper.py'
    if a.readiness_only:
        helper=a.output/'readiness-only-helper.py'
        text=(scripts/'helper.py').read_text();assert text.count('if forms.callback_source_capabilities else')==1
        helper.write_text(text.replace('if forms.callback_source_capabilities else','if False else'))
        env['PYTHONPATH']=str(scripts)
    endpoint=Path(env['XDG_RUNTIME_DIR'])/'native.sock'
    with (a.output/'helper.jsonl').open('w') as out,(a.output/'helper.stderr').open('w') as err:
        host=subprocess.Popen([sys.executable,str(helper),'--library',str(a.runtime/'libnextspace-native-scroller.so.1'),'--socket',str(endpoint),'-GSBackend','wayland','-GSTheme','NextSpace'],env=env,stdout=out,stderr=err);children.append(host)
    client=key_client=None
    try:
        until(lambda:endpoint.exists(),bool,'native host readiness')
        client=wire.Client(str(endpoint),0xc0000000+os.getpid())
        check('native-panel-created',client.register() and client.configure() and client.sync(.25,.5,.75))
        def scroller(operation,**values):
            request=ScrollerRequest(magic=0x4e585343,operation=operation,process=key_client.process,control=1)
            for name,value in values.items():setattr(request,name,value)
            key_client.socket.send(bytes(request))
            reply=wire.Response.from_buffer_copy(key_client.socket.recv(65536))
            assert reply.magic==request.magic
            return reply
        if a.queued_key or a.queued_pointer or a.queued_scroller:
            key_client=wire.Client(str(endpoint),0xc1000000+os.getpid())
        if a.queued_scroller:
            reply=scroller(1,length=240,total=1200,page=120,value=200)
            check('unrelated-native-scroller-created',reply.parts[2].height>0)
        elif key_client:
            check('unrelated-native-button-created',key_client.register() and
                  key_client.request(1,kind=1,width=120,height=24,enabled=1)[0].width==120)
            focus=ControlInputRequest(magic=wire.MAGIC,operation=7,process=key_client.process,kind=1,control=1,focused=1)
            check('unrelated-native-button-focused',key_client.exchange(focus)[0].parts[3].y==1)
        check('native-panel-open',client.request(59,state=1)[0].parts[0].height==1)
        panel=until(lambda:command('windows'),lambda ws:any(w['visible'] and w['title']=='Colors' for w in ws),'native panel maps')
        def click(window):
            for text in [f"pointer {window['x']+window['width']/2:.0f} {window['y']+11}",'button 272 1','button 272 0']:
                assert command(text)['ok']
        for mode in ('clipboard','primary'):
            key_actions=key_client.request(0,kind=1)[0].parts[0].width if key_client and not a.queued_scroller else 0
            payload=a.output/(mode+'.txt');payload.write_text('Selection awaiting native browser paint\n')
            log=a.output/(mode+'-source.log')
            with log.open('w') as out:
                source=subprocess.Popen([str(a.registry),'--'+mode+'-stall',str(payload)],env=dict(env,WAYLAND_DEBUG='1'),stdout=out,stderr=out);children.append(source)
            try:
                ws=until(lambda:command('windows'),lambda ws:any(w['visible'] and w['title']=='ClipboardProbe' for w in ws),'source maps')
                click(next(w for w in ws if w['title']=='ClipboardProbe' and w['visible']))
                for value in ('key 30 1','key 30 0'):assert command(value)['ok']
                until(log.read_text,lambda s:'Clipboard source set' in s,'source owns selection')
                # NSColorPanel normally hides when the external source takes
                # focus. Reopen that same panel through its existing owner.
                check(mode+'-native-owner-reopens-panel',client.request(59,state=2)[0].parts[0].height==1)
                ws=until(lambda:command('windows'),lambda ws:any(w['title']=='Colors' and w['visible'] for w in ws),'native panel reopens')
                click(next(w for w in ws if w['title']=='Colors' and w['visible']))
                until(log.read_text,lambda s:'.send(' in s,'native selection import waits on external pipe')
                if a.queued_scroller:
                    before=scroller(0);knob=before.parts[2]
                    x,y=knob.x+knob.width/2,knob.y+knob.height/2
                    press=scroller(2,length=x,total=y)
                    check(mode+'-native-pointer-queued-before-tracking',press.parts[0].y==1)
                    for operation in (3,4):
                        key_client.socket.send(bytes(ScrollerRequest(magic=0x4e585343,
                            operation=operation,process=key_client.process,control=1,length=x,total=y+30)))
                elif a.queued_pointer:
                    press=key_client.request(2,kind=1,x=20,y=12)[0]
                    check(mode+'-native-pointer-queued-before-tracking',press.parts[0].y==1)
                    release=wire.ControlRequest(magic=wire.MAGIC,operation=4,process=key_client.process,kind=1,control=1,x=20,y=12)
                    key_client.socket.send(bytes(release))
                elif key_client:
                    before=(a.output/'helper.jsonl').read_text().count('native-key-deferred')
                    key=ControlInputRequest(magic=wire.MAGIC,operation=8,process=key_client.process,kind=1,control=1,type=0,text_size=1,unmodified_size=1)
                    key_client.socket.send(bytes(key)+b'  ')
                    until(lambda:(a.output/'helper.jsonl').read_text().count('native-key-deferred'),
                          lambda count:count>before,'native key deferred until the current stack returns')
                started=time.monotonic();client.socket.settimeout(.5 if key_client else 1)
                try:
                    reply,_=client.request(1,width=120,height=24,maximum=1,enabled=1)
                    responsive=reply.width>0
                except socket.timeout:responsive=False
                elapsed=time.monotonic()-started
                negative=a.readiness_only or a.expect_paint_stall
                check(mode+'-paint-rpc-during-native-transfer',responsive!=negative,seconds=elapsed,reply_received=responsive,negative_control=negative)
                # Closing the source releases the transfer pipe before the
                # next graphical case starts; its process is always reaped.
            finally:stop(source)
            client.socket.settimeout(10)
            if a.readiness_only or a.expect_paint_stall:client.socket.recv(65536)
            if key_client:
                reply=wire.Response.from_buffer_copy(key_client.socket.recv(65536))
                if a.queued_scroller:
                    wire.Response.from_buffer_copy(key_client.socket.recv(65536))
                    current=until(lambda:scroller(0),lambda r:not r.parts[0].y,
                        mode+' original scroller tracking completion')
                    check(mode+'-original-scroller-drag-executed-after-transfer',current.parts[0].x>before.parts[0].x,
                          before=before.parts[0].x,after=current.parts[0].x)
                elif a.queued_pointer:
                    current=until(lambda:key_client.request(0,kind=1)[0],
                        lambda r:r.parts[0].width==key_actions+1 and not r.parts[0].y,
                        mode+' original pointer action and native tracking completion')
                    check(mode+'-original-pointer-executed-once-after-transfer',current.parts[0].width==key_actions+1)
                elif not a.expect_paint_stall:
                    check(mode+'-original-key-executed-once-after-transfer',reply.parts[3].x==1 and reply.parts[0].width==key_actions+1)
            check(mode+'-host-recovers-after-source-exit',client.request(1,width=120,height=24,maximum=1,enabled=1)[0].width>0)
        print(json.dumps(dict(complete=True,checks=len(rows),negative_control=a.readiness_only or a.expect_paint_stall)))
    finally:
        if client:client.close()
        if key_client:key_client.close()
        for child in reversed(children):stop(child)
        (a.output/'cleanup.json').write_text(json.dumps([dict(pid=c.pid,exit=c.returncode) for c in children],indent=2)+'\n')
