"""Original engine label filtering with shared native semantic activation."""
import json,time


def run(f):
 js,check,command=f.js,f.check,f.command;members=['r0','r1','r2','r3']
 def records():return [json.loads(x) for x in (f.root/'helper.jsonl').read_text().splitlines() if x.startswith('{') and x.endswith('}')]
 def setup(initial='r0',script=''):
  f.reset();f.model('r0')
  js("for(const id of ['r0','r1','r2','r3']){const e=document.getElementById(id),s=document.createElement('span');s.id='label-'+id;s.textContent=e.parentNode.lastChild.textContent;e.parentNode.lastChild.replaceWith(s)}document.getElementById('"+initial+"').checked=true;document.getElementById('"+initial+"').focus();window.events=[];window.pointerClicks=[];document.addEventListener('click',e=>pointerClicks.push({id:e.target.id,kind:e.constructor.name,pointerType:e.pointerType,detail:e.detail,button:e.button,trusted:e.isTrusted}),true);"+script+";return true")
  model=f.wait(lambda:(m if (m:=f.model('r0'))['selected']==f.identify(initial) else None))
  owner=next(x for x in reversed(records()) if x['event']=='native-form-control' and x.get('kind')==12 and x['control']==model['control']);time.sleep(1.1);return owner
 def click(owner,identifier,script=None):
  before=len(records())
  if script:js(script+';return true')
  else:
   rect=js('return document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()');origin=f.origin()
   assert command('pointer '+str(round(origin[0]+rect['x']+rect['width']/2))+' '+str(round(origin[1]+rect['y']+rect['height']/2)))['ok']
   assert command('button 272 1')['ok'];time.sleep(.04);assert command('button 272 0')['ok']
  time.sleep(.15);state=f.state();state['pointer_clicks']=js('return pointerClicks')
  rows=[x for x in records()[before:] if x.get('kind')==12 and x.get('control')==owner['control'] and x.get('process')==owner['process']]
  return state,rows
 def actions(rows):return [x for x in rows if x['event']=='native-form-action']
 def source_click(state,identifier):return [x for x in state['pointer_clicks'] if x['id']==identifier]
 def native_action(name,owner,identifier,selected,changes,focus=True):
  state,rows=click(owner,identifier);native=actions(rows);forwarded=source_click(state,selected)
  check(name+'-native-semantic-action',len(native)==1 and native[0]['value']==members.index(selected) and len([x for x in rows if x['event']=='native-form-perform-click' and x['accepted']==1])==1 and not any(x['event']=='native-form-press' for x in rows),native=rows)
  check(name+'-original-label-and-control-events',selected in state['checked'] and (not focus or state['focus']==selected) and len(forwarded)==1 and forwarded[0]['trusted'] and forwarded[0]['kind']=='PointerEvent' and forwarded[0]['pointerType']=='mouse' and len([x for x in state['events'] if x['type'] in ['input','change']])==2*changes,state=state)
  return state,rows
 owner=setup();native_action('implicit-label',owner,'label-r2','r2',1);f.pixels('r2',members,'r2','r2',True,label='implicit-label')
 owner=setup('r2');native_action('selected-label',owner,'label-r2','r2',0)
 owner=setup();state,rows=click(owner,'label-r1')
 check('disabled-label-retains-original-engine-filtering',not actions(rows) and 'r0' in state['checked'] and not source_click(state,'r1') and not any(x['type'] in ['input','change'] for x in state['events']),state=state,native=rows)
 explicit="document.getElementById('r2').parentNode.insertAdjacentHTML('afterend','<label id=external-label for=r2><span id=explicit-text>External label</span></label>')"
 owner=setup(script=explicit);native_action('explicit-nested-label',owner,'explicit-text','r2',1);f.pixels('r2',members,'r2','r2',True,label='explicit-label')
 owner=setup(script="document.getElementById('r2').parentNode.addEventListener('click',e=>e.preventDefault(),{once:true})")
 state,rows=click(owner,'label-r2')
 check('cancelled-label-does-not-perform-native-action',not actions(rows) and 'r0' in state['checked'] and not source_click(state,'r2'),state=state,native=rows)
 owner=setup(script="document.getElementById('r2').addEventListener('click',e=>e.preventDefault(),{once:true})")
 state,rows=click(owner,'label-r2')
 check('cancelled-forwarded-label-click-restores-original-model',len(actions(rows))==1 and 'r0' in state['checked'] and state['focus']=='r2' and len(source_click(state,'r2'))==1 and not any(x['type'] in ['input','change'] for x in state['events']),state=state,native=rows)
 f.pixels('r0',members,'r0','r2',True,label='cancelled-label-selection');f.pixels('r2',members,'r0','r2',True,label='cancelled-label-key')
 owner=setup(script="document.getElementById('r2').parentNode.insertAdjacentHTML('beforeend','<a id=interactive-label href=#>Interactive link</a>')")
 state,rows=click(owner,'interactive-label')
 check('interactive-label-descendant-keeps-original-filtering',not actions(rows) and 'r0' in state['checked'] and not source_click(state,'r2'),state=state,native=rows)
 owner=setup(script=explicit+";document.getElementById('external-label').addEventListener('click',e=>e.currentTarget.htmlFor='r3',{once:true})")
 native_action('retargeted-label',owner,'explicit-text','r3',1);f.pixels('r3',members,'r3','r3',True,label='retargeted-label')
 owner=setup(script=explicit+";document.getElementById('external-label').addEventListener('click',e=>document.getElementById('r2').remove(),{once:true})")
 state,rows=click(owner,'explicit-text')
 check('removed-label-target-does-not-perform-native-action',not actions(rows) and 'r0' in state['checked'] and not source_click(state,'r2'),state=state,native=rows)
 owner=setup();state,rows=click(owner,'label-r2',"document.getElementById('r2').parentNode.click()")
 check('programmatic-label-retains-original-engine-model-path',not actions(rows) and 'r2' in state['checked'],state=state,native=rows)
 f.pixels('r2',members,'r2','r2',state['focus']=='r2',label='programmatic-label')
 owner=setup(script="document.getElementById('r2').parentNode.style.userSelect='text'")
 before=len(records());rect=js("return document.getElementById('label-r2').getBoundingClientRect().toJSON()");o=f.origin()
 x,y=round(o[0]+rect['x']+2),round(o[1]+rect['y']+rect['height']/2)
 assert command(f'pointer {x} {y}')['ok'];assert command('button 272 1')['ok'];time.sleep(.04)
 assert command(f'pointer {x+max(8,round(rect["width"])-4)} {y}')['ok'];time.sleep(.04);assert command('button 272 0')['ok'];time.sleep(.15)
 state=f.state();rows=[x for x in records()[before:] if x.get('kind')==12 and x.get('control')==owner['control']]
 check('label-text-drag-keeps-original-selection-filtering',not actions(rows) and 'r0' in state['checked'] and bool(js('return getSelection().toString()')),state=state,native=rows)
