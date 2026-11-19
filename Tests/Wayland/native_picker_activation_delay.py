#!/usr/bin/env python3
"""Real seat input with a private adapter delaying presentation after permission.

The diagnostic adapter waits six seconds after the original browser's user
activation check. The ordinary release gate uses the unmodified delivery binary.
Its twelve-second interaction deadline is unchanged in this fault probe too.
"""
import json
import os
from pathlib import Path
import sys
import signal
import time

from desktop_input import Desktop

root=Path(sys.argv[1]);desktop=Desktop(root);rows=[]
for app,x in [('firefox-esr',0),('chromium-browser',900)]:
    window=next(w for w in desktop.command('windows') if w['app_id']==app and w['level']==0)
    assert desktop.command('move %d %d 24'%(window['id'],x))['ok']
desktop.capture('delayed-activation-arranged')
try:
    for index,(title,x) in enumerate([('Colors',525),('Date and Time',245)]*2):
        if index==2:
            before=(root/'session.stdout').read_text().count('"event": "ready"')
            os.kill(rows[-1]['panel_pid'],signal.SIGKILL)
            deadline=time.monotonic()+12
            while (root/'session.stdout').read_text().count('"event": "ready"')<=before:
                assert time.monotonic()<deadline,'Native host did not recover'
                time.sleep(.05)
        desktop.click(1200,254)
        started=time.monotonic();desktop.click(x,490)
        deadline=started+12
        while True:
            windows=desktop.command('windows')
            panel=next((w for w in windows if w['title']==title and w['visible']),None)
            main=next(w for w in windows if w['app_id']=='firefox-esr' and w['level']==0)
            if panel and panel['focused'] and panel['parent_id']==main['id']:break
            assert time.monotonic()<deadline,(title,panel)
            time.sleep(.05)
        elapsed=time.monotonic()-started
        assert elapsed>=6,'The diagnostic delay was not applied'
        assert panel['parent_id']==main['id']
        events=[json.loads(line) for line in (root/'session.stdout').read_text().splitlines() if line.startswith('{')]
        activation=next(event for event in reversed(events) if event.get('event')=='native-auxiliary-activation' and event.get('serial')==0)
        assert activation['token_age']<5,'Token predates the delayed presentation'
        time.sleep(.4)
        current=next(w for w in desktop.command('windows') if w['id']==panel['id'])
        assert current['visible'] and current['focused']
        if index>=2:assert panel['pid']!=rows[0]['panel_pid'],'Original native host was not replaced'
        desktop.capture('delayed-'+title.replace(' ','-')+('-recovered' if index>=2 else ''))
        rows.append(dict(case=title+(' after host replacement' if index>=2 else ''),passed=True,
                         panel_pid=panel['pid'],open_seconds=elapsed,activation=activation))
        if title=='Colors':desktop.click(panel['x']+panel['width']-11,panel['y']+11)
        else:desktop.key(28)
    (root/'delayed-picker-activation.json').write_text(json.dumps(dict(complete=True,checks=rows),indent=2)+'\n')
    print(json.dumps(dict(complete=True,checks=len(rows))))
except BaseException as error:
    desktop.capture('delayed-activation-failure')
    (root/'delayed-picker-activation.json').write_text(json.dumps(dict(complete=False,checks=rows,error=repr(error)),indent=2)+'\n')
    raise
