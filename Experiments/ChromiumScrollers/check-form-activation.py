#!/usr/bin/env python3
"""Qualify original-engine transactions driven by actual native button state."""
import argparse,json,re,socket,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Tests/Wayland'))
from form_activation import FormFixture,run

parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--fixture',type=Path,required=True)
options=parser.parse_args();root=options.fixture.resolve();rows=[]
def command(text):
 with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as connection:
  connection.settimeout(25);connection.connect(str(root/'control.sock'));connection.send(json.dumps(dict(command=text)).encode());return json.loads(connection.recv(1024*1024))
def check(case,passed,**data):
 rows.append(dict(case=case,passed=bool(passed),**data));(root/'form-results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
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
url=Path(__file__).resolve().parents[2].joinpath('Tests/Wayland/native-form-activation.html').as_uri()
reset_serial=0
def reset():
 global reset_serial;reset_serial+=1
 js('window.__resetPending=true;return true');cdp('Page.navigate',dict(url=url+'?case='+str(reset_serial)))
 fixture.wait(lambda:js("return document.readyState==='complete'&&!!window.events&&!window.__resetPending"));time.sleep(.15)
def window():return next(w for w in command('windows') if w['pid']==pid and w['level']==0)
def origin():
 w=window();inside=js('return {height:innerHeight,scale:devicePixelRatio}');assert inside['scale']==1
 return [w['x']+(w['frame_left'] if w['server_decorated'] else 0),w['y']+(w['frame_top'] if w['server_decorated'] else 0)+w['surface_height']-inside['height']]
fixture=FormFixture(root,command,js,check,pid,origin,reset)
try:
 fixture.wait(window);assert command('focus '+str(window()['id']))['ok']
 reset();run(fixture)
 print(json.dumps(dict(passed=len(rows))),flush=True)
finally:
 command('button 272 0');cdp('Target.detachFromTarget',dict(sessionId=session),False)
