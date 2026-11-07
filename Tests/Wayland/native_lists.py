"""Shared real-seat native list checks for browser engine adapters."""
import json,os,select,subprocess,time
from pathlib import Path
from PIL import ImageChops
from native_popup_fixture import PopupFixture

class ListFixture(PopupFixture):
 key_cell=0
 def records(self):return [json.loads(x) for x in (self.root/'helper.jsonl').read_text().splitlines() if x.startswith('{') and x.endswith('}')]
 def pixels(self,*args,**kwargs):
  assert self.command('pointer 1500 1100')['ok']
  return super().pixels(*args,**kwargs)
 def control_model(self,identifier):
  data=self.js('const e=document.getElementById('+json.dumps(identifier)+');return {id:e.id,kind:13,title:"",state:0,width:e.offsetWidth,height:e.offsetHeight,enabled:!e.disabled,flags:e.multiple?1:0,items:[...e.options].filter(x=>getComputedStyle(x).display!=="none").map((x,i)=>({id:i+1,title:x.label,enabled:!x.disabled,selected:x.selected})),rect:e.getBoundingClientRect().toJSON()}')
  data['key_cell']=self.key_cell;return data
 def plan(self,name,keys):
  data=self.control_model('list');data['list_keys']=keys
  reply=self.command('reference '+json.dumps(dict(name=name,controls=[data],focus=True)))
  return json.loads((Path(reply['path'])/'results.json').read_text())[0]
 def selected(self):return self.js('return [...list.options].flatMap((option,index)=>option.selected?[index+1]:[])')
 def changes(self):return self.js('return window.events.filter(event=>event.type==="input"||event.type==="change")')
 def clear(self):self.js('window.events=[];return true')
 def point(self,rect):
  data=self.control_model('list');origin=self.origin()
  x=origin[0]+data['rect']['x']+rect['x']+rect['width']/2
  y=origin[1]+data['rect']['y']+rect['y']+rect['height']/2
  assert self.command(f'pointer {round(x)} {round(y)}')['ok']
 def click(self,rect):
  self.point(rect);assert self.command('button 272 1')['ok'];time.sleep(.05)
  assert self.command('button 272 0')['ok'];time.sleep(.15)
 def native_actions(self):return [x for x in self.records() if x['event']=='native-form-action' and x.get('kind')==13]
 def ordinary_gesture(self):
  env=dict(os.environ,**json.loads((self.root/'runtime.json').read_text()))
  helper=json.loads((self.root/'launch.json').read_text())['pids'][1]
  for entry in Path('/proc',str(helper),'environ').read_bytes().split(b'\0'):
   if entry.startswith(b'GNUSTEP_CONFIG_FILE='):env['GNUSTEP_CONFIG_FILE']=entry.split(b'=',1)[1].decode()
  process=subprocess.Popen([str(self.ordinary_probe),'-GSBackend','wayland','-GSTheme','NextSpace'],env=env,
    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(self.root/'ordinary-gesture.stderr').open('w'),text=True)
  try:
   assert select.select([process.stdout],[],[],15)[0];ready=json.loads(process.stdout.readline());assert ready['ready']
   window=self.wait(lambda:next((w for w in self.command('windows') if w['pid']==process.pid),None));assert self.command('focus '+str(window['id']))['ok']
   def point(rect):
    x=window['x']+window['frame_left']+rect['x']+rect['width']/2;y=window['y']+window['frame_top']+rect['y']+rect['height']/2
    assert self.command(f'pointer {round(x)} {round(y)}')['ok']
   def snapshot():
    process.stdin.write('snapshot\n');process.stdin.flush();assert select.select([process.stdout],[],[],10)[0];return json.loads(process.stdout.readline())
   observed=[dict(case='initial',native=snapshot())]
   point(ready['rects'][0]);assert self.command('button 272 1')['ok'];time.sleep(.04)
   assert self.command('pointer 600 500')['ok'];assert self.command('button 272 0')['ok'];time.sleep(.1)
   observed.append(dict(case='outside-release',native=snapshot()))
   point(ready['rects'][2]);assert self.command('button 272 1')['ok'];time.sleep(.04);assert self.command('button 272 0')['ok'];time.sleep(.1)
   observed.append(dict(case='next-selection',native=snapshot()))
   assert self.command('pointer 1500 1100')['ok'];time.sleep(.1)
   image=self.image('ordinary-gesture');x=window['x']+window['frame_left'];y=window['y']+window['frame_top']
   reference=image.crop((x,y,x+180,y+96));reference.save(self.root/'ordinary-gesture-reference.png')
   (self.root/'ordinary-gesture-results.json').write_text(json.dumps(observed,indent=2)+'\n')
   return reference,observed
  finally:
   self.command('button 272 0')
   if process.poll() is None:process.stdin.write('quit\n');process.stdin.flush();process.wait(timeout=10)
   window=self.wait(lambda:next((w for w in self.command('windows') if w['pid']==self.pid and w['level']==0),None));assert self.command('focus '+str(window['id']))['ok']

