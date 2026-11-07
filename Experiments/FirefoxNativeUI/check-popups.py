#!/usr/bin/env python3
"""Native single-select controls, engine option models and desktop geometry."""
import argparse,json,re,socket,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from marionette import Marionette
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Tests/Wayland'))
from native_popup_fixture import PopupFixture
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--fixture',type=Path,required=True)
parser.add_argument('--port',type=int,default=2833)
parser.add_argument('--geometry',action='store_true')
parser.add_argument('--models',action='store_true')
parser.add_argument('--sizing',action='store_true')
options=parser.parse_args();root=options.fixture.resolve();results=[]
def command(text):
 with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as c:
  c.settimeout(20);c.connect(str(root/'control.sock'));c.send(json.dumps(dict(command=text)).encode());return json.loads(c.recv(65536))
m=Marionette(options.port)
def js(s):return m.command('WebDriver:ExecuteScript',dict(script=s,args=[]))['value']
def check(case,okay,**data):
 results.append(dict(case=case,passed=bool(okay),**data));(root/'popup-results.json').write_text(json.dumps(results,indent=2)+'\n');assert okay,results[-1]
def wait(fn,okay=lambda x:x):
 end=time.monotonic()+8;v=None
 while time.monotonic()<end:
  v=fn()
  if okay(v):return v
  time.sleep(.05)
 raise AssertionError(v)
def reset():
 m.command('WebDriver:Navigate',dict(url=(Path(__file__).resolve().parent.parent/'ChromiumScrollers/test-popups.html').as_uri()));wait(lambda:js("return document.readyState==='complete'&&!!window.events"));time.sleep(.15)
pid=json.loads((root/'launch.json').read_text())['pids'][-1]
fixture=PopupFixture(root,command,js,check,pid,lambda:js('return [mozInnerScreenX,mozInnerScreenY]'),reset)
key,state,focus,image,pixels=fixture.key,fixture.state,fixture.focus,fixture.image,fixture.pixels
native_menu,highlight,model_geometry=fixture.native_menu,fixture.highlight,fixture.model_geometry
def window():return next(w for w in command('windows') if w['pid']==pid)
def origin():
 content=js("return {x:mozInnerScreenX,y:mozInnerScreenY}")
 m.command('Marionette:SetContext',dict(value='chrome'))
 try:r=js("return gBrowser.selectedBrowser.getBoundingClientRect().toJSON()")
 finally:m.command('Marionette:SetContext',dict(value='content'))
 w=window();return content,dict(x=w['x']+(w['frame_left'] if w['server_decorated'] else 0)+r['x'],y=w['y']+(w['frame_top'] if w['server_decorated'] else 0)+r['y'])
def correct_origin():
 a,b=origin();return abs(a['x']-b['x'])<.01 and abs(a['y']-b['y'])<.01
def open_at_owner(name):
 # Firefox's existing fullscreen toolbar animates. A fixed-position assertion
 # samples settled owner geometry; live movement while open is a separate case.
 previous=None;since=time.monotonic()
 def settled():
  nonlocal previous,since
  current=js("const r=document.getElementById('select').getBoundingClientRect();return [mozInnerScreenX+r.x,mozInnerScreenY+r.y]")
  if current!=previous:previous=current;since=time.monotonic()
  return time.monotonic()-since>.25
 wait(settled)
 focus();key(57);wait(state,lambda s:s['open']);menu=wait(native_menu)
 a=js("const r=document.getElementById('select').getBoundingClientRect();return {x:mozInnerScreenX+r.x,y:mozInnerScreenY+r.y}")
 check(name+'-native-anchor',menu['x']==round(a['x'])-1 and menu['y']==round(a['y'])-1,menu=menu,anchor=a);image(name);key(1);wait(state,lambda s:not s['open'])
