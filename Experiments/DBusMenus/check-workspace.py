#!/usr/bin/env python3
"""Verify real Workspace focus/address association against an owned Firefox."""
import argparse,json,os,signal,socket,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'FirefoxNativeUI'))
from marionette import Marionette
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--fixture',type=Path,required=True);p.add_argument('--port',type=int,required=True)
p.add_argument('--expected-pid',type=int,required=True);p.add_argument('--output',type=Path,required=True)
p.add_argument('--backend',required=True);p.add_argument('--native-text-app',type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);rows=[];native_app=None;second_handle=None;m=Marionette(a.port)
host=json.loads((a.fixture/'menu-binding.json').read_text());launch=json.loads((a.fixture/'launch.json').read_text())
shell=json.loads((a.fixture/'menu-shell-launch.json').read_text())
assert host['association']=='workspace' and host['owner']==a.expected_pid==launch['pids'][-1]
assert shell['pid'] in launch['pids'] and host['pid'] in launch['pids']
def check(case,passed,**data):
 rows.append(dict(case=case,passed=bool(passed),**data));(a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
def control(command):
 with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:
  s.settimeout(15);s.connect(str(a.fixture/'control.sock'));s.send(json.dumps(dict(command=command)).encode());return json.loads(s.recv(65536))
def wait(read,predicate):
 end=time.monotonic()+10
 while True:
  value=read()
  if predicate(value):return value
  assert time.monotonic()<end,value
  time.sleep(.015)
def trace():return [json.loads(l) for l in Path(host['log']).read_text().splitlines()]
def bound():return [r for r in trace() if r['event']=='dbus-menu-bound']
def roots():return [w for w in control('windows') if w['pid']==host['pid'] and w['visible']]
def browser_windows():return [w for w in control('windows') if w['pid']==a.expected_pid]
def js(script):return m.command('WebDriver:ExecuteScript',dict(script=script,args=[]))['value']
def select_window(identifier):
 before=len(bound());assert control('focus '+str(identifier))['ok']
 wait(bound,lambda rs:rs and rs[-1]['window']==identifier)
 wait(roots,lambda ws:len(ws)==1)
 return before

def new_tab(label,identifier):
 path=a.fixture/'shared-menus'/str(identifier)/'native-items.json'
 items=wait(lambda:json.loads(path.read_text()) if path.exists() else [],lambda rs:any(i['title']=='New Tab' for i in rs))
 token=next(i['command'] for i in items if i['title']=='New Tab')
 # Current adapter forwards native field keys. Page-body/global shortcuts are
 # a separate recorded coverage gap; this check exercises window association.
 js('gURLBar.inputField.focus();return true')
 before=js('return gBrowser.tabs.length');start=len(trace())
 for command in ['key 56 1','key 20 1','key 20 0','key 56 0']:assert control(command)['ok']
 after=wait(lambda:js('return gBrowser.tabs.length'),lambda n:n==before+1)
 events=trace()[start:]
 check(label+'-native-shortcut-creates-one-tab',after==before+1)
 check(label+'-routes-once-through-real-application-menu',sum(r['event']=='application-command-queued' and r.get('native')==token for r in events)==1 and sum(r['event']=='application-command' and r.get('native')==token for r in events)==1)
try:
 session=m.command('WebDriver:NewSession',{});check('owned-browser',session['capabilities']['moz:processID']==a.expected_pid)
 m.command('Marionette:SetContext',dict(value='chrome'))
 first_handle=m.command('WebDriver:GetWindowHandles')[0];m.command('WebDriver:SwitchToWindow',dict(handle=first_handle))
 first=host['window'];select_window(first)
 check('workspace-automatically-binds-real-browser-window',bound()[-1]['window']==first)
 check('native-root-is-existing-helper-window',roots()[0]['level']==20 and not roots()[0]['accepts_focus'])
 new_tab('first-window',first)
 existing={w['id'] for w in browser_windows()}
 second_handle=m.command('WebDriver:NewWindow',dict(type='window'))['handle']
 m.command('WebDriver:SwitchToWindow',dict(handle=second_handle))
 second=wait(browser_windows,lambda ws:len(ws)==len(existing)+1)
 second=next(w['id'] for w in second if w['id'] not in existing);select_window(second)
 check('workspace-follows-second-browser-window',bound()[-1]['window']==second)
 new_tab('second-window',second)
 m.command('WebDriver:SwitchToWindow',dict(handle=first_handle));select_window(first)
 new_tab('return-to-first',first)
 start=len(bound());assert control('move '+str(first)+' 90 80')['ok']
 time.sleep(.15)
 check('geometry-update-does-not-recreate-native-menu',len(bound())==start)
 runtime=dict(os.environ,**json.loads((a.fixture/'runtime.json').read_text()));runtime.pop('LD_PRELOAD',None)
 source=a.output/'native-document.txt';source.write_text('Native application focus fixture\n')
 log=(a.output/'native-app.log').open('w')
 native_app=subprocess.Popen([str(a.native_text_app),'-NSUseRunningCopy','NO','-GSBackend',a.backend,'-NSOpen',str(source)],env=runtime,stdout=log,stderr=log)
 native=wait(lambda:control('windows'),lambda ws:any(w['pid']==native_app.pid and w['accepts_focus'] for w in ws))
 native=next(w for w in native if w['pid']==native_app.pid and w['accepts_focus'])
 assert control('focus '+str(native['id']))['ok']
 wait(roots,lambda ws:not ws)
 check('native-application-focus-clears-foreign-menu',not roots())
 check('menu-removal-preserves-shared-control-helper',Path('/proc',str(host['pid'])).exists())
 assert control('focus '+str(first))['ok'];select_window(first)
 check('browser-focus-restores-its-native-menu',bool(roots()))
 new_tab('after-native-app',first)
 os.kill(shell['pid'],signal.SIGTERM)
 wait(roots,lambda ws:not ws)
 check('workspace-role-loss-clears-native-menu',not roots())
 check('workspace-role-loss-preserves-control-helper',Path('/proc',str(host['pid']),'stat').read_text().rsplit(') ',1)[1].split()[0] not in ['Z','X'])
 check('no-menu-callback-errors',not [r for r in trace() if r['event'] in ['callback-error','native-submenu-error','application-error','layout-error']])
 print(json.dumps(dict(passed=len(rows))))
finally:
 control('key 56 0')
 if second_handle is not None:
  m.command('WebDriver:SwitchToWindow',dict(handle=second_handle));m.command('WebDriver:CloseWindow')
 m.close()
 if native_app:
  if native_app.poll() is None:
   native_app.terminate()
   try:native_app.wait(timeout=5)
   except subprocess.TimeoutExpired:native_app.kill();native_app.wait()
  (a.output/'native-app-cleanup.json').write_text(json.dumps(dict(pid=native_app.pid,exit=native_app.returncode))+'\n')
