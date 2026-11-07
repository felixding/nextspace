"""Shared original-DOM transactions and complete native group member images."""
import json,time
from pathlib import Path
from PIL import Image,ImageChops
from native_popup_fixture import PopupFixture

class RadioFixture(PopupFixture):
 def model(self,first,shadow=False):
  root=self.identify(first,shadow)
  def read():
   records=[json.loads(line) for line in (self.root/'hook.log').read_text().splitlines() if line.startswith('{') and line.endswith('}')]
   return next((row for row in reversed(records) if row.get('event')=='native-radio-model' and row.get('root')==root),None)
  return self.wait(read)
 def state(self,identifier=None):
  return self.js("return {focus:document.activeElement.id,checked:[...document.querySelectorAll('input:checked')].map(x=>x.id),events:window.events}")
 def pixels(self,identifier,members,selected,key,focused=False,label=None):
  assert self.command('pointer 1500 1100')['ok']
  data=self.js('const e=document.getElementById('+json.dumps(identifier)+');return {id:e.id,kind:12,title:"",state:0,width:e.offsetWidth,height:e.offsetHeight,enabled:1,rect:e.getBoundingClientRect().toJSON()}')
  data.update(items=[dict(id=self.identify(x),enabled=not self.js('return document.getElementById('+json.dumps(x)+').disabled')) for x in members],member=self.identify(identifier),selected=self.identify(selected) if selected else 0,key_cell=self.identify(key) if key else 0)
  name=label or identifier
  reply=self.command('reference '+json.dumps(dict(name=name+'-reference',controls=[data],focus=focused)))
  expected=Image.open(Path(reply['path'])/(identifier+'.png')).convert('RGB');expected.save(self.root/(name+'-expected.png'))
  screen=self.origin();x,y=round(screen[0]+data['rect']['x']),round(screen[1]+data['rect']['y'])
  def compared():
   actual=self.image(name).crop((x,y,x+expected.width,y+expected.height));actual.save(self.root/(name+'-actual.png'))
   return actual.size==expected.size and ImageChops.difference(actual,expected).getbbox() is None
  self.check(name+'-whole-native-member-pixels',self.wait(compared))

