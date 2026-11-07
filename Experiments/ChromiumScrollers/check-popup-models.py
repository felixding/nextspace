#!/usr/bin/env python3
"""Qualify the same native option models in an owned Chromium CDP-pipe fixture."""
import argparse,json,re,socket,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Tests/Wayland'))
from native_popup_fixture import PopupFixture
from popup_models import run

parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--fixture',type=Path,required=True)
options=parser.parse_args();root=options.fixture.resolve();rows=[]
def command(text):
 with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as connection:
  connection.settimeout(25);connection.connect(str(root/'control.sock'));connection.send(json.dumps(dict(command=text)).encode());return json.loads(connection.recv(1024*1024))
def check(case,passed,**data):
 rows.append(dict(case=case,passed=bool(passed),**data));(root/'popup-results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
def cdp(method,params=None,target=True):
 request=dict(method=method,params=params or {})
 if target:request['sessionId']=session
 reply=command('cdp '+json.dumps(request));assert 'error' not in reply,reply;return reply['result']
def js(script):
 reply=cdp('Runtime.evaluate',dict(expression='(function(){'+script+'}).call(window)',returnByValue=True,awaitPromise=True))
 assert 'exceptionDetails' not in reply,reply;return reply['result'].get('value')
launch=json.loads((root/'launch.json').read_text());pid=launch['pids'][-1];assert launch['engine']=='chromium'
page=next(t for t in cdp('Target.getTargets',target=False)['targetInfos'] if t['type']=='page')
session=cdp('Target.attachToTarget',dict(targetId=page['targetId'],flatten=True),False)['sessionId']
cdp('Page.enable')
url=Path(__file__).with_name('test-popups.html').resolve().as_uri()
def reset():
 js('window.__resetPending=true;return true');cdp('Page.navigate',dict(url=url))
 fixture.wait(lambda:js("return document.readyState==='complete'&&!!window.events&&!window.__resetPending"));time.sleep(.15)
def window():return next(w for w in command('windows') if w['pid']==pid and w['level']==0)
def origin():
 w=window();inside=js('return {height:innerHeight,scale:devicePixelRatio}');assert inside['scale']==1
 return [w['x']+(w['frame_left'] if w['server_decorated'] else 0),w['y']+(w['frame_top'] if w['server_decorated'] else 0)+w['surface_height']-inside['height']]
fixture=PopupFixture(root,command,js,check,pid,origin,reset)
try:
 fixture.wait(window);assert command('focus '+str(window()['id']))['ok'];command('pointer 1500 1100');reset()
 check('owned-pinned-chromium-document',js('return document.title')=='Native select model transport')
 fixture.pixels('select');fixture.pixels('empty');fixture.pixels('select',True)
 fixture.focus();fixture.key(57);fixture.wait(fixture.state,lambda s:s['open']);check('real-native-menu-window',bool(fixture.wait(fixture.native_menu)))
 fixture.key(108);fixture.key(28);state=fixture.wait(fixture.state,lambda s:not s['open'])
 check('native-key-commits-original-option',state['index']==1 and state['value']=='b',actual=state)
 check('one-trusted-native-input-change',[e['type'] for e in state['changes']]==['input','change'] and all(e['trusted'] for e in state['changes']))
 run(fixture,indent='    ',collapse_hr=False)
 trace=(root/'hook.log').read_text()
 check('browser-owned-ui-preserved','browser-owned tabs, address bar and toolbar preserved' in trace and
  'experimental native browser tabs enabled' not in trace and 'experimental native address-bar fields enabled' not in trace and
  not re.search(r'^views-state ',trace,re.M))
 print(json.dumps(dict(passed=len(rows))),flush=True)
finally:
 command('button 272 0')
 cdp('Target.detachFromTarget',dict(sessionId=session),False)
