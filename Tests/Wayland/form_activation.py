"""Native button action state and original engine activation transactions."""
import json,time
from native_popup_fixture import PopupFixture

class FormFixture(PopupFixture):
 def records(self):return [json.loads(x) for x in (self.root/'helper.jsonl').read_text().splitlines() if x.startswith('{') and x.endswith('}')]
 def setup(self,kind='checkbox',checked=False,mixed=False,script=''):
  before=len(self.records());self.reset()
  self.js('configure('+json.dumps(kind)+','+json.dumps(checked)+','+json.dumps(mixed)+');'+script+';return true')
  self.focus('control')
  native_kind=2 if kind=='checkbox' else 1
  owner=self.wait(lambda:next((x for x in reversed(self.records()[before:]) if x['event']=='native-form-control' and x.get('kind')==native_kind),None))
  time.sleep(.3);self.owner=owner;self.model_kind=native_kind;return owner
 def state(self):return self.js("const e=document.getElementById('control');return {checked:e.checked,mixed:e.indeterminate,disabled:e.disabled,focus:document.activeElement.id,events:window.events,submits:window.submits,resets:window.resets,actions:window.actions,resetValue:document.getElementById('reset-target')?.value}")
 def control_model(self,identifier):
  return self.js('const e=document.getElementById('+json.dumps(identifier)+');return {id:e.id,kind:' +str(self.model_kind)+',title:e.tagName==="BUTTON"?e.textContent:(e.type==="checkbox"?"":e.value),state:e.indeterminate?-1:(e.checked?1:0),width:e.offsetWidth,height:e.offsetHeight,enabled:!e.disabled,rect:e.getBoundingClientRect().toJSON()}')
 def pixels(self,*args,**kwargs):
  assert self.command('pointer 1500 1100')['ok']
  return super().pixels(*args,**kwargs)
 def trigger(self,how='label'):
  if how=='key':self.focus('control')
  self.js('window.events=[];return true');before=len(self.records())
  if how=='key':self.key(57)
  elif how=='programmatic':self.js("document.getElementById('label').click();return true")
  else:
   rect=self.js('return document.getElementById('+json.dumps('label-text' if how=='label' else 'control' if how=='pointer' else how)+').getBoundingClientRect().toJSON()');o=self.origin()
   assert self.command('pointer '+str(round(o[0]+rect['x']+rect['width']/2))+' '+str(round(o[1]+rect['y']+rect['height']/2)))['ok']
   assert self.command('button 272 1')['ok'];time.sleep(.04);assert self.command('button 272 0')['ok']
  def native_rows():return [x for x in self.records()[before:] if x.get('kind')==self.owner['kind'] and x.get('control')==self.owner['control'] and x.get('process')==self.owner['process']]
  if how=='pointer':self.wait(lambda:any(x['event']=='native-form-release' for x in native_rows()))
  if how not in ['key','programmatic']:
   target='label-text' if how=='label' else 'control' if how=='pointer' else how
   self.wait(lambda:any(x['type']=='click' and x['id']==target for x in self.state()['events']))
  time.sleep(.05);rows=native_rows()
  return self.state(),rows

def probe(f):
 rows=[]
 for how in ['pointer','key','label']:
  for checked,mixed in [(False,False),(True,False),(False,True),(True,True)]:
   f.setup(checked=checked,mixed=mixed);state,native=f.trigger(how);actions=[x for x in native if x['event']=='native-form-action']
   rows.append(dict(how=how,initial_checked=checked,initial_mixed=mixed,state=state,native=native));(f.root/'form-activation-observations.json').write_text(json.dumps(rows,indent=2)+'\n')
   print(json.dumps(dict(how=how,checked=checked,mixed=mixed,native_state=[x['state'] for x in actions],dom_checked=state['checked'],dom_mixed=state['mixed'])),flush=True)