try:
 pid=json.loads((root/'launch.json').read_text())['pids'][-1];s=m.command('WebDriver:NewSession',{});check('owned-pinned-firefox',s['capabilities']['moz:processID']==pid)
 reset();command('pointer 1500 1100')
 for identifier in ['select','disabled','empty']:pixels(identifier)
 pixels('select',True)
 focus();key(57);check('native-key-open',wait(state,lambda x:x['open'])['open']);image('native-open')
 menu=next(w for w in command('windows') if w['pid']!=pid and w['level']==101 and w['visible']);check('native-menu-surface-visible',menu['width']>0 and menu['height']>0,menu=menu)
 anchor=js("const r=document.getElementById('select').getBoundingClientRect();return {x:mozInnerScreenX+r.x,y:mozInnerScreenY+r.y}")
 check('native-menu-exact-owner-anchor',menu['x']==round(anchor['x'])-1 and menu['y']==round(anchor['y'])-1,anchor=anchor,menu=menu)
 key(108);key(28);s=wait(state,lambda x:x['index']==1 and not x['open']);check('native-key-commits-real-option',s['value']=='b',actual=s);check('one-trusted-input-change',[x['type'] for x in s['changes']]==['input','change'] and all(x['trusted'] for x in s['changes']))
 pixels('select',True)
 js('window.events=[];return true');key(57);key(108);key(1);s=wait(state,lambda x:not x['open']);check('escape-cancels-selection',s['index']==1 and not s['changes'],actual=s)
 reset();focus();js("document.getElementById('select').addEventListener('keydown',e=>e.preventDefault());return true");key(57);time.sleep(.15);check('cancelled-key-no-native-menu',not state()['open'])
 reset();focus();js("document.getElementById('select').dispatchEvent(new KeyboardEvent('keydown',{key:' ',bubbles:true,cancelable:true}));return true");check('untrusted-key-no-native-menu',not state()['open'])
 reset();focus();key(57);wait(state,lambda x:x['open']);js("document.getElementById('select').options[1].replaceWith(new Option('Replacement','replacement'));return true");key(108);key(28);s=wait(state,lambda x:not x['open']);check('stale-option-identity-rejected',s['value']=='a' and not s['changes'],actual=s)
 reset();focus();key(57);wait(state,lambda x:x['open']);js("document.getElementById('select').remove();return true");time.sleep(.15);check('remove-open-control-closes-native-menu',not any(w['level']==101 and w['visible'] for w in command('windows')))
 reset();focus();js("document.getElementById('select').addEventListener('input',e=>e.target.remove(),{once:true});return true");key(57);key(108);key(28);check('reentrant-input-removes-control',wait(lambda:js("return !document.getElementById('select')")))
 reset();focus();key(57);wait(state,lambda x:x['open']);js("document.getElementById('select').blur();return true");check('blur-closes-native-menu',wait(lambda:not state()['open'] and not any(w['level']==101 and w['visible'] for w in command('windows'))))
 if options.geometry:
  m.command('WebDriver:SetWindowRect',dict(x=0,y=0,width=1280,height=1040));wait(lambda:not window()['fullscreen']);reset()
  check('initial-independent-content-origin',wait(correct_origin),actual=origin());open_at_owner('initial')
  check('move-request',command(f"move {window()['id']} 140 80")['ok']);check('moved-independent-content-origin',wait(correct_origin),actual=origin());open_at_owner('moved')
  m.command('WebDriver:FullscreenWindow',{});wait(lambda:window()['fullscreen']);check('fullscreen-independent-content-origin',wait(correct_origin),actual=origin());open_at_owner('fullscreen')
  m.command('WebDriver:SetWindowRect',dict(x=140,y=80,width=1000,height=800));wait(lambda:not window()['fullscreen']);check('restored-independent-content-origin',wait(correct_origin),actual=origin());open_at_owner('restored')
  # Native menu receives real seat motion/release while the engine owns trusted
  # select activation. The native item rectangles come from the direct provider.
  reset();command('pointer 1500 1100');focus()
  a=js("const r=document.getElementById('select').getBoundingClientRect();return {x:mozInnerScreenX+r.x,y:mozInnerScreenY+r.y,width:r.width,height:r.height}")
  command(f"pointer {round(a['x']+a['width']/2)} {round(a['y']+a['height']/2)}");command('button 272 1');wait(state,lambda s:s['open']);menu=wait(native_menu);check('real-pointer-opens-native-menu',True)
  image('pointer-open')
  item=json.loads((root/'select-normal-reference/results.json').read_text())[0]['native_item_rects'][1]
  command(f"pointer {round(a['x']+item['x']+item['width']/2)} {round(a['y']+item['y']+item['height']/2)}");time.sleep(.1);command('button 272 0')
  s=wait(state,lambda s:not s['open']);check('native-pointer-choice-real-model',s['index']==1 and [x['type'] for x in s['changes']]==['input','change'] and all(x['trusted'] for x in s['changes']),actual=s)
  pixels('select',True);image('pointer-committed')
 if options.models:
  sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Tests/Wayland'))
  from popup_models import run
  run(fixture)
 if options.sizing:
  m.command('WebDriver:Navigate',dict(url=Path(__file__).resolve().parent.parent.joinpath('ChromiumScrollers/test-select-sizing.html').as_uri()))
  wait(lambda:js("return document.readyState==='complete'&&document.title==='Native select sizing'"))
  from popup_sizing import run
  run(fixture)
 trace=(root/'hook.log').read_text()
 parent_bindings=[line for line in trace.splitlines() if re.match(str(pid)+r" native-(?:text |button |widget |widget bound|select )",line)]
 check('browser-owned-ui-preserved',not parent_bindings and 'experimental native Gecko tab container installed' not in trace and 'native Gecko frontend text binding installed' not in trace,parent_native_widgets=parent_bindings)
 print(json.dumps(dict(passed=len(results))),flush=True)
finally:
 command('button 272 0');m.close()
