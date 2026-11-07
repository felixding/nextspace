#!/usr/bin/env python3
"""Qualify shared native button layout/actions in an owned Gecko fixture."""
import argparse,json,re,socket,sys,time
from pathlib import Path
from marionette import Marionette
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Tests/Wayland'))
from button_sizing import ButtonFixture,run as buttons
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--fixture',type=Path,required=True);p.add_argument('--port',type=int,default=2835)
p.add_argument('--text-regression',action='store_true')
a=p.parse_args();root=a.fixture.resolve();rows=[]
def command(text):
 with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:
  s.settimeout(25);s.connect(str(root/'control.sock'));s.send(json.dumps(dict(command=text)).encode());return json.loads(s.recv(1048576))
def check(case,passed,**data):
 rows.append(dict(case=case,passed=bool(passed),**data));(root/'button-results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
deadline=time.monotonic()+30
while True:
 try:m=Marionette(a.port);break
 except ConnectionRefusedError:
  if time.monotonic()>=deadline:raise
  time.sleep(.05)
launch=json.loads((root/'launch.json').read_text());pid=launch['pids'][-1];assert launch['engine']=='firefox'
def js(script):return m.command('WebDriver:ExecuteScript',dict(script=script,args=[]))['value']
origin=lambda:js('return [mozInnerScreenX,mozInnerScreenY]')
f=ButtonFixture(root,command,js,check,pid,origin,lambda:None)
try:
 session=m.command('WebDriver:NewSession',{});assert session['capabilities']['moz:processID']==pid
 window=f.wait(lambda:next((w for w in command('windows') if w['pid']==pid and w['level']==0),None));assert command('focus '+str(window['id']))['ok']
 m.command('WebDriver:Navigate',dict(url=Path(__file__).resolve().parent.parent.joinpath('ChromiumScrollers/test-button-sizing.html').as_uri()))
 f.wait(lambda:js("return document.readyState==='complete'&&document.title==='Native button sizing'"));buttons(f)
 if a.text_regression:
  m.command('WebDriver:Navigate',dict(url=Path(__file__).resolve().parent.parent.joinpath('ChromiumScrollers/test-text.html').as_uri()))
  f.wait(lambda:js("return document.readyState==='complete'&&document.title==='Blink native text transport'"))
  from form_text_regression import TextFixture,run as text_checks
  out=root/'text-regression';out.mkdir();text_checks(TextFixture(out,command,js,check,pid,origin,lambda:None))
 trace=(root/'hook.log').read_text();parent=[line for line in trace.splitlines() if re.match(str(pid)+r' native-(?:text |button |widget |widget bound|select )',line)]
 check('browser-owned-ui-preserved',not parent and 'experimental native Gecko tab container installed' not in trace and 'native Gecko frontend text binding installed' not in trace,parent_native_widgets=parent)
 print(json.dumps(dict(passed=len(rows),native_images=sum('pixels' in x['case'] for x in rows))),flush=True)
finally:command('button 272 0');m.close()
