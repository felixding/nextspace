#!/usr/bin/env python3
"""Delay only the owned renderer after real input; observe fresh native grants.

Browser permission checks and native controls are unchanged. The compositor's
original token lifetime and the twelve-second interaction deadline stay intact.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time

from native_density_controls import DensityFixture
from native_context_menus import ContextFixture
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Libraries/NativeUI/Bridge'))
from color_owners import ColorOwners

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('root',type=Path)
parser.add_argument('--scale',type=float,default=2)
parser.add_argument('--port',type=int,default=9293)
args=parser.parse_args();root=args.root
fixture=DensityFixture(root,'chromium',args.port,args.scale,
    page='../../.build/native-ui/desktop-demo/native-controls.html',
    title='NEXTSPACE controls',report='activation-backpressure-checks.json')
rows=[]
def panel(title):
    return next((w for w in fixture.command('windows') if w['visible'] and w['title']==title),None)
def wait(read,predicate,label,deadline):
    while True:
        value=read()
        if predicate(value):return value
        assert time.monotonic()<deadline,(label,value)
        time.sleep(.03)
try:
    for title,selector in [('Date and Time','button[onclick]'),('Colors','input[type=color]')]*2:
        fixture.js('document.querySelector('+json.dumps(selector)+').scrollIntoView({block:"center"})')
        box=fixture.js('document.querySelector('+json.dumps(selector)+').getBoundingClientRect().toJSON()')
        fixture.update_origin();fixture.point(box,box['width']/2,box['height']/2)
        renderers=[]
        for path in Path('/proc').iterdir():
            if not path.name.isdigit():continue
            try:cmd=(path/'cmdline').read_bytes()
            except OSError:continue
            # Chromium can rewrite its process title into one space-delimited
            # argv entry. Keep ownership checks independent of that spelling.
            if b'--type=renderer' in cmd.replace(b'\0',b' ').split() and ColorOwners.ancestor(int(path.name),fixture.pid):
                assert path.stat().st_uid==os.getuid();renderers.append(int(path.name))
        assert renderers,'No renderer belonging to the owned browser'
        before=sum('native-auxiliary-activation' in line for line in (root/'helper.jsonl').read_text().splitlines())
        timer=None;started=time.monotonic()
        try:
            for pid in renderers:os.kill(pid,signal.SIGSTOP)
            fixture.button(1);fixture.button(0)
            def resume():
                for pid in renderers:
                    try:os.kill(pid,signal.SIGCONT)
                    except ProcessLookupError:pass
            timer=threading.Timer(6.2,resume);timer.start()
            current=wait(lambda:panel(title),lambda w:w and w['focused'],title+' after renderer backpressure',started+12)
        finally:
            for pid in renderers:
                try:os.kill(pid,signal.SIGCONT)
                except ProcessLookupError:pass
            if timer:timer.cancel();timer.join()
        elapsed=time.monotonic()-started
        assert elapsed>=6.2,'Renderer was not delayed across the token lifetime'
        def activation():
            events=[json.loads(line) for line in (root/'helper.jsonl').read_text().splitlines() if line.startswith('{')]
            events=[row for row in events if row.get('event')=='native-auxiliary-activation']
            return events[-1] if len(events)>before else None
        receipt=wait(activation,bool,'new activation receipt',started+12)
        assert receipt['token_age']<5,('Token predates delayed presentation',receipt)
        time.sleep(.3);current=panel(title);assert current and current['focused'],current
        ContextFixture.capture(fixture,'activation-backpressure-'+str(len(rows)))
        rows.append(dict(title=title,passed=True,open_seconds=elapsed,activation=receipt))
        if title=='Colors':
            assert fixture.command('pointer %d %d'%(current['x']+current['width']-11,current['y']+11))['ok']
            fixture.button(1);fixture.button(0)
        else:fixture.key(1)
        wait(lambda:panel(title),lambda w:not w,title+' ordinary close',time.monotonic()+12)
    (root/'activation-backpressure.json').write_text(json.dumps(dict(complete=True,checks=rows),indent=2)+'\n')
except BaseException as error:
    ContextFixture.capture(fixture,'activation-backpressure-failure')
    (root/'activation-backpressure.json').write_text(json.dumps(dict(complete=False,checks=rows,error=repr(error)),indent=2)+'\n')
    raise
