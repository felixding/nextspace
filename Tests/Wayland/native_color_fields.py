"""Real native panel input and original browser event/lifetime boundaries."""
import json,time
from native_popup_fixture import PopupFixture

class ColorFixture(PopupFixture):
 def control_model(self,identifier):
  model=self.js('const e=document.getElementById('+json.dumps(identifier)+');return {id:e.id,kind:16,title:"",state:0,width:e.offsetWidth,height:e.offsetHeight,enabled:!e.disabled,value:e.value,rect:e.getBoundingClientRect().toJSON()}')
  model['rgba']=[int(model['value'][i:i+2],16)/255 for i in (1,3,5)]+[1]
  model['value']=0;return model
 def panel(self):
  return next((w for w in self.command('windows') if w['pid']!=self.pid and w['title']=='Colors' and w['visible']),None)
 def click_point(self,x,y):
  for text in [f'pointer {round(x)} {round(y)}','button 272 1','button 272 0']:assert self.command(text)['ok'],text
 def click(self,identifier):
  box=self.control_model(identifier)['rect'];origin=self.origin()
  self.click_point(origin[0]+box['x']+box['width']/2,origin[1]+box['y']+box['height']/2)
 def close_panel(self):
  panel=self.panel();assert panel
  self.click_point(panel['x']+panel['width']-11,panel['y']+11)
  self.wait(lambda:not self.panel())
 def select_color(self):
  panel=self.panel();assert panel
  # Exercise the original installed color wheel with real seat input.
  self.click_point(panel['x']+120,panel['y']+155)

def run(fixture):
 js,check=fixture.js,fixture.check
 check('native-color-document',js('return document.title')=='Native color fields')
 fixture.command('pointer 1500 1100')
 for identifier in ['normal','second','disabled']:fixture.pixels(identifier,label='color-'+identifier)
 fixture.click('disabled');time.sleep(.15)
 check('disabled-color-does-not-open',not fixture.panel() and js('return !events.length'))
 js('normal.addEventListener("click",e=>e.preventDefault(),{once:true});return true')
 fixture.click('normal');time.sleep(.15)
 check('cancelled-engine-click-does-not-open',not fixture.panel() and js('return !events.length'))
 fixture.click('normal');panel=fixture.wait(fixture.panel)
 check('original-native-color-panel-opens',panel['app_id'].startswith('org.nextspace.') and js('return normal.matches(":open")'))
 fixture.image('color-panel-open')
 before=js('return normal.value');fixture.select_color()
 fixture.wait(lambda:js('return normal.value')!=before)
 changed=js('return events')
 check('native-panel-original-trusted-input',len(changed)==1 and changed[0]['id']=='normal' and changed[0]['type']=='input' and changed[0]['trusted'],events=changed)
 fixture.close_panel();fixture.wait(lambda:js('return events.length')==2)
 changed=js('return events')
 check('native-panel-original-trusted-change',[e['type'] for e in changed]==['input','change'] and all(e['trusted'] for e in changed) and js('return !normal.matches(":open")'),events=changed)
 fixture.pixels('normal',label='color-after-selection')
 fixture.click('normal');fixture.wait(fixture.panel)
 js('window.events=[];normal.value="#ff00ff";return true');time.sleep(.15)
 check('script-update-does-not-synthesize-input',js('return normal.value==="#ff00ff"&&!events.length'))
 fixture.image('color-panel-script-update')
 fixture.close_panel();fixture.wait(lambda:js('return !normal.matches(":open")'))
 check('script-model-preserved-after-panel-close',js('return normal.value==="#ff00ff"&&!window.events.some(e=>e.type==="input")'),events=js('return window.events'))
 fixture.pixels('normal',label='color-after-script')
 fixture.click('normal');fixture.wait(fixture.panel)
 js('normal.remove();return true');fixture.wait(lambda:not fixture.panel())
 check('removed-owner-retires-native-panel',js('return !document.getElementById("normal")'))
 fixture.click('second');fixture.wait(fixture.panel)
 check('second-owner-reuses-shared-panel',sum(1 for w in fixture.command('windows') if w['title']=='Colors' and w['visible'])==1 and js('return second.matches(":open")'))
 fixture.select_color();fixture.wait(lambda:js('return second.value')!='#c08040')
 fixture.close_panel()
 fixture.pixels('second',label='color-second-owner')
 fixture.js('second.focus();return true')
 for pressed in [1,0]:assert fixture.command(f'key 28 {pressed}')['ok']
 fixture.wait(fixture.panel)
 check('original-engine-keyboard-opens-native-panel',js('return second.matches(":open")'))
 fixture.close_panel()
