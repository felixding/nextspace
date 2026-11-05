#!/usr/bin/env python3
"""Check held native address-editor release on window closure and helper loss."""
import argparse,json,os,signal,time
from pathlib import Path
from marionette import Marionette
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--port',type=int,required=True);p.add_argument('--fixture',type=Path,required=True)
a=p.parse_args();root=a.fixture;launch=json.loads((root/'launch.json').read_text());results=[];m=Marionette(a.port)
def js(script):return m.command('WebDriver:ExecuteScript',dict(script=script,args=[]))['value']
def state():return js("let e=document.getElementById('urlbar-input');return {value:e.value,start:e.selectionStart,end:e.selectionEnd}")
def seed(value):return js("let e=document.getElementById('urlbar-input');e.focus();e.value="+json.dumps(value)+";e.setSelectionRange(0,0);return e.getBoundingClientRect().toJSON()")
def rows():return [json.loads(line) for line in (root/'helper.jsonl').read_text().splitlines()]
def check(case,condition,**details):
 results.append(dict(case=case,passed=bool(condition),**details));(root/'frontend-lifecycle.json').write_text(json.dumps(results,indent=2)+'\n');assert condition,results[-1]
def key(value):m.command('WebDriver:PerformActions',dict(actions=[dict(type='key',id='keyboard',actions=[dict(type='keyDown',value=value),dict(type='keyUp',value=value)])]))
def held():
 rect=seed('Alpha beta');x,y=round(rect['x']),round(rect['y'])
 actions=[dict(type='pointerMove',duration=0,x=x+3,y=y+12),dict(type='pointerDown',button=0),dict(type='pointerMove',duration=100,x=x+25,y=y+12),dict(type='pause',duration=100)]
 m.command('WebDriver:PerformActions',dict(actions=[dict(type='pointer',id='mouse',parameters=dict(pointerType='mouse'),actions=actions)]))
 actual=state();check('held-native-range',actual==dict(value='Alpha beta',start=0,end=3),state=actual)
 return next(r for r in reversed(rows()) if r['event']=='native-form-press')
try:
 session=m.command('WebDriver:NewSession',{});check('owned-browser',session['capabilities']['moz:processID']==launch['pids'][-1]);m.command('Marionette:SetContext',dict(value='chrome'))
 first=m.command('WebDriver:GetWindowHandle')['value'];seed('First')
 second=m.command('WebDriver:NewWindow',dict(type='window',focus=True))['handle'];m.command('WebDriver:SwitchToWindow',dict(handle=second))
 press=held();m.command('WebDriver:CloseWindow')
 deadline=time.monotonic()+5
 def destroyed():return any(r['event']=='native-form-destroy' and r['process']==press['process'] and r['control']==press['control'] for r in rows())
 while not destroyed() and time.monotonic()<deadline:time.sleep(.02)
 check('close-releases-native-editor',destroyed(),native_press=press)
 m.command('WebDriver:SwitchToWindow',dict(handle=first));m.command('WebDriver:ReleaseActions')
 check('first-window-model-retained',state()['value']=='First',state=state())
 js("document.getElementById('urlbar-input').focus();return true")
 key('\ue010');key('X');check('first-window-address-editor-still-usable',state()['value']=='FirstX',state=state())
 press=held();helper=launch['pids'][1];argv=Path('/proc',str(helper),'cmdline').read_bytes().split(bytes([0]));runtime=json.loads((root/'runtime.json').read_text())
 assert any(v.endswith(b'/Experiments/ChromiumScrollers/helper.py') for v in argv) and (runtime['XDG_RUNTIME_DIR']+'/native.sock').encode() in argv
 os.kill(helper,signal.SIGKILL)
 m.command('WebDriver:ReleaseActions');key('X');check('typing-after-held-helper-loss',state()==dict(value='Xha beta',start=1,end=1),state=state(),helper=helper,native_press=press)
 print(json.dumps(dict(passed=len(results))))
finally:m.close()