def run(f):
 js,check=f.js,f.check
 def clear():js('events=[];return true')
 def select(identifier,focus=None):
  js('document.getElementById('+json.dumps(identifier)+').checked=true;document.getElementById('+json.dumps(focus or identifier)+').focus();events=[];return true')
 def action(code,identifier,selected,changes=1,clicks=1):
  clear();f.key(code);s=f.state();events=s['events']
  change=[e for e in events if e['type'] in ['input','change']];click=[e for e in events if e['type']=='click']
  check('native-key-'+str(code)+'-'+identifier,s['focus']==identifier and selected in s['checked'] and len(change)==changes*2 and len(click)==clicks and all(e['trusted'] for e in change+click),state=s)
 def reset():f.reset();f.wait(lambda:js("return document.title==='Native radio groups'"));time.sleep(.15)
 members=['r0','r1','r2','r3']
 reset();f.command('pointer 1500 1100')
 model=f.model('r0');check('original-engine-group-includes-disabled-and-retains-hidden-data',model['total']==5 and model['canonical_selected']==f.identify('r0') and model['members']==[dict(id=f.identify(x),enabled=int(x!='r1')) for x in members],model=model)
 for first,group in [('s0',['s0','s1']),('u0',['u0']),('u1',['u1']),('loose0',['loose0','loose1'])]:
  model=f.model(first);check('original-engine-group-isolation-'+first,[x['id'] for x in model['members']]==[f.identify(x) for x in group],model=model)
 model=f.model('shadow0',True);check('original-engine-tree-scope-isolates-shadow-group',[x['id'] for x in model['members']]==[f.identify(x,True) for x in ['shadow0','shadow1']],model=model)
 for identifier in members:f.pixels(identifier,members,'r0','r0',label='initial-'+identifier)
 select('r0');f.pixels('r0',members,'r0','r0',True,label='focused-r0')
 action(108,'r2','r2');f.pixels('r2',members,'r2','r2',True,label='down-selected-r2')
 clear();f.command('key 42 1');f.key(108);f.command('key 42 0')
 s=f.state();check('native-shift-focus-separate-from-selection',s['focus']=='r3' and 'r2' in s['checked'] and not any(e['type'] in ['input','change'] for e in s['events']),state=s)
 f.pixels('r2',members,'r2','r3',True,label='shift-selected-r2');f.pixels('r3',members,'r2','r3',True,label='shift-focused-r3')
 action(57,'r3','r3');action(108,'r3','r3',changes=0,clicks=0)
 check('separate-forms-and-unnamed-retain-selection',all(x in f.state()['checked'] for x in ['s0','u0','u1']))
 select('r0');clear();js("document.getElementById('r0').addEventListener('keydown',e=>e.preventDefault(),{once:true});return true");f.key(108)
 check('original-keydown-cancellation-precedes-native-input',f.state()['focus']=='r0' and 'r0' in f.state()['checked'] and not any(e['type']=='click' for e in f.state()['events']))
 select('r0');js("document.getElementById('r2').addEventListener('click',e=>e.preventDefault(),{once:true});return true");f.key(108)
 s=f.state();check('original-radio-preactivation-and-cancel-rollback',s['focus']=='r2' and 'r0' in s['checked'] and not any(e['type'] in ['input','change'] for e in s['events']) and len([e for e in s['events'] if e['type']=='click'])==1,state=s)
 f.pixels('r0',members,'r0','r2',True,label='cancel-restored-r0');f.pixels('r2',members,'r0','r2',True,label='cancel-focus-r2')
 select('hidden-radio','r0');f.pixels('r0',members,None,'r0',True,label='hidden-selection-no-fake-cell')
 f.key(108);check('original-engine-unchecks-hidden-member',not js("return document.getElementById('hidden-radio').checked") and 'r2' in f.state()['checked'])
 select('r0');js("document.getElementById('r2').addEventListener('focus',e=>e.target.remove(),{once:true});return true");f.key(108)
 s=f.state();check('removed-focus-target-cannot-receive-stale-click','r0' in s['checked'] and not any(e['type']=='click' for e in s['events']),state=s)
 reset();select('r0');js("document.getElementById('r2').addEventListener('focus',e=>e.target.name='different',{once:true});return true");f.key(108)
 s=f.state();check('regrouped-focus-target-cannot-receive-stale-click','r0' in s['checked'] and not any(e['type']=='click' for e in s['events']),state=s)
 reset();select('r0');js("document.getElementById('r0').addEventListener('keydown',e=>e.target.remove(),{once:true});return true");f.key(108)
 check('removed-key-origin-retains-cancelled-gesture','r2' not in f.state()['checked'] and not any(e['type']=='click' for e in f.state()['events']))
 reset();select('r0');js("document.getElementById('r2').addEventListener('focus',e=>e.target.type='checkbox',{once:true});return true");f.key(108)
 s=f.state();check('changed-control-type-cannot-receive-stale-radio-action','r0' in s['checked'] and not js("return document.getElementById('r2').checked") and not any(e['type']=='click' for e in s['events']),state=s)
 reset();select('r0');js("document.getElementById('r1').disabled=false;return true");action(108,'r1','r1')
 f.pixels('r1',members,'r1','r1',True,label='enabled-member-r1')
 reset();select('r0');clear()
 r=js("return document.getElementById('r2').getBoundingClientRect().toJSON()");o=f.origin();assert f.command(f"pointer {round(o[0]+r['x']+r['width']/2)} {round(o[1]+r['y']+r['height']/2)}")['ok']
 f.command('button 272 1');time.sleep(.1);f.command('button 272 0');f.wait(lambda:'r2' in f.state()['checked'])
 s=f.state();check('native-matrix-pointer-original-trusted-activation',len([e for e in s['events'] if e['type']=='click'])==1 and len([e for e in s['events'] if e['type'] in ['input','change']])==2 and all(e['trusted'] for e in s['events']),state=s)
 f.pixels('r2',members,'r2','r2',True,label='pointer-selected-r2')
 old=f.model('r0')['control']
 js("window.retained=document.getElementById('r0').parentElement;retained.remove();return true")
 f.wait(lambda:f.model('r1')['total']==4)
 js("document.getElementById('main').prepend(retained);document.getElementById('r0').checked=true;document.getElementById('r0').focus();return true")
 f.wait(lambda:f.model('r0')['control']!=old)
 action(108,'r2','r2');f.pixels('r2',members,'r2','r2',True,label='reinserted-owner-r2')
 js("const e=document.createElement('input');e.type='radio';e.id='external';e.name='choice';e.setAttribute('form','main');document.body.append(e);document.getElementById('r3').checked=true;document.getElementById('r3').focus();return true")
 f.wait(lambda:f.model('r0')['total']==6)
 model=f.model('r0');check('original-engine-retains-external-form-associated-member',[x['id'] for x in model['members']]==[f.identify(x) for x in members+['external']],model=model)
 action(108,'external','external');f.pixels('external',members+['external'],'external','external',True,label='external-associated-member')
 records=[json.loads(line) for line in (f.root/'helper.jsonl').read_text().splitlines() if line.endswith('}')]
 live=set()
 for row in records:
  if row.get('kind')==12:
   key=(row.get('process'),row.get('control'))
   if row['event']=='native-form-control':live.add(key)
   elif row['event']=='native-form-destroy':live.discard(key)
 check('one-native-matrix-per-live-engine-group',len(live)==6 and not any(row['event']=='native-form-control' and row.get('kind')==3 for row in records),live_groups=len(live))
