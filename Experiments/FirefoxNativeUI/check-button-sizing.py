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
p.add_argument('--text-types-only',action='store_true',help='Run shared URL/telephone native text checks')
p.add_argument('--email-only',action='store_true',help='Run native email editing and protected selection checks')
p.add_argument('--search-only',action='store_true',help='Run real GNUstep search-field checks')
p.add_argument('--search-actions-only',action='store_true',help='Compare native search activation with original form actions')
p.add_argument('--search-clear-only',action='store_true',help='Check native clear actions after cancellable click dispatch')
p.add_argument('--colors-only',action='store_true',help='Check native color fields and picker callback ownership')
p.add_argument('--placeholders-only',action='store_true',help='Check original native field placeholders')
p.add_argument('--search-notifications-only',action='store_true',help='Compare native clear search events with the original engine')
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
 if not (a.text_types_only or a.email_only or a.search_only or a.search_actions_only or a.search_clear_only or a.search_notifications_only or a.placeholders_only or a.colors_only):
  m.command('WebDriver:Navigate',dict(url=Path(__file__).resolve().parent.parent.joinpath('ChromiumScrollers/test-button-sizing.html').as_uri()))
  f.wait(lambda:js("return document.readyState==='complete'&&document.title==='Native button sizing'"));buttons(f)
 if a.colors_only:
  m.command('WebDriver:Navigate',dict(url=Path(__file__).resolve().parents[2].joinpath('Tests/Wayland/native-color-fields.html').as_uri()))
  f.wait(lambda:js("return document.readyState==='complete'&&document.title==='Native color fields'"))
  from native_color_fields import ColorFixture,run as color_checks
  out=root/'colors';out.mkdir();color_checks(ColorFixture(out,command,js,check,pid,origin,lambda:None))
 if a.text_regression:
  m.command('WebDriver:Navigate',dict(url=Path(__file__).resolve().parent.parent.joinpath('ChromiumScrollers/test-text.html').as_uri()))
  f.wait(lambda:js("return document.readyState==='complete'&&document.title==='Blink native text transport'"))
  from form_text_regression import TextFixture,run as text_checks
  out=root/'text-regression';out.mkdir();text_checks(TextFixture(out,command,js,check,pid,origin,lambda:None))
 if a.text_types_only:
  m.command('WebDriver:Navigate',dict(url=Path(__file__).resolve().parents[2].joinpath('Tests/Wayland/native-text-types.html').as_uri()))
  f.wait(lambda:js("return document.readyState==='complete'&&document.title==='Native text field types'"))
  from form_text_regression import TextFixture
  from native_text_types import run as type_checks
  out=root/'text-types';out.mkdir();type_checks(TextFixture(out,command,js,check,pid,origin,lambda:None))
 if a.email_only:
  m.command('WebDriver:Navigate',dict(url=Path(__file__).resolve().parents[2].joinpath('Tests/Wayland/native-email-fields.html').as_uri()))
  f.wait(lambda:js("return document.readyState==='complete'&&document.title==='Native email fields'"))
  from native_email_fields import EmailFixture,run as email_checks
  out=root/'email';out.mkdir();email_checks(EmailFixture(out,command,js,check,pid,origin,lambda:None))
 if a.search_only:
  m.command('WebDriver:Navigate',dict(url=Path(__file__).resolve().parents[2].joinpath('Tests/Wayland/native-search-fields.html').as_uri()))
  f.wait(lambda:js("return document.readyState==='complete'&&document.title==='Native search fields'"))
  from native_search_fields import SearchFixture,run as search_checks
  out=root/'search';out.mkdir();search_checks(SearchFixture(out,command,js,check,pid,origin,lambda:None))
 if a.search_actions_only:
  m.command('WebDriver:Navigate',dict(url=Path(__file__).resolve().parents[2].joinpath('Tests/Wayland/native-search-actions.html').as_uri()))
  f.wait(lambda:js("return document.readyState==='complete'&&document.title==='Native search actions'"))
  from native_search_fields import SearchFixture
  from native_search_actions import run as search_actions
  out=root/'search-actions';out.mkdir();search_actions(SearchFixture(out,command,js,check,pid,origin,lambda:None))
 if a.search_clear_only:
  m.command('WebDriver:Navigate',dict(url=Path(__file__).resolve().parents[2].joinpath('Tests/Wayland/native-search-actions.html').as_uri()))
  f.wait(lambda:js("return document.readyState==='complete'&&document.title==='Native search actions'"))
  from native_search_fields import SearchFixture
  from native_search_clear_actions import run as clear_actions
  out=root/'search-clear';out.mkdir();clear_actions(SearchFixture(out,command,js,check,pid,origin,lambda:None))
 if a.search_notifications_only:
  m.command('WebDriver:Navigate',dict(url=Path(__file__).resolve().parents[2].joinpath('Tests/Wayland/native-search-notifications.html').as_uri()))
  f.wait(lambda:js("return document.readyState==='complete'&&document.title==='Native search notifications'"))
  from native_search_fields import SearchFixture
  from native_search_notifications import run as notification_checks
  out=root/'search-notifications';out.mkdir();notification_checks(SearchFixture(out,command,js,check,pid,origin,lambda:None))
 if a.placeholders_only:
  m.command('WebDriver:Navigate',dict(url=Path(__file__).resolve().parents[2].joinpath('Tests/Wayland/native-placeholders.html').as_uri()))
  f.wait(lambda:js("return document.readyState==='complete'&&document.title==='Native field placeholders'"))
  from native_placeholders import PlaceholderFixture,run as placeholder_checks
  out=root/'placeholders';out.mkdir();placeholder_checks(PlaceholderFixture(out,command,js,check,pid,origin,lambda:None))
 trace=(root/'hook.log').read_text();parent=[line for line in trace.splitlines() if re.match(str(pid)+r' native-(?:text |button |widget |widget bound|select )',line)]
 check('browser-owned-ui-preserved',not parent and 'experimental native Gecko tab container installed' not in trace and 'native Gecko frontend text binding installed' not in trace,parent_native_widgets=parent)
 print(json.dumps(dict(passed=len(rows),native_images=sum('pixels' in x['case'] for x in rows))),flush=True)
finally:command('button 272 0');m.close()
