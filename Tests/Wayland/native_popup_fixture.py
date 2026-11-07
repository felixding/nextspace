"""Shared native popup reference, seat-input and geometry checks for owned browsers."""
import ctypes as C,json,socket,sys,time
from pathlib import Path
from PIL import Image,ImageChops
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Experiments/ChromiumScrollers'))
from helper import Response
from native_controls import ControlRequest,MAGIC

class PopupFixture:
 def __init__(self,root,command,js,check,pid,origin,reset):
  self.root,self.command,self.js,self.check,self.pid,self.origin,self.reset=root,command,js,check,pid,origin,reset
 def wait(self,read,okay=lambda x:x):
  end=time.monotonic()+8;value=None
  while time.monotonic()<end:
   value=read()
   if okay(value):return value
   time.sleep(.05)
  raise AssertionError(value)
 def key(self,code):
  before=self.js("return window.events.filter(x=>x.type==='keyup').length")
  for pressed in [1,0]:assert self.command(f'key {code} {pressed}')['ok']
  self.wait(lambda:self.js("return window.events.filter(x=>x.type==='keyup').length"),lambda n:n>before)
 def state(self,identifier='select'):
  return self.js("const e=document.getElementById("+json.dumps(identifier)+");return {index:e.selectedIndex,value:e.value,open:e.matches(':open'),changes:window.events.filter(x=>x.type==='input'||x.type==='change')}")
 def focus(self,identifier='select'):
  self.js("document.getElementById("+json.dumps(identifier)+").focus();return true")
 def image(self,name):
  head=self.command('outputs')[0];reply=self.command('capture '+head['name']);event=reply['event']
  image=Image.frombytes('RGBA' if event['format']==0 else 'RGB',(event['width'],event['height']),Path(reply['path']).read_bytes(),'raw','BGRA' if event['format']==0 else 'BGRX',event['stride'],-1 if event['flags']&1 else 1).convert('RGB')
  image.save(self.root/(name+'-desktop.png'));return image
 def control_model(self,identifier):
  return self.js("const e=document.getElementById("+json.dumps(identifier)+");return {id:e.id,kind:6,title:'',state:0,width:e.offsetWidth,height:e.offsetHeight,enabled:!e.disabled,selected:e.selectedIndex,items:[...e.options].map(x=>({title:x.label,enabled:!x.disabled})),rect:e.getBoundingClientRect().toJSON()}")
 def pixels(self,identifier,focused=False,model=None,label=None):
  self.js('document.getElementById('+json.dumps(identifier)+').'+('focus()' if focused else 'blur()')+';return true');time.sleep(.15)
  data=self.control_model(identifier)
  data['screen']=self.origin()
  if model:data.update(model)
  name=(label or identifier)+('-focused' if focused else '-normal')
  reply=self.command('reference '+json.dumps(dict(name=name+'-reference',controls=[data],focus=focused)))
  expected=Image.open(Path(reply['path'])/(identifier+'.png')).convert('RGBA');canvas=Image.new('RGBA',expected.size,'white');canvas.alpha_composite(expected);expected=canvas.convert('RGB');expected.save(self.root/(name+'-expected.png'))
  x,y=round(data['screen'][0]+data['rect']['x']),round(data['screen'][1]+data['rect']['y'])
  def compared():
   actual=self.image(name).crop((x,y,x+expected.width,y+expected.height));actual.save(self.root/(name+'-actual.png'))
   return ImageChops.difference(actual,expected).getbbox() is None
  self.check(name+'-whole-native-pixels',self.wait(compared))
  return json.loads((Path(reply['path'])/'results.json').read_text())[0]
 def native_menu(self):
  return next((w for w in self.command('windows') if w['pid']!=self.pid and w['level']==101 and w['visible']),None)
 def native_state(self,count,operation=5,item=0):
  lines=(self.root/'helper.jsonl').read_text().splitlines()
  rows=[json.loads(line) for line in lines if line.endswith('}')]
  model=next(row for row in reversed(rows) if row['event']=='native-popup-model' and row['count']==count)
  request=ControlRequest(magic=MAGIC,operation=operation,process=model['process'],kind=6,control=model['control'],x=item)
  with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as connection:
   connection.settimeout(3);connection.connect(json.loads((self.root/'native-endpoint.json').read_text())['path']);connection.send(bytes(request));data=connection.recv(65536)
  assert len(data)==C.sizeof(Response);response=Response.from_buffer_copy(data);assert response.magic==MAGIC;return response
 def native_highlight(self,count):return int(self.native_state(count).parts[5].y)
 def highlight(self,count,index):
  for unused in range(count+2):
   if self.native_highlight(count)==index:return
   self.key(108)
  raise AssertionError(('Native menu did not highlight',index,self.native_highlight(count)))
 def model_geometry(self,reference):
  count=len(reference['native_item_rects']);actual=[]
  for i in range(count):
   rect=self.native_state(count,12,i).parts[6];actual.append({key:getattr(rect,key) for key in ('x','y','width','height')})
  rect=self.native_state(count).parts[6];frame={key:getattr(rect,key) for key in ('x','y','width','height')}
  return actual==reference['native_item_rects'] and frame==reference['native_menu_frame']