def run(f):
 f.reset();f.focus('list');f.key_cell=0;time.sleep(.25)
 initial=f.plan('initial-reference',[]);f.key_cell=initial['list_state']['key_cell'];f.pixels('list',True,label='initial')
 def keyboard(name,key,code,modifiers=0):
  before=f.selected();reference=f.plan(name+'-reference',[dict(key=key,modifiers=modifiers)])
  f.clear()
  if modifiers&1:assert f.command('key 42 1')['ok']
  f.key(code)
  if modifiers&1:assert f.command('key 42 0')['ok']
  expected=reference['list_state'];f.wait(lambda:f.selected()==expected['selected'])
  f.check(name+'-selection-matches-original-native-control',f.selected()==expected['selected'],selected=f.selected(),native=expected)
  events=f.changes();changed=before!=expected['selected']
  f.check(name+'-original-trusted-events',[x['type'] for x in events]==(['input','change'] if changed else []) and all(x['trusted'] for x in events),events=events)
  f.key_cell=expected['key_cell'];f.pixels('list',True,label=name)
 keyboard('down-skips-disabled',9,108);keyboard('next-row',9,108)
 actions=len(f.native_actions());f.js('list.addEventListener("keydown",event=>event.preventDefault(),{once:true});return true');f.clear();f.key(103)
 f.check('cancelled-key-leaves-native-and-DOM-selection',f.selected()==[4] and not f.changes() and len(f.native_actions())==actions)
 f.clear();actions=len(f.native_actions());f.js('list.selectedIndex=0;return true')
 f.check('script-selection-keeps-original-model-without-native-action',f.selected()==[1] and not f.changes() and len(f.native_actions())==actions)
 f.pixels('list',True,label='script-selection')
 f.clear();f.click(initial['native_item_rects'][2]);f.key_cell=3
 f.check('pointer-original-trusted-events',f.selected()==[3] and [x['type'] for x in f.changes()]==['input','change'] and all(x['trusted'] for x in f.changes()),selected=f.selected(),events=f.changes())
 f.pixels('list',True,label='pointer')
 actions=len(f.native_actions());f.clear();f.click(initial['native_item_rects'][1])
 f.check('disabled-option-keeps-native-selection-without-DOM-change',f.selected()==[3] and not f.changes(),native_actions=f.native_actions()[actions:])
 f.js('list.multiple=true;list.options[0].selected=true;list.options[2].selected=true;return true');time.sleep(.2);f.pixels('list',True,label='multiple')
 keyboard('shift-keeps-native-focus-separate-from-selection',9,108,1)
 keyboard('multiple-up',8,103)
 f.js('list.options[2].label="Changed";return true');time.sleep(.2);f.pixels('list',True,label='changed-title')
 f.js('list.options[2].textContent="Another title";list.options[2].removeAttribute("label");return true');time.sleep(.2);f.pixels('list',True,label='changed-text')
 f.js('list.disabled=true;return true');time.sleep(.2);f.pixels('list',False,label='disabled')
 f.clear();actions=len(f.native_actions());f.click(initial['native_item_rects'][0]);f.check('disabled-control-has-no-selection-action',not f.changes() and len(f.native_actions())==actions)
 f.js('list.disabled=false;return true');f.focus('list');time.sleep(.15)
 f.clear();f.js('list.addEventListener("mousedown",event=>event.preventDefault(),{once:true});return true');actions=len(f.native_actions());f.click(initial['native_item_rects'][0])
 f.check('cancelled-press-has-no-native-action',not f.changes() and len(f.native_actions())==actions)
 owner=next(x for x in reversed(f.records()) if x['event']=='native-form-control' and x.get('kind')==13)
 f.js('list.style.appearance="none";return true')
 f.wait(lambda:any(x['event']=='native-form-destroy' and x.get('kind')==13 and x.get('control')==owner['control'] and x.get('process')==owner['process'] for x in f.records()))
 f.check('unsupported-appearance-releases-native-ownership',True)
 before=len(f.records());f.js('list.style.appearance="auto";return true')
 f.wait(lambda:any(x['event']=='native-form-control' and x.get('kind')==13 for x in f.records()[before:]))
 f.check('native-appearance-can-bind-again',True)
 f.js('list.multiple=false;list.selectedIndex=0;return true');f.key_cell=1;time.sleep(.15);f.pixels('list',True,label='single-again')
 before=len(f.records());f.point(initial['native_item_rects'][0]);assert f.command('button 272 1')['ok'];time.sleep(.04)
 assert f.command('pointer 600 500')['ok'];assert f.command('button 272 0')['ok'];time.sleep(.2)
 f.check('outside-release-ends-original-native-tracking',f.wait(lambda:any(x['event']=='native-form-release' and x.get('kind')==13 for x in f.records()[before:])))
 f.clear();f.click(initial['native_item_rects'][2]);f.key_cell=3
 f.check('new-gesture-works-after-outside-release',f.selected()==[3] and [x['type'] for x in f.changes()]==['input','change'])
 # The original matrix can retain a cell's visual state after outside release
 # even when selectedCells no longer contains it. Compare the actual ordinary
 # native gesture, rather than reconstructing an incomplete visual oracle.
 reference,observed=f.ordinary_gesture();time.sleep(.15);data=f.control_model('list');origin=f.origin()
 x=round(origin[0]+data['rect']['x']);y=round(origin[1]+data['rect']['y'])
 actual=f.image('after-outside-release').crop((x,y,x+180,y+96));actual.save(f.root/'after-outside-release-actual.png')
 f.check('after-outside-release-whole-original-native-pixels',ImageChops.difference(actual,reference).getbbox() is None,native=observed)
 owner=next(x for x in reversed(f.records()) if x['event']=='native-form-control' and x.get('kind')==13)
 retired=lambda:any(x['event']=='native-form-destroy' and x.get('kind')==13 and x.get('control')==owner['control'] and x.get('process')==owner['process'] for x in f.records())
 f.js('list.addEventListener("change",()=>list.remove(),{once:true});return true');f.clear();f.key(108)
 f.check('original-change-callback-can-retire-control',f.js('return !document.getElementById("list")'))
 f.wait(retired)
 f.check('retired-frame-destroys-native-control',retired())
