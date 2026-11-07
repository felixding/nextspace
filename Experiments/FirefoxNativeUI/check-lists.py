#!/usr/bin/env python3
"""Qualify shared native lists in the unchanged pinned Gecko engine."""
import argparse,json,re,socket,sys,time
from pathlib import Path
from marionette import Marionette
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Tests/Wayland'))
from native_lists import ListFixture,run
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--fixture',type=Path,required=True);p.add_argument('--port',type=int,default=2835)
p.add_argument('--ordinary-probe',type=Path,required=True)
p.add_argument('--only-list',action='store_true',help='Focus the only control during parsing, before first paint')
p.add_argument('--scroll',action='store_true',help='Qualify native overflowing list layout and scroll ownership')
p.add_argument('--hit-targets',action='store_true',help='Also require native row identities for original DOM pointer targets')
a=p.parse_args();root=a.fixture.resolve();rows=[]
def command(text):
 with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:
  s.settimeout(25);s.connect(str(root/'control.sock'));s.send(json.dumps(dict(command=text)).encode());return json.loads(s.recv(1048576))
def check(case,passed,**data):
 rows.append(dict(case=case,passed=bool(passed),**data));(root/('list-scroll-results.json' if a.scroll else 'list-results.json')).write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
deadline=time.monotonic()+30
while True:
 try:m=Marionette(a.port);break
 except ConnectionRefusedError:
  if time.monotonic()>=deadline:raise
  time.sleep(.05)
launch=json.loads((root/'launch.json').read_text());pid=launch['pids'][-1];assert launch['engine']=='firefox'
def js(script):return m.command('WebDriver:ExecuteScript',dict(script=script,args=[]))['value']
def reset():
 url=Path(__file__).resolve().parents[2].joinpath('Tests/Wayland/native-listboxes.html').as_uri()
 m.command('WebDriver:Navigate',dict(url=url+'?case=scroll'+('&only=1' if a.only_list else '')+('&rows=24' if a.scroll else '')))
 f.wait(lambda:js('return document.readyState==="complete"&&!!document.getElementById("list")'))
f=ListFixture(root,command,js,check,pid,lambda:js('return [mozInnerScreenX,mozInnerScreenY]'),reset)
f.ordinary_probe=a.ordinary_probe
f.require_native_hit=a.hit_targets
try:
 session=m.command('WebDriver:NewSession',{});assert session['capabilities']['moz:processID']==pid
 window=f.wait(lambda:next((w for w in command('windows') if w['pid']==pid and w['level']==0),None));assert command('focus '+str(window['id']))['ok']
 if a.scroll:
  from native_list_scroll import run as run_scroll
  run_scroll(f)
 else:run(f)
 trace=(root/'hook.log').read_text();parent=[line for line in trace.splitlines() if re.match(str(pid)+r' native-(?:text |button |widget |widget bound|select |list )',line)]
 check('browser-owned-ui-preserved',not parent and 'experimental native Gecko tab container installed' not in trace and 'native Gecko frontend text binding installed' not in trace,parent_native_widgets=parent)
 print(json.dumps(dict(passed=len(rows),native_images=sum('pixels' in row['case'] for row in rows))),flush=True)
finally:command('button 272 0');m.close()