def run(f):
 def actions(rows):return [x for x in rows if x['event']=='native-form-action']
 def clicks(state):return [x for x in state['events'] if x['id']=='control' and x['type']=='click']
 def changes(state):return [x for x in state['events'] if x['type'] in ['input','change'] and x['id']=='control']
 for how in ['pointer','key','label']:
  for checked,mixed in [(False,False),(True,False),(False,True),(True,True)]:
   name=how+'-'+str(int(checked))+'-'+str(int(mixed));f.setup(checked=checked,mixed=mixed)
   state,rows=f.trigger(how);native=actions(rows)
   f.check(name+'-one-original-native-action',len(native)==1 and (how!='label' or len([x for x in rows if x['event']=='native-form-perform-click' and x['accepted']])==1),native=rows)
   expected_checked=checked if native[0]['state']==-1 else native[0]['state']>0
   f.check(name+'-native-result-enters-original-DOM-transaction',state['checked']==expected_checked and state['mixed']==(native[0]['state']==-1) and len(clicks(state))==1 and clicks(state)[0]['checked']==expected_checked and clicks(state)[0]['mixed']==state['mixed'],state=state,native=native)
   f.check(name+'-original-trusted-events',len(changes(state))==2 and all(x['trusted'] for x in clicks(state)+changes(state)) and (how=='key' or (clicks(state)[0]['kind']=='PointerEvent' and clicks(state)[0]['pointerType']=='mouse')),state=state)
   f.pixels('control',True,label=name)
 for how in ['pointer','key','label']:
  for checked in [False,True]:
   name='cancel-'+how+'-'+str(int(checked));f.setup(checked=checked,mixed=True,script="control.addEventListener('click',e=>e.preventDefault(),{once:true})")
   state,rows=f.trigger(how)
   f.check(name+'-original-journal-restores-checked-and-mixed',len(actions(rows))==1 and state['checked']==checked and state['mixed'] and len(clicks(state))==1 and not changes(state),state=state,native=rows)
   f.pixels('control',True,label=name)
 f.setup(script="control.addEventListener('click',e=>control.checked=false,{once:true})");state,rows=f.trigger('label')
 f.check('application-click-handler-keeps-model-ownership',len(actions(rows))==1 and actions(rows)[0]['state']==1 and clicks(state)[0]['checked'] and not state['checked'],state=state,native=rows)
 f.pixels('control',True,label='application-override')
 f.setup(checked=True,mixed=True,script="label.addEventListener('click',e=>e.preventDefault(),{once:true})");state,rows=f.trigger('label')
 f.check('cancelled-label-keeps-original-filtering',not actions(rows) and state['checked'] and state['mixed'] and not clicks(state),state=state,native=rows)
 f.setup(script="control.disabled=true");state,rows=f.trigger('label')
 f.check('disabled-label-keeps-original-filtering',not actions(rows) and not state['checked'] and not clicks(state),state=state,native=rows)
 f.setup(script="label.insertAdjacentHTML('beforeend','<a href=# id=link>Interactive</a>')");state,rows=f.trigger('link')
 f.check('interactive-label-content-keeps-original-filtering',not actions(rows) and not state['checked'] and not clicks(state),state=state,native=rows)
 f.setup(script="label.removeAttribute('for');label.append(control)");state,rows=f.trigger('label')
 f.check('implicit-label-uses-original-association',len(actions(rows))==1 and state['checked'] and len(clicks(state))==1,state=state,native=rows)
 f.setup(checked=True,mixed=True);state,rows=f.trigger('programmatic')
 f.check('programmatic-click-keeps-original-model-path',not actions(rows) and not state['checked'] and not state['mixed'],state=state,native=rows)
 f.pixels('control',True,label='programmatic')
 f.setup(script="control.addEventListener('click',e=>{if(e.isTrusted){document.body.insertAdjacentHTML('beforeend','<input id=nested type=checkbox>');document.getElementById('nested').click()}},{once:true})");state,rows=f.trigger('label')
 f.check('nested-programmatic-click-does-not-reuse-native-receipt',len(actions(rows))==1 and state['checked'] and len(clicks(state))==1 and f.js("return document.getElementById('nested').checked") and len([x for x in state['events'] if x['id']=='nested' and x['type']=='click' and not x['trusted']])==1,state=state,native=rows)
 for kind in ['button','button-input','submit','reset']:
  for cancel in [False,True]:
   name=kind+('-cancel' if cancel else '')
   script=("document.getElementById('reset-target').value='Modified';" if kind=='reset' else '')+("control.addEventListener('click',e=>e.preventDefault(),{once:true})" if cancel else '')
   f.setup(kind=kind,script=script);state,rows=f.trigger('label')
   f.check(name+'-one-native-label-action',len(actions(rows))==1 and len([x for x in rows if x['event']=='native-form-perform-click' and x['accepted']])==1,native=rows)
   f.check(name+'-original-trusted-click',len(clicks(state))==1 and clicks(state)[0]['trusted'] and clicks(state)[0]['kind']=='PointerEvent' and clicks(state)[0]['pointerType']=='mouse',state=state)
   okay=state['submits']==int(kind=='submit' and not cancel) and state['resets']==int(kind=='reset' and not cancel)
   if kind in ['button','button-input']:okay=okay and state['actions']==1
   if kind=='reset':okay=okay and state['resetValue']==('Modified' if cancel else 'Original')
   f.check(name+'-original-form-default-and-cancellation',okay,state=state)
   f.pixels('control',True,label=name)
