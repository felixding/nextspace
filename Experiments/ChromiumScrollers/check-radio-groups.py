#!/usr/bin/env python3
"""Qualify native matrices in an owned pinned Chromium fixture."""
import argparse,json,socket,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Tests/Wayland'))
from radio_groups import RadioFixture,run
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fixture',type=Path,required=True);a=p.parse_args();root=a.fixture.resolve();rows=[]
def command(text):
 with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:
  s.settimeout(25);s.connect(str(root/'control.sock'));s.send(json.dumps(dict(command=text)).encode());return json.loads(s.recv(1048576))
def check(case,passed,**data):
 rows.append(dict(case=case,passed=bool(passed),**data));(root/'radio-results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
def cdp(method,params=None,target=True):
 request=dict(method=method,params=params or {})
 if target:request['sessionId']=session
 reply=command('cdp '+json.dumps(request));assert 'error' not in reply,reply;return reply['result']
def js(script):
 reply=cdp('Runtime.evaluate',dict(expression='(function(){'+script+'}).call(window)',returnByValue=True,awaitPromise=True));assert 'exceptionDetails' not in reply,reply;return reply['result'].get('value')
pid=json.loads((root/'launch.json').read_text())['pids'][-1]
page=next(t for t in cdp('Target.getTargets',target=False)['targetInfos'] if t['type']=='page');session=cdp('Target.attachToTarget',dict(targetId=page['targetId'],flatten=True),False)['sessionId'];cdp('Page.enable')
url=Path(__file__).resolve().parents[2].joinpath('Tests/Wayland/native-radio-groups.html').as_uri()
def reset():
 js('window.__resetPending=true;return true');cdp('Page.navigate',dict(url=url));fixture.wait(lambda:js("return document.readyState==='complete'&&!window.__resetPending"))
def window():return next(w for w in command('windows') if w['pid']==pid and w['level']==0)
def origin():
 w=window();inside=js('return {height:innerHeight,scale:devicePixelRatio}');assert inside['scale']==1
 return [w['x']+(w['frame_left'] if w['server_decorated'] else 0),w['y']+(w['frame_top'] if w['server_decorated'] else 0)+w['surface_height']-inside['height']]
def identify(identifier,shadow=False):
 expression=("document.getElementById('shadow-host').shadowRoot" if shadow else 'document')+'.getElementById('+json.dumps(identifier)+')'
 obj=cdp('Runtime.evaluate',dict(expression=expression))['result']['objectId']
 try:return cdp('DOM.describeNode',dict(objectId=obj))['node']['backendNodeId']
 finally:cdp('Runtime.releaseObject',dict(objectId=obj))
fixture=RadioFixture(root,command,js,check,pid,origin,reset);fixture.identify=identify
try:
 fixture.wait(window);assert command('focus '+str(window()['id']))['ok'];run(fixture)
 print(json.dumps(dict(passed=len(rows),native_images=sum('pixels' in row['case'] for row in rows))))
finally:
 command('button 272 0');command('key 42 0');cdp('Target.detachFromTarget',dict(sessionId=session),False)
