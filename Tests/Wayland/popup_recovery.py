"""Native popup data and actions across actual supervised host replacement."""
import json,subprocess,sys,time
from pathlib import Path
from PIL import Image,ImageChops

class PopupRecovery:
 def __init__(self,js,check,command,wait,desktop,root,args,environment,repo,hosts,origin=None,indent=''):
  self.js,self.check,self.command,self.wait,self.desktop=js,check,command,wait,desktop
  self.root,self.args,self.environment,self.repo=root,args,environment,repo
  self.hosts=hosts
  self.origin=origin or (lambda:js('return [mozInnerScreenX,mozInnerScreenY]'));self.indent=indent
 def state(self):
  return self.js("const e=document.getElementById('native-popup-recovery');return {index:e.selectedIndex,value:e.value,open:e.matches(':open'),events:window.__popupRecoveryEvents}")
 def key(self,code):
  before=self.js('return window.__popupRecoveryKeyups')
  for pressed in [1,0]:assert self.command(f'key {code} {pressed}')['ok']
  self.wait(lambda:self.js('return window.__popupRecoveryKeyups'),lambda n:n>before)
 def compare(self,label):
  self.js("document.getElementById('native-popup-recovery').blur();return true")
  data=self.js("const e=document.getElementById('native-popup-recovery');return {rect:e.getBoundingClientRect().toJSON(),index:e.selectedIndex}");data['screen']=self.origin()
  model=dict(id='native-popup-recovery',kind=6,title='',state=0,width=200,height=26,enabled=1,selected=-1 if data['index']==0 else 2,
    popup_title='Retained hidden' if data['index']==0 else None,
    items=[dict(title='Group',enabled=0),dict(title=self.indent+'Blocked',enabled=0),dict(title='Visible')])
  definition=self.root/(label+'-popup-model.json');definition.write_text(json.dumps([model])+'\n');references=self.root/(label+'-popup-reference')
  result=subprocess.run([sys.executable,str(self.repo/'Experiments/ChromiumScrollers/native-control-reference.py'),'--library',str(self.args.library),'--controls',str(definition),'--output',str(references),'-GSBackend','wayland'],env=self.environment,text=True,capture_output=True,timeout=15)
  (self.root/(label+'-popup-reference.stdout')).write_text(result.stdout);(self.root/(label+'-popup-reference.stderr')).write_text(result.stderr);assert result.returncode==0,result.stderr
  native=Image.open(references/'native-popup-recovery.png').convert('RGBA');expected=Image.new('RGBA',native.size,'white');expected.alpha_composite(native);expected=expected.convert('RGB')
  left=round(data['screen'][0]+data['rect']['x']);top=round(data['screen'][1]+data['rect']['y'])
  def same():
   actual=self.desktop(label+'-popup').crop((left,top,left+200,top+26));actual.save(self.root/(label+'-popup-actual.png'))
   return ImageChops.difference(actual,expected).getbbox() is None
  self.check(label+'-complete-native-popup-pixels',self.wait(same,lambda x:x))
 def choose(self,label):
  self.js("window.__popupRecoveryEvents=[];document.getElementById('native-popup-recovery').focus();return true")
  self.key(57);self.wait(self.state,lambda s:s['open'])
  self.check(label+'-actual-native-popup-window',any(w['visible'] and w['level']==101 and w['pid'] in self.hosts() for w in self.command('windows')))
  for unused in range(4):
   self.key(108);self.key(28);state=self.state()
   if not state['open']:break
  self.check(label+'-original-index-and-one-trusted-action',state['index']==2 and state['value']=='visible' and [e['type'] for e in state['events']]==['input','change'] and all(e['trusted'] for e in state['events']),actual=state)
 def before(self):
  self.js("const e=document.createElement('select');e.id='native-popup-recovery';e.style.cssText='position:fixed;right:24px;bottom:24px;width:200px;height:26px;z-index:9999';e.innerHTML='<option hidden selected value=hidden>Retained hidden</option><optgroup label=Group disabled><option value=blocked>Blocked</option></optgroup><option value=visible>Visible</option>';document.body.append(e);window.__popupRecoveryEvents=[];for(const type of ['input','change'])document.addEventListener(type,event=>{if(event.target.id===e.id)__popupRecoveryEvents.push({type,id:e.id,trusted:event.isTrusted})});window.__popupRecoveryKeyups=0;document.addEventListener('keyup',()=>window.__popupRecoveryKeyups++);return true")
  self.compare('before-host-replacement');self.choose('before-host-replacement')
  self.js("document.getElementById('native-popup-recovery').selectedIndex=0;window.__popupRecoveryEvents=[];return true")
  self.compare('before-host-retained-hidden')
 def after(self):
  self.check('host-replacement-retains-popup-dom-model',self.state()['index']==0 and self.state()['value']=='hidden')
  self.compare('after-host-replacement');self.choose('after-host-replacement');self.compare('after-host-native-action')
