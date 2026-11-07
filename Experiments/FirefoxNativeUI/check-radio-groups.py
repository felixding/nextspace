#!/usr/bin/env python3
"""Exercise original Gecko group transactions through shared native matrices."""
import argparse,json,socket,sys,time
from pathlib import Path
from marionette import Marionette
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Tests/Wayland'))
from radio_groups import RadioFixture,run
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--port',type=int,default=2833);a=p.parse_args();root=a.fixture.resolve();rows=[];model_start=0
deadline=time.monotonic()+30
while True:
 try:m=Marionette(a.port);break
 except ConnectionRefusedError:
  if time.monotonic()>=deadline:raise
  time.sleep(.05)
def command(text):
 with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:
  s.settimeout(25);s.connect(str(root/'control.sock'));s.send(json.dumps(dict(command=text)).encode());return json.loads(s.recv(1048576))
def js(script):return m.command('WebDriver:ExecuteScript',dict(script=script,args=[]))['value']
def check(case,passed,**data):
 rows.append(dict(case=case,passed=bool(passed),**data));(root/'radio-results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
def reset():
 global model_start
 model_start=len((root/'hook.log').read_text())
 m.command('WebDriver:Navigate',dict(url=Path(__file__).resolve().parents[2].joinpath('Tests/Wayland/native-radio-groups.html').as_uri()))
 fixture.wait(lambda:js("return document.readyState==='complete'&&document.title==='Native radio groups'"))
def identify(identifier,shadow=False):
 encoded=identifier.encode().hex()
 def found():
  lines=(root/'hook.log').read_text()[model_start:].splitlines()
  for line in reversed(lines):
   if line.startswith('{') and line.endswith('}'):
    row=json.loads(line)
    if row.get('event')=='native-radio-model':
     for node in row.get('nodes',[]):
      if node['dom_id_hex']==encoded:return node['id']
  return None
 return fixture.wait(found)
pid=json.loads((root/'launch.json').read_text())['pids'][-1]
fixture=RadioFixture(root,command,js,check,pid,lambda:js('return [mozInnerScreenX,mozInnerScreenY]'),reset)
fixture.identify=identify;fixture.reinsert_recreates_group=False
try:
 session=m.command('WebDriver:NewSession',{});assert session['capabilities']['moz:processID']==pid
 window=fixture.wait(lambda:next((w for w in command('windows') if w['pid']==pid and w['level']==0),None));assert command('focus '+str(window['id']))['ok']
 run(fixture);print(json.dumps(dict(passed=len(rows),native_images=sum('pixels' in x['case'] for x in rows))))
finally:
 command('button 272 0');command('key 42 0');m.close()
